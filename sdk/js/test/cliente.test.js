import { test, afterEach } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { ChispaCliente, ErrorChispa, bytes } from "../src/index.js";

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

test("500 no se reintenta", async () => {
  const { url, vistas } = await falso((req, c, res) => json(res, 500, { error: { code: "x", message: "y" } }));
  await assert.rejects(cliente(url).decidir("x", [ferreteria]), { status: 500 });
  assert.equal(vistas.length, 1);
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
