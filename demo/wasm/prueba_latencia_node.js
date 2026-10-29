// Arnés de latencia sin navegador (mismo arnes.js que latencia.html).
// Uso: node prueba_latencia_node.js <modelo.chispa-l1> [--n 2000] [--calentamiento 200] [--lote 50] [--salida latencia-node.json]
//      node prueba_latencia_node.js --stub      (comprueba la lógica del arnés con un decisor falso; NO mide Chispa)
// Requiere chispa.wasm (construir.sh). Imprime un resumen y escribe el JSON (por defecto latencia-node.json).
"use strict";
const fs = require("fs");
const path = require("path");
const { correrArnes } = require("./arnes.js");

const arg = (k, def) => { const i = process.argv.indexOf("--" + k); return i < 0 ? def : process.argv[i + 1]; };
const stub = process.argv.includes("--stub");
const modelo = process.argv[2] && !process.argv[2].startsWith("--") ? process.argv[2] : null;
if (!stub && !modelo) { console.error("uso: node prueba_latencia_node.js <modelo.chispa-l1> [--n N] [--calentamiento N] [--lote N] [--salida f.json] | --stub"); process.exit(2); }

async function apiWasm() {
  Object.assign(globalThis, { require, fs, path, TextEncoder, TextDecoder });
  globalThis.performance ??= require("perf_hooks").performance;
  globalThis.crypto ??= require("crypto");
  require("./wasm_exec.js");
  const go = new Go();
  const { instance } = await WebAssembly.instantiate(fs.readFileSync(path.join(__dirname, "chispa.wasm")), go.importObject);
  go.run(instance);
  for (let i = 0; i < 300 && !globalThis.chispaListo; i++) await new Promise(r => setTimeout(r, 10));
  if (!globalThis.chispaListo) throw new Error("el wasm no arrancó");
  const d = fs.readFileSync(modelo);
  const c = cargar(new Uint8Array(d.buffer, d.byteOffset, d.length));
  if (!c.ok) throw new Error(c.error);
  return { decidir, decidirLote, memoriaGo, memoriaWasm: () => instance.exports.mem.buffer.byteLength, ahora: () => performance.now() };
}

function apiStub() {
  const r = t => ({ ok: true, answer: ["a", "b"][t.length % 2] });
  return {
    decidir: (t) => r(t),
    decidirLote: (ts) => ({ ok: true, n: JSON.parse(ts).length, answers: JSON.parse(ts).map(t => r(t).answer), total_us: 1 }),
    memoriaGo: () => ({ heap_alloc: 0, sys: 0, num_gc: 0 }),
    ahora: () => performance.now(),
  };
}

(async () => {
  const api = stub ? apiStub() : await apiWasm();
  const res = await correrArnes(api, {
    n: +arg("n", 2000), calentamiento: +arg("calentamiento", 200), lote: +arg("lote", 50),
  });
  if (stub) res.entorno.aviso = "STUB: no es una medida de Chispa";
  const f = arg("salida", stub ? "/tmp/latencia-stub.json" : path.join(__dirname, "latencia-node.json"));
  fs.writeFileSync(f, JSON.stringify(res, null, 1));
  const s = res.por_decision_us;
  console.log(`${stub ? "[STUB] " : ""}N ${s.n} · por decisión µs: p50 ${s.p50.toFixed(1)} p95 ${s.p95.toFixed(1)} p99 ${s.p99.toFixed(1)} · ${res.decisiones_por_s.toFixed(0)} dec/s`);
  if (res.por_lote) console.log(`por texto en lote de ${res.por_lote.tamano}: p50 ${res.por_lote.por_texto_us.p50.toFixed(1)} µs p99 ${res.por_lote.por_texto_us.p99.toFixed(1)} µs`);
  console.log(`memoria`, JSON.stringify(res.memoria.despues), `· ${res.entorno.user_agent}\nJSON: ${f}`);
  process.exit(0);
})().catch(e => { console.error(e); process.exit(1); });
