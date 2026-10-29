export type Kind = "choice" | "score" | "noul";

export interface Opcion {
  /** 1..256 bytes UTF-8. En noul, solo "false" y "true". */
  id: string;
  /** ≤ 4096 bytes UTF-8. En zero-shot es lo único que Chispa ve de la opción. */
  description?: string;
}

export interface Pregunta {
  /** Único en la petición; 1..256 bytes UTF-8. */
  id: string;
  /** 1..4096 bytes UTF-8. */
  question: string;
  kind: Kind;
  /** choice y score: al menos 2. noul: opcional. */
  options?: Opcion[];
  /** Clave de idempotencia (≤ 256 bytes). Si falta, el cliente genera una. */
  nonce?: string;
}

export interface Resultado {
  id: string;
  kind: Kind;
  /** Id de la opción elegida, o "" si ninguna capa opinó. */
  answer: string;
  probs: Record<string, number>;
  /** L0, L1, L2, L3, o "escalar" cuando escalate es true. */
  layer: string;
  escalate: boolean;
  ms: number;
  nonce?: string;
}

export type CodigoServidor =
  | "invalid_json" | "request_too_large" | "method_not_allowed" | "not_found" | "empty_questions"
  | "too_many_questions" | "state_too_long" | "missing_id" | "missing_question" | "missing_kind"
  | "invalid_kind" | "too_few_options" | "too_many_options" | "invalid_options" | "missing_option_id"
  | "duplicate_question_id" | "duplicate_option_id" | "field_too_long";

/** Códigos propios del cliente: `network_error`, `timeout`, `bad_response`, y `http_<status>` si el error no es tipado. */
export type CodigoCliente = "network_error" | "timeout" | "bad_response" | `http_${number}`;

export class ErrorChispa extends Error {
  constructor(init: { codigo: string; mensaje: string; idPregunta?: string; status?: number; cause?: unknown });
  readonly name: "ErrorChispa";
  /** `error.code` del servidor, o uno del cliente. La validación local usa los mismos códigos que el servidor. */
  codigo: CodigoServidor | CodigoCliente | (string & {});
  /** Texto para humanos; no es estable, usa `codigo`. */
  mensaje: string;
  /** `question_id` del error, cuando se conoce. */
  idPregunta?: string;
  /** HTTP; 0 si no hubo respuesta o falló la validación local. */
  status: number;
}

export interface Limites {
  maxEstado: number;
  maxPreguntas: number;
  maxId: number;
  maxTexto: number;
  maxOpciones: number;
}

export const LIMITES: Readonly<Limites>;

/** Bytes UTF-8 de una cadena. */
export function bytes(s: string): number;

export interface OpcionesCliente {
  /** Por defecto http://127.0.0.1:8090. */
  url?: string;
  /** Por intento. Por defecto 10000. */
  timeoutMs?: number;
  /** Reintentos extra tras el primero, solo en red, timeout y 503. Por defecto 2. */
  reintentos?: number;
  /** Base de la espera exponencial entre reintentos. Por defecto 200. */
  esperaMs?: number;
  /** Si el operador cambió la sección `limites` del servidor. */
  limites?: Partial<Limites>;
  /** Para pruebas o entornos sin fetch global. */
  fetch?: typeof fetch;
}

export class ChispaCliente {
  constructor(opts?: OpcionesCliente);
  readonly url: string;
  /** Resultados en el orden de `preguntas`. Lanza ErrorChispa. */
  decidir(estado: string, preguntas: Pregunta[], opts?: { nonce?: string }): Promise<Resultado[]>;
  /** `true` si /healthz contesta ok; `false` ante cualquier fallo. */
  salud(): Promise<boolean>;
}
