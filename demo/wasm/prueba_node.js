// Prueba sin navegador. Uso: node prueba_node.js <modelo.chispa-l1> [--latencia]   (requiere chispa.wasm: construir.sh)
//  1. CLI: ejecuta chispa.wasm con wasm_exec_node.js y la versión nativa (go run ./nativo) sobre 50 frases del sondeo;
//     exige la misma huella de embeddings (sha256 de los float32) y las mismas respuestas.
//  2. API: carga wasm_exec.js en este proceso y comprueba que cargar/decidir/huella (lo que usa la página)
//     dan lo mismo que la CLI.
// Con --latencia imprime p50/p99 de 16, 64 y 256 tokens × 200 repeticiones, medidos en node.
"use strict";
const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFileSync } = require("child_process");

const modelo = process.argv[2];
if (!modelo) { console.error("uso: node prueba_node.js <modelo.chispa-l1> [--latencia]"); process.exit(2); }
const sondeo = path.join(__dirname, "../../model/sondeo");
const preguntaRuta = path.join(__dirname, "ejemplo_pregunta.json");
const wasm = path.join(__dirname, "chispa.wasm");

function frases() {
  const leer = f => fs.readFileSync(path.join(sondeo, f), "utf8").trim().split("\n").map(l => JSON.parse(l).texto);
  const paso = (x, n) => Array.from({ length: n }, (_, i) => x[Math.floor(i * x.length / n)]);
  return [...paso(leer("whatsapp_comercio.jsonl"), 25), ...paso(leer("intencion.jsonl"), 25)];
}
const ejecutar = (cmd, args) => execFileSync(cmd, args, { cwd: __dirname, encoding: "utf8", maxBuffer: 1 << 26 });
const viaWasm = args => ejecutar("node", ["wasm_exec_node.js", "chispa.wasm", ...args]);

async function api(fr, pregunta) {
  Object.assign(globalThis, { require, fs, path, TextEncoder, TextDecoder });
  globalThis.performance ??= require("perf_hooks").performance;
  globalThis.crypto ??= require("crypto");
  require("./wasm_exec.js");
  const go = new Go();
  const { instance } = await WebAssembly.instantiate(fs.readFileSync(wasm), go.importObject);
  go.run(instance); // se queda a la escucha de las llamadas de JS
  for (let i = 0; i < 300 && !globalThis.chispaListo; i++) await new Promise(r => setTimeout(r, 10));
  if (!globalThis.chispaListo) throw new Error("el wasm no arrancó");
  const sin = decidir("hola", pregunta);
  if (sin.ok) throw new Error("decidir sin cargar debía fallar");
  const d = fs.readFileSync(modelo);
  const c = cargar(new Uint8Array(d.buffer, d.byteOffset, d.length));
  if (!c.ok) throw new Error(c.error);
  return { huella: huella(JSON.stringify(fr)).huella, respuestas: fr.map(t => decidir(t, pregunta).answer) };
}

async function main() {
  const fr = frases();
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "chispa-wasm-"));
  const frasesRuta = path.join(tmp, "frases.json");
  fs.writeFileSync(frasesRuta, JSON.stringify(fr));
  const args = ["huella", modelo, frasesRuta, preguntaRuta];
  const nat = JSON.parse(ejecutar("go", ["run", "./nativo", ...args]));
  const was = JSON.parse(viaWasm(args));
  const viaApi = await api(fr, fs.readFileSync(preguntaRuta, "utf8"));
  let malos = 0;
  const igual = (n, x) => {
    if (x.huella !== nat.huella) { console.error(`${n}: huella ${x.huella} ≠ nativo ${nat.huella}`); malos++; }
    x.respuestas.forEach((r, i) => { if (r !== nat.respuestas[i] || !r) { console.error(`${n}: frase ${i} «${r}» ≠ «${nat.respuestas[i]}»`); malos++; } });
  };
  igual("wasm-cli", was);
  igual("wasm-api", viaApi);
  console.log(`frases ${fr.length} · huella ${nat.huella} · coinciden wasm-cli ${was.respuestas.filter((r, i) => r === nat.respuestas[i]).length}/${fr.length}, wasm-api ${viaApi.respuestas.filter((r, i) => r === nat.respuestas[i]).length}/${fr.length}`);
  if (process.argv.includes("--latencia")) {
    for (const l of viaWasm(["latencia", modelo, preguntaRuta]).trim().split("\n").map(JSON.parse)) {
      console.log(`latencia node ${l.tokens} tokens (reales ${l.tokens_reales}): p50 ${l.p50_us.toFixed(0)} µs · p99 ${l.p99_us.toFixed(0)} µs · ${l.reps} reps`);
    }
  }
  fs.rmSync(tmp, { recursive: true });
  if (malos) { console.error("FALLO"); process.exit(1); }
  console.log("OK");
  process.exit(0);
}
main().catch(e => { console.error(e); process.exit(1); });
