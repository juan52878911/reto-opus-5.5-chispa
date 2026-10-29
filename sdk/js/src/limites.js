// Validación local de la petición, con los límites por defecto de server/api/openapi.yaml (x-max-bytes).
// Se cuentan BYTES UTF-8, como hace el servidor, no caracteres. Mismos códigos de error que el servidor.

import { ErrorChispa } from "./error.js";

/** Valores por defecto del servidor; se pueden sobreescribir si el operador cambió la sección `limites`. */
export const LIMITES = Object.freeze({
  maxEstado: 262144,
  maxPreguntas: 256,
  maxId: 256,
  maxTexto: 4096,
  maxOpciones: 256,
  maxCuerpo: 1048576,
});

const KINDS = ["choice", "score", "noul", "multi"];
const enc = new TextEncoder();

/** Bytes UTF-8 de una cadena. */
export function bytes(s) {
  return enc.encode(s).length;
}

// U+001D–U+001F: el servidor los usa de separadores al hashear el esquema, así que no los admite.
const SEPARADORES = /[\x1d-\x1f]/;

function falla(codigo, mensaje, idPregunta) {
  return new ErrorChispa({ codigo, mensaje, idPregunta, status: 0 });
}

function texto(v, ruta, idPregunta) {
  if (typeof v !== "string") throw falla("invalid_json", `${ruta}: debe ser texto`, idPregunta);
}

/** Lanza ErrorChispa (status 0) si la petición no cumple el contrato. Todo o nada, como el servidor. */
export function validar(estado, preguntas, lim = LIMITES) {
  if (estado !== undefined && estado !== null) {
    texto(estado, "state", undefined);
    if (bytes(estado) > lim.maxEstado) {
      throw falla("state_too_long", `state: ${bytes(estado)} bytes, máximo ${lim.maxEstado}`);
    }
  }
  if (!Array.isArray(preguntas) || preguntas.length === 0) {
    throw falla("empty_questions", "questions: hace falta al menos una pregunta");
  }
  if (preguntas.length > lim.maxPreguntas) {
    throw falla("too_many_questions", `questions: ${preguntas.length}, máximo ${lim.maxPreguntas}`);
  }
  const vistos = new Set();
  preguntas.forEach((q, i) => {
    const r = `questions[${i}]`;
    if (q === null || typeof q !== "object") throw falla("invalid_json", `${r}: debe ser un objeto`);
    if (q.id === undefined || q.id === "") throw falla("missing_id", `${r}.id: obligatorio`);
    texto(q.id, `${r}.id`, undefined);
    const id = q.id;
    if (bytes(id) > lim.maxId) throw falla("field_too_long", `${r}.id: ${bytes(id)} bytes, máximo ${lim.maxId}`, id);
    if (vistos.has(id)) throw falla("duplicate_question_id", `${r}.id: "${id}" repetido`, id);
    vistos.add(id);
    if (q.question === undefined || q.question === "") throw falla("missing_question", `${r}.question: obligatorio`, id);
    texto(q.question, `${r}.question`, id);
    if (bytes(q.question) > lim.maxTexto) {
      throw falla("field_too_long", `${r}.question: ${bytes(q.question)} bytes, máximo ${lim.maxTexto}`, id);
    }
    if (SEPARADORES.test(q.question)) {
      throw falla("invalid_characters", `${r}.question: no admite los caracteres de control U+001D–U+001F`, id);
    }
    if (q.nonce !== undefined) {
      texto(q.nonce, `${r}.nonce`, id);
      if (bytes(q.nonce) > lim.maxId) {
        throw falla("field_too_long", `${r}.nonce: ${bytes(q.nonce)} bytes, máximo ${lim.maxId}`, id);
      }
    }
    if (q.kind === undefined || q.kind === "") throw falla("missing_kind", `${r}.kind: obligatorio`, id);
    if (!KINDS.includes(q.kind)) {
      throw falla("invalid_kind", `${r}.kind: "${q.kind}" no válido (choice, score, noul o multi)`, id);
    }
    validarOpciones(q, r, id, lim);
  });
}

function validarOpciones(q, r, id, lim) {
  const ops = q.options ?? [];
  if (!Array.isArray(ops)) throw falla("invalid_options", `${r}.options: debe ser una lista`, id);
  if (q.kind !== "noul" && ops.length < 2) {
    throw falla("too_few_options", `${r}.options: ${q.kind} necesita al menos 2 opciones`, id);
  }
  // como el servidor: noul admite 0 opciones o exactamente {false, true}
  if (q.kind === "noul" && ops.length !== 0) {
    const ids = ops.map((o) => o?.id).sort();
    if (ops.length !== 2 || ids[0] !== "false" || ids[1] !== "true") {
      throw falla("invalid_options", `${r}.options: noul solo admite los ids "false" y "true"`, id);
    }
  }
  if (ops.length > lim.maxOpciones) {
    throw falla("too_many_options", `${r}.options: ${ops.length}, máximo ${lim.maxOpciones}`, id);
  }
  const vistas = new Set();
  ops.forEach((o, j) => {
    const ro = `${r}.options[${j}]`;
    if (o === null || typeof o !== "object") throw falla("invalid_options", `${ro}: debe ser un objeto`, id);
    if (o.id === undefined || o.id === "") throw falla("missing_option_id", `${ro}.id: obligatorio`, id);
    texto(o.id, `${ro}.id`, id);
    if (bytes(o.id) > lim.maxId) {
      throw falla("field_too_long", `${ro}.id: ${bytes(o.id)} bytes, máximo ${lim.maxId}`, id);
    }
    if (o.description !== undefined) {
      texto(o.description, `${ro}.description`, id);
      if (bytes(o.description) > lim.maxTexto) {
        throw falla("field_too_long", `${ro}.description: ${bytes(o.description)} bytes, máximo ${lim.maxTexto}`, id);
      }
    }
    if (SEPARADORES.test(o.id)) {
      throw falla("invalid_characters", `${ro}.id: no admite los caracteres de control U+001D–U+001F`, id);
    }
    if (typeof o.description === "string" && SEPARADORES.test(o.description)) {
      throw falla("invalid_characters", `${ro}.description: no admite los caracteres de control U+001D–U+001F`, id);
    }
    if (vistas.has(o.id)) throw falla("duplicate_option_id", `${ro}.id: "${o.id}" repetido`, id);
    vistas.add(o.id);
    if (q.kind === "noul" && o.id !== "true" && o.id !== "false") {
      throw falla("invalid_options", `${ro}.id: en noul solo "false" y "true"`, id);
    }
  });
}
