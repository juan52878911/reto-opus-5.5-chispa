// Arnés de latencia de Chispa. Sin dependencias ni red; lo usan latencia.html (navegador) y prueba_latencia_node.js.
// correrArnes(api, opc) mide N decisiones una a una (con performance.now, incluido el cruce JS→wasm) y por lotes
// (cronometrados dentro del wasm), tras un calentamiento. api = { decidir, decidirLote, memoriaGo, memoriaWasm, ahora }.
(function (raiz) {
  "use strict";

  const PREGUNTA_FERRETERIA = {
    question: "¿Qué necesita la persona que escribe a la ferretería?",
    kind: "choice",
    options: [
      { id: "cotizacion", description: "pide precio o disponibilidad de un producto, o una cotización de materiales" },
      { id: "pedido", description: "quiere comprar y recibir productos, o pregunta por el estado de un pedido ya hecho" },
      { id: "garantia", description: "reclama por una herramienta defectuosa, un cambio o una devolución" },
      { id: "asesoria", description: "pide ayuda técnica para elegir o usar un material o una herramienta" },
      { id: "factura", description: "pide una factura, un RUT o corregir datos de facturación" },
    ],
  };

  // Generador determinista (mulberry32): mismos textos en cada corrida y en cada navegador.
  function azar(semilla) {
    let a = semilla >>> 0;
    return () => {
      a = (a + 0x6d2b79f5) >>> 0;
      let t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  const SALUDOS = ["Buenas", "Hola", "Buenos días", "Buenas tardes", "Hola, qué tal", "Una pregunta", "Mire,"];
  const CUERPOS = [
    "¿cuánto vale el bulto de cemento gris de 50 kg y tienen hoy?",
    "necesito cotizar 20 láminas de drywall y perfiles para una obra en Envigado",
    "¿tienen disponible el taladro percutor de 1/2 pulgada?",
    "mi pedido 48213 no ha llegado y ya pasaron cinco días",
    "el martillo que compré ayer salió con el mango partido y quiero cambiarlo",
    "me pueden enviar la factura electrónica del pedido de la semana pasada con el NIT de la empresa",
    "¿qué tipo de broca me sirve para perforar concreto sin que se queme?",
    "tengo que pintar una fachada húmeda, ¿qué sellador me recomiendan?",
    "quiero devolver la pulidora porque no enciende, tengo la garantía",
    "¿hacen domicilio a Soacha y cuánto cobran por 30 varillas?",
    "necesito corregir el RUT en la factura, salió con otro número de documento",
    "¿el tubo PVC de 4 pulgadas viene en presión o sanitario? necesito para un baño",
    "cuánto cuesta el galón de pintura blanca y el rodillo, y si hay descuento por cantidad",
    "ya pagué por transferencia y todavía no me confirman el despacho",
  ];
  const COLAS = ["", " gracias", " quedo atento", " es urgente por favor", " ¿me confirman hoy?", " saludos", " muchas gracias de antemano por la ayuda"];

  // n textos variados (de 3 a ~60 palabras), deterministas según la semilla.
  function generarTextos(n, semilla) {
    const r = azar(semilla == null ? 12345 : semilla);
    const el = a => a[Math.floor(r() * a.length)];
    const out = [];
    for (let i = 0; i < n; i++) {
      const k = 1 + Math.floor(r() * r() * 4); // sesgado a textos cortos, con cola larga
      const partes = [el(SALUDOS) + ","];
      for (let j = 0; j < k; j++) partes.push(el(CUERPOS));
      out.push(partes.join(" ") + el(COLAS) + " #" + i); // el sufijo evita textos idénticos
    }
    return out;
  }

  function percentil(ord, q) {
    return ord[Math.min(ord.length - 1, Math.max(0, Math.ceil(q * ord.length) - 1))];
  }
  function resumen(xs) {
    const o = Float64Array.from(xs).sort();
    const suma = o.reduce((s, x) => s + x, 0);
    return { n: o.length, min: o[0], p50: percentil(o, 0.5), p95: percentil(o, 0.95), p99: percentil(o, 0.99), max: o[o.length - 1], media: suma / o.length };
  }
  const esperar = () => new Promise(r => setTimeout(r));

  async function correrArnes(api, opc) {
    const o = Object.assign({ n: 2000, calentamiento: 200, lote: 50, semilla: 12345, pregunta: PREGUNTA_FERRETERIA, progreso: null }, opc);
    if (!Number.isInteger(o.n) || o.n < 1) throw new Error("n debe ser un entero ≥ 1");
    if (!Number.isInteger(o.lote) || o.lote < 1) throw new Error("lote debe ser un entero ≥ 1");
    const preguntaJSON = typeof o.pregunta === "string" ? o.pregunta : JSON.stringify(o.pregunta);
    const ahora = api.ahora || (() => performance.now());
    const textos = generarTextos(o.n, o.semilla);
    const calor = generarTextos(o.calentamiento, o.semilla + 1);
    const falla = (r, que) => { if (!r.ok) throw new Error(que + ": " + r.error); return r; };
    const avisa = (fase, i, t) => o.progreso && o.progreso(fase, i, t);

    const mem0 = memoria(api);
    for (const t of calor) falla(api.decidir(t, preguntaJSON), "calentamiento");
    falla(api.decidirLote(JSON.stringify(calor.slice(0, o.lote)), preguntaJSON), "calentamiento lote");

    // Decisión a decisión: cada tiempo incluye el cruce JS→wasm y la conversión del resultado.
    const us = new Float64Array(o.n);
    const respuestas = {};
    const t0 = ahora();
    for (let i = 0; i < o.n; i++) {
      const a = ahora();
      const r = api.decidir(textos[i], preguntaJSON);
      us[i] = (ahora() - a) * 1000;
      falla(r, "decidir");
      respuestas[r.answer] = (respuestas[r.answer] || 0) + 1;
      if (i % 100 === 99) { avisa("decisiones", i + 1, o.n); await esperar(); }
    }
    const totalMs = ahora() - t0;

    // Por lotes: tiempo total del lote medido dentro del wasm, y por texto = total / tamaño.
    const lotesUs = [], porTextoUs = [];
    for (let i = 0; i + o.lote <= o.n; i += o.lote) {
      const l = falla(api.decidirLote(JSON.stringify(textos.slice(i, i + o.lote)), preguntaJSON), "decidirLote");
      lotesUs.push(l.total_us);
      porTextoUs.push(l.total_us / o.lote);
      if ((i / o.lote) % 10 === 9) { avisa("lotes", i + o.lote, o.n); await esperar(); }
    }
    const mem1 = memoria(api);

    return {
      version: 1,
      fecha: new Date().toISOString(),
      entorno: entorno(),
      config: { n: o.n, calentamiento: o.calentamiento, lote: o.lote, semilla: o.semilla, pregunta: o.pregunta, opciones: o.pregunta.options ? o.pregunta.options.length : null },
      por_decision_us: resumen(us),
      decisiones_por_s: o.n / (totalMs / 1000),
      por_lote: lotesUs.length ? { tamano: o.lote, lotes: lotesUs.length, lote_us: resumen(lotesUs), por_texto_us: resumen(porTextoUs) } : null,
      respuestas,
      memoria: { antes: mem0, despues: mem1 },
    };
  }

  function memoria(api) {
    const m = {};
    if (api.memoriaGo) Object.assign(m, api.memoriaGo());
    if (api.memoriaWasm) m.wasm_buffer_bytes = api.memoriaWasm();
    const pm = raiz.performance && raiz.performance.memory;
    if (pm) m.js_heap_usado = pm.usedJSHeapSize; // solo Chrome
    return m;
  }

  function entorno() {
    const n = raiz.navigator || {};
    return {
      user_agent: n.userAgent || ("node " + (raiz.process && raiz.process.version)),
      plataforma: n.platform || (raiz.process && raiz.process.platform) || null,
      nucleos: n.hardwareConcurrency || (raiz.process && require("os").cpus().length) || null,
      memoria_gb_aprox: n.deviceMemory || null,
      resolucion_timer: "performance.now()",
    };
  }

  const exp = { correrArnes, generarTextos, resumen, PREGUNTA_FERRETERIA };
  if (typeof module !== "undefined" && module.exports) module.exports = exp;
  else raiz.Arnes = exp;
})(typeof globalThis !== "undefined" ? globalThis : this);
