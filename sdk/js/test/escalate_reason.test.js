import { test } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { readFileSync } from "node:fs";
import { ChispaCliente } from "../src/index.js";

const MOTIVOS = ["sin_opinion", "score_ids_no_validos", "baja_confianza", "incompleta"];

test("index.d.ts declara escalate_reason con todos sus valores y la nota de ids 1..K", () => {
  const d = readFileSync(new URL("../src/index.d.ts", import.meta.url), "utf8");
  const campo = d.match(/escalate_reason\?:([^;]+);/);
  assert.ok(campo, "falta escalate_reason?");
  for (const m of MOTIVOS) assert.ok(campo[1].includes(`"${m}"`), m);
  assert.match(d, /ids deben ser "1".."K"/);
});

test("escalate_reason llega al cliente tal como lo manda el servidor", async () => {
  const s = http.createServer((req, res) => {
    let b = "";
    req.on("data", (c) => (b += c));
    req.on("end", () => {
      const q = JSON.parse(b).questions[0];
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ results: [{ id: q.id, kind: q.kind, answer: "", probs: {}, layer: "escalar", escalate: true, escalate_reason: "score_ids_no_validos", ms: 0.1 }] }));
    });
  });
  await new Promise((r) => s.listen(0, "127.0.0.1", r));
  try {
    const c = new ChispaCliente({ url: `http://127.0.0.1:${s.address().port}`, esperaMs: 1 });
    const [r] = await c.decidir("x", [{ id: "q", question: "¿?", kind: "score", options: [{ id: "a", description: "a" }, { id: "b", description: "b" }] }]);
    assert.equal(r.escalate, true);
    assert.equal(r.escalate_reason, "score_ids_no_validos");
  } finally {
    s.close();
  }
});
