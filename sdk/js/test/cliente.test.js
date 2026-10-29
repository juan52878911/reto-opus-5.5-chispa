import { test, afterEach } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { readFileSync } from "node:fs";
import { ChispaCliente, ErrorChispa, bytes } from "../src/index.js";
import { LIMITES, validar } from "../src/limites.js";

const servidores = [];
afterEach(async () => {
  for (const s of servidores.splice(0)) {
    s.closeAllConnections?.();
    await new Promise((r) => s.close(r));
  }
});

/** Servidor falso: `manejador(req, cuerpoJson, res, n)` con n = nº de petición a /v1/decide (desde 1). */
async function falso(manejador) {
  const vistas = [];
  const s = http.createServer((req, res) => {
    let b = "";
    req.on("data", (c) => (b += c));
    req.on("end", () => {
      if (req.url === "/healthz") return json(res, 200, { status: "ok" });
      const cuerpo = b ? JSON.parse(b) : undefined;
      vistas.push({ metodo: req.method, url: req.url, cuerpo, tipo: req.headers["content-type"] });
      manejador(req, cuerpo, res, vistas.length);
    });
  });
  servidores.push(s);
  await new Promise((r) => s.listen(0, "127.0.0.1", r));
  return { url: `http://127.0.0.1:${s.address().port}`, vistas };
}
const json = (res, status, o) => {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(o));
};
const eco = (probs = {}) => (req, c, res) =>
  json(res, 200, {
    results: c.questions.map((q) => ({
      id: q.id, kind: q.kind, answer: Object.keys(probs)[0] ?? "", probs, layer: "L1", escalate: false, ms: 0.1, nonce: q.nonce,
    })),
  });
const cliente = (url, o = {}) => new ChispaCliente({ url, esperaMs: 1, ...o });

// ferretería de docs/02-inicio-rapido.md, zero-shot
const ferreteria = {
  id: "q1",
  question: "¿Qué necesita la persona que escribe a la ferretería?",
  kind: "choice",
  options: [
    { id: "cotizacion", description: "pide precio o disponibilidad de un producto, o una cotización de materiales" },
    { id: "pedido", description: "quiere comprar y recibir productos, o pregunta por el estado de un pedido ya hecho" },
    { id: "garantia", description: "reclama por una herramienta defectuosa, un cambio o una devolución" },
  ],
};

test("choice: envía el esquema y devuelve el resultado", async () => {
  const { url, vistas } = await falso(eco({ cotizacion: 0.8, pedido: 0.1, garantia: 0.1 }));
  const [r] = await cliente(url).decidir("¿cuánto vale el bulto de cemento?", [ferreteria]);
  assert.equal(r.answer, "cotizacion");
  assert.equal(r.layer, "L1");
  assert.equal(vistas[0].metodo, "POST");
  assert.equal(vistas[0].url, "/v1/decide");
  assert.equal(vistas[0].tipo, "application/json");
  assert.equal(vistas[0].cuerpo.state, "¿cuánto vale el bulto de cemento?");
  assert.equal(vistas[0].cuerpo.questions[0].options[0].description.startsWith("pide precio"), true);
});

test("noul y score en la misma petición, en orden, con nonce propio respetado", async () => {
  const { url, vistas } = await falso(eco());
  const rs = await cliente(url).decidir("llegó roto", [
    { id: "n1", question: "¿Hay una queja?", kind: "noul" },
    { id: "s1", question: "¿Qué tan urgente?", kind: "score", options: [{ id: "1" }, { id: "2" }, { id: "3" }], nonce: "abc-1" },
  ]);
  assert.deepEqual(rs.map((r) => r.id), ["n1", "s1"]);
  assert.equal(vistas[0].cuerpo.questions[1].nonce, "abc-1");
  assert.match(vistas[0].cuerpo.questions[0].nonce, /^[0-9a-f-]{36}$/);
});

test("multi: envía las opciones y devuelve answers y una probabilidad por opción", async () => {
  const srv = await falso((req, c, res) =>
    json(res, 200, {
      results: c.questions.map((q) => ({
        id: q.id, kind: q.kind, answer: "cobro", answers: ["cobro", "atencion"],
        probs: { cobro: 0.93, atencion: 0.81, fraude: 0.07 }, layer: "L1", escalate: false, ms: 0.5,
      })),
    }));
  const [r] = await cliente(srv.url).decidir("me cobraron dos veces y nadie contesta", [
    { id: "temas", question: "¿Qué temas toca?", kind: "multi", options: [{ id: "cobro", description: "un cobro" }, { id: "atencion" }, { id: "fraude" }] },
  ]);
  assert.equal(srv.vistas[0].cuerpo.questions[0].kind, "multi");
  assert.deepEqual(r.answers, ["cobro", "atencion"]);
  assert.equal(r.answer, "cobro");
  assert.equal(Object.keys(r.probs).length, 3);
  // multi no suma 1: cada opción tiene su propia probabilidad
  assert.ok(Object.values(r.probs).reduce((a, b) => a + b, 0) > 1);
});

test("{nonce}: una pregunta lo usa tal cual; varias, nonce:id", async () => {
  const { url, vistas } = await falso(eco());
  const c = cliente(url);
  await c.decidir("x", [ferreteria], { nonce: "pedido-7" });
  await c.decidir("x", [ferreteria, { id: "n", question: "¿Queja?", kind: "noul" }], { nonce: "pedido-8" });
  assert.equal(vistas[0].cuerpo.questions[0].nonce, "pedido-7");
  assert.deepEqual(vistas[1].cuerpo.questions.map((q) => q.nonce), ["pedido-8:q1", "pedido-8:n"]);
});

test("error tipado 400: codigo, mensaje, idPregunta y status; sin reintento", async () => {
  const { url, vistas } = await falso((req, c, res) =>
    json(res, 400, { error: { code: "invalid_options", message: "questions[0].options: no", question_id: "q1" } }));
  await assert.rejects(cliente(url).decidir("x", [ferreteria]), (e) => {
    assert.ok(e instanceof ErrorChispa);
    assert.equal(e.codigo, "invalid_options");
    assert.equal(e.mensaje, "questions[0].options: no");
    assert.equal(e.idPregunta, "q1");
    assert.equal(e.status, 400);
    return true;
  });
  assert.equal(vistas.length, 1);
});

test("413 y error con formato no tipado", async () => {
  const { url } = await falso((req, c, res) => json(res, 413, { error: { code: "request_too_large", message: "grande" } }));
  await assert.rejects(cliente(url).decidir("x", [ferreteria]), { codigo: "request_too_large", status: 413 });
  const otro = await falso((req, c, res) => json(res, 400, { error: "texto viejo" }));
  await assert.rejects(cliente(otro.url).decidir("x", [ferreteria]), { codigo: "http_400", mensaje: "texto viejo", status: 400 });
});

test("503 se reintenta con el mismo nonce y los mismos bytes", async () => {
  const { url, vistas } = await falso((req, c, res, n) =>
    n < 3 ? json(res, 503, { error: { code: "not_found", message: "ocupado" } }) : eco({ a: 1 })(req, c, res));
  const [r] = await cliente(url, { reintentos: 2 }).decidir("x", [ferreteria]);
  assert.equal(r.answer, "a");
  assert.equal(vistas.length, 3);
  const nonces = vistas.map((v) => v.cuerpo.questions[0].nonce);
  assert.equal(new Set(nonces).size, 1);
  assert.ok(nonces[0]);
});

test("503 sin recuperación: tras agotar los reintentos lanza el último error", async () => {
  const { url, vistas } = await falso((req, c, res) => json(res, 503, { error: { code: "not_found", message: "no" } }));
  await assert.rejects(cliente(url, { reintentos: 1 }).decidir("x", [ferreteria]), { status: 503 });
  assert.equal(vistas.length, 2);
});

test("503 persistente: se reintenta y al agotar lanza el último error", async () => {
  const { url, vistas } = await falso((req, c, res) => json(res, 503, { error: { code: "x", message: "y" } }));
  await assert.rejects(cliente(url).decidir("x", [ferreteria]), { status: 503 });
  assert.equal(vistas.length, 4);
});

test("corte de red a mitad: se reintenta con el mismo nonce", async () => {
  const { url, vistas } = await falso((req, c, res, n) => (n === 1 ? req.socket.destroy() : eco({ a: 1 })(req, c, res)));
  const [r] = await cliente(url).decidir("x", [ferreteria]);
  assert.equal(r.answer, "a");
  assert.equal(vistas.length, 2);
  assert.equal(vistas[0].cuerpo.questions[0].nonce, vistas[1].cuerpo.questions[0].nonce);
});

test("servidor caído: network_error tras los reintentos", async () => {
  const { url } = await falso(eco());
  await afterEachCerrar();
  await assert.rejects(cliente(url, { reintentos: 1 }).decidir("x", [ferreteria]), { codigo: "network_error", status: 0 });
});
async function afterEachCerrar() {
  for (const s of servidores.splice(0)) await new Promise((r) => s.close(r));
}

test("timeout: codigo timeout; reintenta y el segundo intento responde", async () => {
  const { url, vistas } = await falso((req, c, res, n) => {
    if (n === 1) return; // no contesta; el cliente aborta
    eco({ a: 1 })(req, c, res);
  });
  const [r] = await cliente(url, { timeoutMs: 50 }).decidir("x", [ferreteria]);
  assert.equal(r.answer, "a");
  assert.equal(vistas.length, 2);
  assert.equal(vistas[0].cuerpo.questions[0].nonce, vistas[1].cuerpo.questions[0].nonce);
});

test("timeout agotado: ErrorChispa timeout", async () => {
  const { url, vistas } = await falso(() => {});
  const t0 = Date.now();
  await assert.rejects(cliente(url, { timeoutMs: 30, reintentos: 1 }).decidir("x", [ferreteria]), { codigo: "timeout", status: 0 });
  assert.equal(vistas.length, 2);
  assert.ok(Date.now() - t0 < 2000);
});

test("reintentos: 0 hace un solo intento", async () => {
  const { url, vistas } = await falso((req, c, res) => json(res, 503, { error: { code: "a", message: "b" } }));
  await assert.rejects(cliente(url, { reintentos: 0 }).decidir("x", [ferreteria]), { status: 503 });
  assert.equal(vistas.length, 1);
});

test("respuesta fuera de contrato: bad_response, sin reintento", async () => {
  const { url, vistas } = await falso((req, c, res) => json(res, 200, { results: [] }));
  await assert.rejects(cliente(url).decidir("x", [ferreteria]), { codigo: "bad_response" });
  assert.equal(vistas.length, 1);
});

test("salud: true con ok, false si cae o responde mal", async () => {
  const { url } = await falso(eco());
  assert.equal(await cliente(url).salud(), true);
  await afterEachCerrar();
  assert.equal(await cliente(url).salud(), false);
});

test("salud: false con 500", async () => {
  const s = http.createServer((q, r) => json(r, 500, { error: "no" }));
  servidores.push(s);
  await new Promise((r) => s.listen(0, "127.0.0.1", r));
  assert.equal(await cliente(`http://127.0.0.1:${s.address().port}/`).salud(), false);
});

// --- validación local: no toca la red ---
const sinRed = () => cliente("http://127.0.0.1:1", { fetch: () => assert.fail("no debería llamar al servidor") });
const q = (extra) => ({ id: "q", question: "¿Tema?", kind: "choice", options: [{ id: "a" }, { id: "b" }], ...extra });

test("límites en bytes UTF-8: 'ñ' ocupa 2 bytes", async () => {
  assert.equal(bytes("ñ"), 2);
  // 129 'ñ' = 129 caracteres pero 258 bytes > 256
  await assert.rejects(sinRed().decidir("x", [q({ id: "ñ".repeat(129) })]), { codigo: "field_too_long", status: 0 });
  // 128 'ñ' = 256 bytes: cabe (la validación pasa y llega al fetch)
  let llamado = false;
  const c = cliente("http://x", { fetch: async () => { llamado = true; throw new Error("stop"); }, reintentos: 0 });
  await assert.rejects(c.decidir("x", [q({ id: "ñ".repeat(128) })]), { codigo: "network_error" });
  assert.ok(llamado);
  await assert.rejects(sinRed().decidir("x", [q({ question: "é".repeat(2049) })]), { codigo: "field_too_long", idPregunta: "q" });
  await assert.rejects(sinRed().decidir("x".repeat(262145), [q()]), { codigo: "state_too_long" });
  await assert.rejects(sinRed().decidir("ñ".repeat(131073), [q()]), { codigo: "state_too_long" });
  await assert.rejects(sinRed().decidir("x", [q({ nonce: "ñ".repeat(129) })]), { codigo: "field_too_long" });
  await assert.rejects(sinRed().decidir("x", [q({ options: [{ id: "a", description: "é".repeat(2049) }, { id: "b" }] })]), { codigo: "field_too_long" });
});

test("validación local: mismos códigos que el servidor", async () => {
  const caso = (preguntas, codigo, extra = {}) => assert.rejects(sinRed().decidir("x", preguntas), { codigo, ...extra });
  await caso([], "empty_questions");
  await caso(Array.from({ length: 257 }, (_, i) => q({ id: `q${i}` })), "too_many_questions");
  await caso([q({ id: "" })], "missing_id");
  await caso([q({ question: "" })], "missing_question");
  await caso([q({ kind: undefined })], "missing_kind");
  await caso([q({ kind: "raro" })], "invalid_kind", { idPregunta: "q" });
  await caso([q({ options: [{ id: "a" }] })], "too_few_options");
  await caso([q({ kind: "score", options: undefined })], "too_few_options");
  await caso([q({ options: Array.from({ length: 257 }, (_, i) => ({ id: `o${i}` })) })], "too_many_options");
  await caso([q({ options: [{ id: "" }, { id: "b" }] })], "missing_option_id");
  await caso([q({ options: [{ id: "a" }, { id: "a" }] })], "duplicate_option_id");
  await caso([q(), q()], "duplicate_question_id");
  await caso([{ id: "n", question: "¿?", kind: "noul", options: [{ id: "tal" }] }], "invalid_options");
  // multi: como choice (≥ 2 opciones con id único)
  await caso([q({ kind: "multi", options: [{ id: "a" }] })], "too_few_options");
  await caso([q({ kind: "multi", options: undefined })], "too_few_options");
  await caso([q({ kind: "multi", options: [{ id: "a" }, { id: "a" }] })], "duplicate_option_id");
});

test("separadores U+001D–U+001F: invalid_characters en local, sin red", async () => {
  const caso = (preguntas, extra = {}) => assert.rejects(sinRed().decidir("x", preguntas), { codigo: "invalid_characters", status: 0, ...extra });
  for (const c of ["\x1d", "\x1e", "\x1f"]) {
    await caso([q({ question: `a${c}b` })], { idPregunta: "q" });
    await caso([q({ options: [{ id: `a${c}` }, { id: "b" }] })]);
    await caso([q({ options: [{ id: "a", description: `d${c}` }, { id: "b" }] })]);
  }
  // el límite de longitud va antes, como en el servidor
  await assert.rejects(sinRed().decidir("x", [q({ question: "\x1f".repeat(4097) })]), { codigo: "field_too_long" });
  // otros caracteres de control sí pasan
  const c = cliente("http://x", { fetch: async () => { throw new Error("stop"); }, reintentos: 0 });
  await assert.rejects(c.decidir("x", [q({ question: "a\x1cb\n" })]), { codigo: "network_error" });
});

test("noul con false/true y sin opciones es válido", async () => {
  const { url } = await falso(eco());
  const c = cliente(url);
  await c.decidir("x", [{ id: "n", question: "¿Queja?", kind: "noul" }]);
  await c.decidir("x", [{ id: "n", question: "¿Queja?", kind: "noul", options: [{ id: "false" }, { id: "true" }] }]);
});

test("limites configurables", async () => {
  const c = cliente("http://x", { limites: { maxPreguntas: 1 }, fetch: () => assert.fail("no") });
  await assert.rejects(c.decidir("x", [q({ id: "a" }), q({ id: "b" })]), { codigo: "too_many_questions" });
});

const conEsperas = (url, o = {}) => {
  const esperas = [];
  return { esperas, c: cliente(url, { dormir: async (ms) => void esperas.push(ms), ...o }) };
};
const ocupado = (cab, code = "overloaded") => (req, c, res) => {
  res.writeHead(503, { "Content-Type": "application/json", ...cab });
  res.end(JSON.stringify({ error: { code, message: "ocupado" } }));
};

test("503 con Retry-After: espera al menos ese tiempo y reintenta con el mismo nonce", async () => {
  const { url, vistas } = await falso((req, c, res, n) => (n === 1 ? ocupado({ "Retry-After": "3" })(req, c, res) : eco({ a: 1 })(req, c, res)));
  const { c, esperas } = conEsperas(url);
  const [r] = await c.decidir("x", [ferreteria]);
  assert.equal(r.answer, "a");
  assert.deepEqual(esperas, [3000]);
  assert.equal(vistas[0].cuerpo.questions[0].nonce, vistas[1].cuerpo.questions[0].nonce);
});

test("503 con Retry-After enorme: se topa a 30 s", async () => {
  const { url } = await falso((req, c, res, n) => (n === 1 ? ocupado({ "Retry-After": "999" })(req, c, res) : eco({ a: 1 })(req, c, res)));
  const { c, esperas } = conEsperas(url);
  await c.decidir("x", [ferreteria]);
  assert.deepEqual(esperas, [30000]);
});

test("503 sin Retry-After (o con fecha HTTP): solo backoff con jitter", async () => {
  for (const cab of [{}, { "Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT" }]) {
    const { url } = await falso((req, c, res, n) => (n === 1 ? ocupado(cab)(req, c, res) : eco({ a: 1 })(req, c, res)));
    const { c, esperas } = conEsperas(url, { esperaMs: 100 });
    await c.decidir("x", [ferreteria]);
    assert.equal(esperas.length, 1);
    assert.ok(esperas[0] >= 50 && esperas[0] <= 100, String(esperas[0]));
  }
});

test("timeout del servidor (503 código timeout con Retry-After) no se reintenta", async () => {
  const { url, vistas } = await falso(ocupado({ "Retry-After": "5" }, "timeout"));
  const { c, esperas } = conEsperas(url);
  await assert.rejects(c.decidir("x", [ferreteria]), { codigo: "timeout", status: 503 });
  assert.equal(vistas.length, 1);
  assert.deepEqual(esperas, []);
});

test("504 no se reintenta", async () => {
  const { url, vistas } = await falso((req, c, res) => json(res, 504, { error: { code: "gateway_timeout", message: "x" } }));
  await assert.rejects(cliente(url).decidir("x", [ferreteria]), { status: 504 });
  assert.equal(vistas.length, 1);
});

test("error de red: reintenta con el mismo nonce y backoff", async () => {
  const { url, vistas } = await falso((req, c, res, n) => (n < 3 ? req.socket.destroy() : eco({ a: 1 })(req, c, res)));
  const { c, esperas } = conEsperas(url, { esperaMs: 100 });
  await c.decidir("x", [ferreteria]);
  assert.equal(vistas.length, 3);
  assert.equal(new Set(vistas.map((v) => v.cuerpo.questions[0].nonce)).size, 1);
  assert.equal(esperas.length, 2);
  assert.ok(esperas[1] >= 100 && esperas[1] <= 200);
});

test("noul con una sola opción se rechaza en local con invalid_options", async () => {
  const f = await falso((_q, _b, res) => json(res, 200, { results: [] }));
  const c = new ChispaCliente({ url: f.url });
  for (const options of [[{ id: "true" }], [{ id: "true" }, { id: "true" }], [{ id: "false" }, { id: "true" }, { id: "x" }]]) {
    await assert.rejects(
      c.decidir("t", [{ id: "q", question: "?", kind: "noul", options }]),
      (e) => e instanceof ErrorChispa && e.codigo === "invalid_options" && e.status === 0,
    );
  }
  assert.equal(f.vistas.length, 0);
});

test("noul acepta 0 opciones o {true,false} en cualquier orden", async () => {
  const f = await falso((_q, b, res) => json(res, 200, { results: b.questions.map((q) => ({ id: q.id })) }));
  const c = new ChispaCliente({ url: f.url });
  await c.decidir("t", [
    { id: "a", question: "?", kind: "noul" },
    { id: "b", question: "?", kind: "noul", options: [{ id: "true" }, { id: "false" }] },
  ]);
  assert.equal(f.vistas.length, 1);
});

test("cuerpo mayor que maxCuerpo (1 MiB por defecto) falla en local con request_too_large", async () => {
  const f = await falso((_q, _b, res) => json(res, 200, { results: [] }));
  const c = new ChispaCliente({ url: f.url });
  const options = Array.from({ length: 256 }, (_, i) => ({ id: `o${i}`, description: "x".repeat(4096) }));
  const qs = Array.from({ length: 2 }, (_, i) => ({ id: `q${i}`, question: "?", kind: "choice", options }));
  await assert.rejects(c.decidir("t", qs), (e) => e.codigo === "request_too_large" && e.status === 0);
  assert.equal(f.vistas.length, 0);
  const c2 = new ChispaCliente({ url: f.url, limites: { maxCuerpo: 100 } });
  await assert.rejects(c2.decidir("t", [{ id: "q", question: "x".repeat(200), kind: "noul" }]), (e) => e.codigo === "request_too_large");
});

test("R5-1: timeout por defecto (35 s) mayor que el -timeout del servidor (30 s)", () => {
  assert.ok(new ChispaCliente().timeoutMs > 30000);
  assert.equal(new ChispaCliente().reintentos, 3);
});

test("R5-3: 'timeout' es un CodigoServidor en index.d.ts", async () => {
  const { readFile } = await import("node:fs/promises");
  const d = await readFile(new URL("../src/index.d.ts", import.meta.url), "utf8");
  const bloque = d.slice(d.indexOf("type CodigoServidor"), d.indexOf("type CodigoCliente"));
  assert.match(bloque, /"timeout"/);
});

test("R5-6: 401, 429, 500 y 502 no se reintentan (docs/05-sdks.md); el 503 sí", async () => {
  for (const st of [401, 429, 500, 502]) {
    const { url, vistas } = await falso((req, c, res) => json(res, st, { error: { code: "x", message: "y" } }));
    const { c, esperas } = conEsperas(url);
    await assert.rejects(c.decidir("x", [ferreteria]), { status: st });
    assert.equal(vistas.length, 1, `status ${st}`);
    assert.deepEqual(esperas, []);
  }
  const { url, vistas } = await falso((req, c, res, n) => (n === 1 ? json(res, 503, { error: { code: "x", message: "y" } }) : eco({ a: 1 })(req, c, res)));
  await conEsperas(url).c.decidir("x", [ferreteria]);
  assert.equal(vistas.length, 2);
});

test("apiKey: Authorization Bearer en /v1/decide (salud no la envía); sin apiKey no hay cabecera", async () => {
  const auths = [];
  const { url } = await falso((req, c, res) => { auths.push([req.url, req.headers.authorization]); return eco({ a: 1 })(req, c, res); });
  const con = new ChispaCliente({ url, apiKey: "s3creto" });
  await con.decidir("x", [ferreteria]);
  assert.equal(await con.salud(), true);
  await new ChispaCliente({ url }).decidir("x", [ferreteria]);
  assert.deepEqual(auths, [["/v1/decide", "Bearer s3creto"], ["/v1/decide", undefined]]);
});

test("apiKey con salto final, espacios o control: se rechaza al construir, sin filtrar la clave", async () => {
  for (const k of ["s3creto\n", " s3creto", "s3 creto", "s3creto\r\n", "s3\u0000creto", "clavé"]) {
    assert.throws(() => new ChispaCliente({ apiKey: k }), (e) => e instanceof TypeError && !e.message.includes("s3creto"), JSON.stringify(k));
  }
  assert.doesNotThrow(() => new ChispaCliente({ apiKey: "s3creto" }));
  assert.doesNotThrow(() => new ChispaCliente({ apiKey: "" }));
});

test("401: ErrorChispa unauthorized, un solo intento", async () => {
  const { url, vistas } = await falso((req, c, res) => json(res, 401, { error: { code: "unauthorized", message: "clave de API ausente o incorrecta" } }));
  await assert.rejects(conEsperas(url).c.decidir("x", [ferreteria]), { status: 401, codigo: "unauthorized" });
  assert.equal(vistas.length, 1);
});

test("429 rate_limited: no se reintenta y retryAfterMs trae la espera (tope 30 s)", async () => {
  for (const [ra, ms] of [["7", 7000], ["999", 30000], [undefined, undefined]]) {
    const { url, vistas } = await falso((req, c, res) => {
      res.writeHead(429, { "Content-Type": "application/json", ...(ra ? { "Retry-After": ra } : {}) });
      res.end(JSON.stringify({ error: { code: "rate_limited", message: "x" } }));
    });
    const { c, esperas } = conEsperas(url);
    await assert.rejects(c.decidir("x", [ferreteria]), { status: 429, codigo: "rate_limited", retryAfterMs: ms });
    assert.equal(vistas.length, 1);
    assert.deepEqual(esperas, []);
  }
});

test("R5-6: 200 con cuerpo no JSON se reintenta como en Python", async () => {
  const { url, vistas } = await falso((req, c, res, n) => {
    if (n === 1) { res.writeHead(200); return res.end("<html>"); }
    eco({ a: 1 })(req, c, res);
  });
  await conEsperas(url).c.decidir("x", [ferreteria]);
  assert.equal(vistas.length, 2);
});

test("R5-9: nonce vacío se trata como ausente (pregunta y opción)", async () => {
  const { url, vistas } = await falso(eco({ a: 1 }));
  await cliente(url).decidir("x", [{ ...ferreteria, nonce: "" }]);
  await cliente(url).decidir("x", [ferreteria], { nonce: "" });
  for (const v of vistas) assert.match(v.cuerpo.questions[0].nonce, /^[0-9a-f-]{36}$/);
});

/** Propiedades de un esquema de openapi.yaml (sin dependencia de YAML: lee las claves bajo `properties:` por sangría). */
function propiedadesOpenapi(esquema) {
  const l = readFileSync(new URL("../../../server/api/openapi.yaml", import.meta.url), "utf8").split("\n");
  const i = l.findIndex((x) => x === `    ${esquema}:`);
  assert.ok(i >= 0, `no hay ${esquema} en openapi.yaml`);
  const p = l.findIndex((x, j) => j > i && x === "      properties:");
  const claves = [];
  for (let j = p + 1; j < l.length && /^(        \S|\s*$|          )/.test(l[j]); j++) {
    const m = /^        (\w+):\s*$/.exec(l[j]);
    if (m) claves.push(m[1]);
  }
  return claves;
}

test("el cuerpo solo lleva campos de openapi.yaml (el servidor es estricto)", async () => {
  const f = await falso((req, cuerpo, res) => json(res, 200, { results: cuerpo.questions.map((q) => ({ id: q.id })) }));
  const c = new ChispaCliente({ url: f.url });
  const q = { id: "a", question: "¿Sí?", kind: "choice", extra: 1, options: [{ id: "x", description: "d", peso: 2 }, { id: "y", otro: true }], nonce: "n1" };
  await c.decidir("t", [q, { id: "b", question: "¿No?", kind: "noul", basura: "z" }]);
  const cuerpo = f.vistas[0].cuerpo;
  assert.deepEqual(Object.keys(cuerpo).sort(), ["questions", "state"].sort());
  const okQ = propiedadesOpenapi("Question");
  const okO = propiedadesOpenapi("Option");
  assert.ok(okQ.includes("nonce") && okO.includes("description"));
  for (const x of cuerpo.questions) for (const k of Object.keys(x)) assert.ok(okQ.includes(k), `campo ${k} fuera del contrato`);
  for (const o of cuerpo.questions[0].options) for (const k of Object.keys(o)) assert.ok(okO.includes(k), `opción: campo ${k} fuera del contrato`);
  assert.equal(cuerpo.questions[0].nonce, "n1");
  assert.deepEqual(cuerpo.questions[0].options[1], { id: "y" });
});

test("orden de validación como el servidor: nonce largo antes que kind vacío", () => {
  const q = { id: "q1", question: "x", kind: "", nonce: "n".repeat(LIMITES.maxId + 1) };
  assert.throws(() => validar("", [q]), (e) => e instanceof ErrorChispa && e.codigo === "field_too_long");
});
