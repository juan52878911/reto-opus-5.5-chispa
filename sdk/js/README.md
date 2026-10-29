# SDK de JavaScript

Cliente de `POST /v1/decide` y `GET /healthz` de `chispa-server`, para Node ≥ 20 y navegador. Sin dependencias de ejecución,
solo módulos ESM (usa `fetch`) y tipos escritos a mano en [`src/index.d.ts`](src/index.d.ts). No hay paso de compilación.
Desde CommonJS: `const { ChispaCliente } = await import("@juanbedoya/chispa")`.

El contrato es [`server/api/openapi.yaml`](../../server/api/openapi.yaml). El paquete no se ha publicado en ningún registro:
se usa desde el repositorio (`import … from "./sdk/js/src/index.js"`).

## Ejemplo: la ferretería, zero-shot

El esquema de [`docs/02-inicio-rapido.md`](../../docs/02-inicio-rapido.md). El esquema viaja en la petición, sin
`.chispa` entrenado para esta pregunta: las descripciones son lo único que Chispa ve de cada opción.

```js
import { ChispaCliente, ErrorChispa } from "./sdk/js/src/index.js";

const chispa = new ChispaCliente({ url: "http://127.0.0.1:8090", timeoutMs: 5000, reintentos: 2 });

const [r] = await chispa.decidir(
  "Buenas, ¿cuánto vale el bulto de cemento gris de 50 kg y tienen hoy?",
  [{
    id: "q1",
    question: "¿Qué necesita la persona que escribe a la ferretería?",
    kind: "choice",
    options: [
      { id: "cotizacion", description: "pide precio o disponibilidad de un producto, o una cotización de materiales" },
      { id: "pedido", description: "quiere comprar y recibir productos, o pregunta por el estado de un pedido ya hecho" },
      { id: "garantia", description: "reclama por una herramienta defectuosa, un cambio o una devolución" },
      { id: "asesoria", description: "pide ayuda técnica para elegir o usar un material o una herramienta" },
      { id: "factura", description: "pide una factura, un RUT o corregir datos de facturación" },
    ],
  }],
);

console.log(r.answer, r.probs, r.layer, r.escalate);
// si r.escalate es true, ninguna capa llegó a su τ: r.answer es solo la mejor pista; decide tú qué hacer
```

Los valores de `answer` y `probs` dependen de tu modelo.

## API

`new ChispaCliente({ url, timeoutMs, reintentos, esperaMs, limites, fetch })`

| Opción | Por defecto | |
|---|---|---|
| `url` | `http://127.0.0.1:8090` | |
| `timeoutMs` | `10000` | por intento, incluye leer el cuerpo |
| `reintentos` | `2` | intentos extra; espera exponencial `esperaMs · 2^(n-1)` |
| `esperaMs` | `200` | |
| `limites` | los del OpenAPI | si el operador cambió la sección `limites` del servidor |
| `fetch` | `globalThis.fetch` | |

- `await chispa.decidir(estado, preguntas, { nonce })` → `Resultado[]` en el orden de `preguntas`. `Pregunta` es
  `{ id, question, kind: "choice" | "score" | "noul", options?: [{ id, description? }], nonce? }`;
  `Resultado` es `{ id, kind, answer, probs, layer, escalate, ms, nonce? }`.
- `await chispa.salud()` → `true` si `/healthz` dice `ok`; `false` ante cualquier fallo (no lanza, sin reintentos).

### Nonce e idempotencia

Cada pregunta sin `nonce` recibe un UUID antes del primer intento, y todos los reintentos reenvían exactamente los mismos bytes:
si la respuesta se perdió, el servidor devuelve el resultado guardado en vez de decidir otra vez. Con `{ nonce }`, las preguntas
sin nonce propio lo usan (una sola pregunta: tal cual; varias: `${nonce}:${id}`). Reintenta **solo** con error de red, timeout y 503;
un 4xx, 405, 413, 500 o una respuesta ilegible se lanzan al instante.

### Errores

Todo falla con `ErrorChispa`: `codigo`, `mensaje`, `idPregunta`, `status`.

```js
try { await chispa.decidir(texto, preguntas); }
catch (e) {
  if (e instanceof ErrorChispa) console.error(e.codigo, e.idPregunta, e.status, e.mensaje);
}
```

- `codigo` es el `error.code` del servidor (`invalid_kind`, `field_too_long`…). Usa `codigo`, no `mensaje` (no es estable).
- Códigos propios: `network_error`, `timeout`, `bad_response` (200 fuera del contrato) y `http_<status>` si el error no es tipado.
- `status` es el HTTP; `0` si no hubo respuesta o falló la validación local.

### Validación local

Antes de enviar, el cliente comprueba los límites del OpenAPI **en bytes UTF-8** (una `ñ` o una tilde pesan 2 bytes): `state` 262144,
`id`, `nonce` e ids de opción 256, `question` y `description` 4096, 256 preguntas y 256 opciones; ids únicos; al menos 2 opciones en
`choice` y `score`; en `noul` solo `false` y `true`. Falla con el mismo `codigo` que daría el servidor y `status: 0`, sin tocar la red.
Todo o nada, como el servidor.

## Pruebas

```
cd sdk/js && node --test
```

Sin instalar nada: `node:test` contra un servidor falso de `node:http` (choice, noul, score, errores tipados, timeout,
corte de red, 503 y reintento con el mismo nonce, límites en bytes).

Sin verificar: contra un `chispa-server` real (aquí no hay Go) y en navegador; los tipos de `index.d.ts` no se han pasado por `tsc`
(no está en el nodo). Comando para otro nodo: `npx -p typescript tsc --noEmit --strict --module nodenext src/index.d.ts`.
