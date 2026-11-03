# SDK de Go

Cliente de `POST /v1/decide` y `GET /healthz` de `chispa-server`. Solo biblioteca estándar, Go ≥ 1.27. Módulo
`github.com/juan52878911/chispa/sdk/go` (paquete `chispa`): el mismo propietario y prefijo que `server/go.mod`
(`github.com/juan52878911/chispa/server`), así que el path es el real del repositorio y no hace falta un dominio que no existe.
Los tipos están copiados a mano del contrato ([`server/api/openapi.yaml`](../../server/api/openapi.yaml)): el cliente no importa el servidor.
No se ha publicado en ningún sitio; se usa desde el repositorio (`go.work` o `replace`).

## Ejemplo: la ferretería, zero-shot

El esquema de [`docs/02-inicio-rapido.md`](../../docs/02-inicio-rapido.md). El esquema viaja en la petición, sin `.chispa` entrenado
para esta pregunta: las descripciones son lo único que Chispa ve de cada opción.

```go
c := chispa.Nuevo("http://127.0.0.1:8090", chispa.ConTimeout(5*time.Second), chispa.ConReintentos(2))

rs, err := c.Decidir(ctx, "Buenas, ¿cuánto vale el bulto de cemento gris de 50 kg y tienen hoy?", []chispa.Pregunta{{
	ID:    "q1",
	Texto: "¿Qué necesita la persona que escribe a la ferretería?",
	Kind:  chispa.KindChoice,
	Opciones: []chispa.Opcion{
		{ID: "cotizacion", Description: "pide precio o disponibilidad de un producto, o una cotización de materiales"},
		{ID: "pedido", Description: "quiere comprar y recibir productos, o pregunta por el estado de un pedido ya hecho"},
		{ID: "garantia", Description: "reclama por una herramienta defectuosa, un cambio o una devolución"},
		{ID: "asesoria", Description: "pide ayuda técnica para elegir o usar un material o una herramienta"},
		{ID: "factura", Description: "pide una factura, un RUT o corregir datos de facturación"},
	},
}}, nil)
if err != nil {
	var e *chispa.ErrorChispa
	if errors.As(err, &e) {
		log.Fatalf("%s (HTTP %d, pregunta %q)", e.Codigo, e.Status, e.IDPregunta)
	}
	log.Fatal(err)
}
r := rs[0]
fmt.Println(r.Answer, r.Probs, r.Layer, r.Escalate)
// si r.Escalate es true, ninguna capa llegó a su τ: r.Answer es solo la mejor pista; decide tú qué hacer
```

Los valores de `Answer` y `Probs` dependen de tu modelo.

## API

- `chispa.Nuevo(url, opts...) *Cliente`; opciones: `ConTimeout` (35 s), `ConReintentos` (3), `ConEspera` (200 ms), `ConAPIKey`,
  `ConLimites`, `ConHTTPClient`. El `Cliente` es seguro para uso concurrente.
- `Decidir(ctx, estado, preguntas, *DecidirOpts) ([]Resultado, error)`: resultados en el orden de `preguntas`. `opts` puede ser `nil`;
  `DecidirOpts{Nonce}` da nonce a las preguntas que no traen uno (tal cual con una; `nonce:id` con varias).
- `Salud(ctx) error`: `nil` si `/healthz` dice `ok`. Sin reintentos.
- Tipos: `Pregunta{ID, Texto, Kind, Opciones, Nonce}`, `Opcion{ID, Description}`, `Resultado{ID, Kind, Answer, Answers (solo multi), Probs, Layer, Escalate, MS, Nonce}`;
  `KindChoice`, `KindScore`, `KindNoul`, `KindMulti`.
- `ConAPIKey("…")` añade `Authorization: Bearer …` a todas las llamadas, por si el servidor la pide.

## Errores

Todos son `*ErrorChispa` (`errors.As`): `Codigo` (el `error.code` del servidor o uno propio: `network_error`, `timeout`, `bad_response`,
`canceled`, `http_error`), `Mensaje`, `IDPregunta`, `Status` (HTTP; 0 si no hubo respuesta o falló la validación local),
`RetryAfter` (segundos, tope 30 s) y `Causa`. `timeout` con `Status` 0 es el del cliente; con 503, el del servidor.
Si cancelas el `ctx`, el error es `canceled` y `errors.Is(err, context.Canceled)` sigue valiendo.

## Validación local, nonce y reintentos

- **Límites en bytes UTF-8** como el servidor (`len(string)`, no runas): estado 256 KiB, 256 preguntas, id y nonce 256 B, texto y descripción
  4096 B, 256 opciones, cuerpo 1 MiB. Mismos códigos de error y todo o nada. Si el operador cambió la sección `limites`, pásalos con `ConLimites`.
- **Nonce**: cada pregunta sin nonce recibe uno aleatorio antes del primer intento y todos los reintentos envían el mismo cuerpo, así que
  reintentar es idempotente. Un nonce vacío cuenta como ausente. No se mutan las preguntas del llamador.
- **Reintentos** (misma política que Python, [`docs/05-sdks.md`](../../docs/05-sdks.md)): se reintenta el error de red, el cuerpo 200 ilegible
  y el 503 que no sea `timeout`, con espera `espera·2^(n-1)` y al menos `Retry-After` si lo hay (tope 30 s). No se reintenta el timeout
  propio, el 503 `timeout` del servidor, el 504 ni ningún otro estado, 429 incluido: el error trae `RetryAfter` y decides tú.
- **Timeout**: 35 s por intento (incluye leer el cuerpo), mayor que el `-timeout` del servidor (30 s). Si lo bajas, mantenlo por encima.

## Pruebas

```
cd sdk/go && go vet ./... && go test -race -count=1 ./...
```

Con `httptest`, sin servidor real. Las esperas entre reintentos se sustituyen en las pruebas, que no duermen.

## Licencia

Apache-2.0 (ver `LICENSE` de la raíz del repositorio). Las atribuciones de terceros están en `NOTICE`. Los datasets con SA, NC o con términos pendientes
(XNLI, clima, datos.gov.co, SIB-200, etiquetas de ALIA, salidas de Haiku) no se redistribuyen y solo se usan como test.
