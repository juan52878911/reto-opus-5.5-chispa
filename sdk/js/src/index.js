// Cliente de POST /v1/decide y GET /healthz de chispa-server. Sin dependencias: usa fetch (node ≥ 20 y navegadores).

import { ErrorChispa } from "./error.js";
import { LIMITES, validar, bytes } from "./limites.js";

export { ErrorChispa, LIMITES, bytes };

const dormir = (ms) => new Promise((r) => setTimeout(r, ms));
const REINTENTABLES = new Set([429, 500, 502, 503]); // igual que `_REINTENTABLES` de cliente.py
const TOPE_RETRY_AFTER_MS = 30000; // igual que el cliente Python

/** `Retry-After` en segundos → ms con tope; una fecha HTTP u otra cosa cuenta como ausente (undefined). */
function retryAfterMs(h) {
  const v = h?.get?.("Retry-After")?.trim();
  if (!v || !/^\d+(\.\d+)?$/.test(v)) return undefined;
  return Math.min(Number(v) * 1000, TOPE_RETRY_AFTER_MS);
}

/**
 * @typedef {import("./index.d.ts").Pregunta} Pregunta
 * @typedef {import("./index.d.ts").Resultado} Resultado
 */

export class ChispaCliente {
  /**
   * @param {{url?: string, timeoutMs?: number, reintentos?: number, esperaMs?: number,
   *          limites?: Partial<typeof LIMITES>, fetch?: typeof fetch}} [opts]
   * `reintentos`: reintentos extra tras el primer intento (por defecto 3), como el cliente Python. `timeoutMs` (35 s) debe superar el `-timeout` del servidor (30 s).
   */
  constructor({ url = "http://127.0.0.1:8090", timeoutMs = 35000, reintentos = 3, esperaMs = 200, limites, fetch: f, dormir: d } = {}) {
    this._dormir = d ?? dormir;
    this.url = url.replace(/\/+$/, "");
    this.timeoutMs = timeoutMs;
    this.reintentos = reintentos;
    this.esperaMs = esperaMs;
    this.limites = { ...LIMITES, ...limites };
    this._fetch = f ?? globalThis.fetch;
    if (typeof this._fetch !== "function") throw new TypeError("no hay fetch: usa node ≥ 20 o pasa {fetch}");
  }

  /**
   * Decide una o varias preguntas sobre el mismo texto. Resultados en el orden de `preguntas`.
   * Cada pregunta sin nonce recibe uno antes del primer intento, y los reintentos lo repiten: el servidor
   * devuelve el resultado guardado en vez de decidir otra vez. Con `{nonce}`, las preguntas sin nonce propio
   * usan ese valor (con una sola pregunta tal cual; con varias, `${nonce}:${id}`).
   * @param {string} estado
   * @param {Pregunta[]} preguntas
   * @param {{nonce?: string}} [opts]
   * @returns {Promise<Resultado[]>}
   */
  async decidir(estado, preguntas, { nonce } = {}) {
    validar(estado, preguntas, this.limites);
    const qs = preguntas.map((q) => {
      if (q.nonce !== undefined && q.nonce !== "") return q; // "" cuenta como ausente: el servidor no guardaría nada
      const n = nonce === undefined || nonce === "" ? globalThis.crypto.randomUUID() : preguntas.length === 1 ? nonce : `${nonce}:${q.id}`;
      return { ...q, nonce: n };
    });
    validar(estado, qs, this.limites); // el nonce derivado también cuenta en bytes
    const resp = await this._pedir("/v1/decide", { state: estado ?? "", questions: qs });
    const res = resp?.results;
    if (!Array.isArray(res) || res.length !== qs.length || res.some((r, i) => r?.id !== qs[i].id)) {
      throw new ErrorChispa({ codigo: "bad_response", mensaje: "la respuesta no trae las preguntas en orden", status: 200 });
    }
    return res;
  }

  /** `true` si /healthz contesta `{status:"ok"}`; `false` ante cualquier fallo (no lanza). Sin reintentos. */
  async salud() {
    try {
      const r = await this._intento("/healthz", undefined);
      return r?.status === "ok";
    } catch {
      return false;
    }
  }

  async _pedir(ruta, cuerpo) {
    const json = JSON.stringify(cuerpo); // se serializa una vez: todos los intentos envían los mismos bytes y el mismo nonce
    const n = bytes(json);
    if (n > this.limites.maxCuerpo) {
      throw new ErrorChispa({ codigo: "request_too_large", mensaje: `cuerpo: ${n} bytes, máximo ${this.limites.maxCuerpo}`, status: 0 });
    }
    let ultimo;
    for (let i = 0; i <= this.reintentos; i++) {
      // backoff exponencial con jitter (×0,5–1); si el servidor pidió Retry-After, se espera al menos eso
      if (i) await this._dormir(Math.max(this.esperaMs * 2 ** (i - 1) * (0.5 + Math.random() / 2), ultimo?.retryAfterMs ?? 0));
      try {
        return await this._intento(ruta, json);
      } catch (e) {
        if (!(e instanceof ErrorChispa) || !reintentable(e)) throw e;
        ultimo = e;
      }
    }
    throw ultimo;
  }

  async _intento(ruta, json) {
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), this.timeoutMs);
    try {
      const init = { signal: ctl.signal, method: json === undefined ? "GET" : "POST" };
      if (json !== undefined) Object.assign(init, { body: json, headers: { "Content-Type": "application/json" } });
      let r, texto;
      try {
        r = await this._fetch(this.url + ruta, init);
        texto = await r.text(); // el timeout cubre también la lectura del cuerpo
      } catch (e) {
        if (ctl.signal.aborted) {
          throw new ErrorChispa({ codigo: "timeout", mensaje: `${ruta}: sin respuesta en ${this.timeoutMs} ms`, cause: e });
        }
        throw new ErrorChispa({ codigo: "network_error", mensaje: `${this.url}${ruta}: ${e?.message ?? e}`, cause: e });
      }
      let datos;
      try {
        datos = texto === "" ? undefined : JSON.parse(texto);
      } catch {
        datos = undefined;
      }
      if (r.ok) {
        if (datos === undefined) {
          throw new ErrorChispa({ codigo: "bad_response", mensaje: `${ruta}: cuerpo no es JSON`, status: r.status });
        }
        return datos;
      }
      const e = datos?.error;
      throw new ErrorChispa({
        codigo: typeof e === "object" && e?.code ? e.code : `http_${r.status}`,
        mensaje: typeof e === "object" && e ? (e.message ?? "") : typeof e === "string" ? e : texto.slice(0, 200),
        idPregunta: typeof e === "object" ? e?.question_id : undefined,
        status: r.status,
        retryAfterMs: REINTENTABLES.has(r.status) ? retryAfterMs(r.headers) : undefined,
      });
    } finally {
      clearTimeout(t);
    }
  }
}

/**
 * Misma política que `cliente.py`: red, timeout propio, cuerpo 200 ilegible y 429/500/502/503. No se repite el `timeout` del
 * servidor (503 con código `timeout`) ni el 504: repetir gasta otra vez la cascada. Tampoco el resto de 4xx/5xx.
 */
function reintentable(e) {
  if (e.status === 504 || (e.status === 503 && e.codigo === "timeout")) return false;
  if (e.status > 0 && e.status !== 200) return REINTENTABLES.has(e.status);
  return e.codigo === "network_error" || e.codigo === "timeout" || e.codigo === "bad_response";
}
