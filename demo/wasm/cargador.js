// Carga chispa.wasm y el modelo L1 de la misma carpeta (sin red externa) y devuelve el API para el arnés y la UI.
async function iniciarChispa(modelo) {
  const go = new Go();
  const [wasm, datos] = await Promise.all([
    WebAssembly.instantiateStreaming(fetch("chispa.wasm"), go.importObject),
    fetch(modelo).then(r => { if (!r.ok) throw new Error(modelo + " no existe: genéralo (ver README)"); return r.arrayBuffer(); }),
  ]);
  go.run(wasm.instance);
  const c = cargar(new Uint8Array(datos));
  if (!c.ok) throw new Error(c.error);
  return {
    info: c,
    decidir, decidirLote, memoriaGo,
    memoriaWasm: () => wasm.instance.exports.mem.buffer.byteLength,
    ahora: () => performance.now(),
  };
}
