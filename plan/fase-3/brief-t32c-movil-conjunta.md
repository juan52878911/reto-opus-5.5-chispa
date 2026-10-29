# T3.2c SDK móvil con la cascada nueva: L0TF y CONJ en `chispamovil`

## Antecedentes
- El servidor ya usa la cascada L0TF → L2c, la cabeza conjunta (`server/decide/`, secciones `L0TF` y `CONJ` de
  `format/chispa3`, tokenizador de e5 en `runtime/tok`). En la prueba de punta a punta da massive 0,814 y clinc150 0,887.
- Los SDK móviles se quedaron atrás:
  - `sdk/movil/chispamovil/`: paquete Go para gomobile;
  - `sdk/android/`: Kotlin, con L2 por ORT;
  - `sdk/ios/`: Swift, sin compilar.

  Tal como cuenta `docs/05-sdks.md`, ninguno lee `L0TF` ni `CONJ`, y piden a la app un tokenizador de e5.

## Hipótesis
`chispamovil` puede exponer, en Go puro:
- L0TF;
- el tokenizador de e5 (`runtime/tok`);
- la cabeza conjunta: recibe las similitudes que calcula L2 en ORT desde Kotlin o Swift y devuelve probabilidades.

Para eso reutiliza el código de `server/decide` y `runtime/tok`, sacando lo común a un paquete compartido si hace falta y
sin cambiar su comportamiento. Las probabilidades de L0TF y de la cabeza coinciden con las del servidor con |Δp| ≤ 1e-6.
Se refuta si la reutilización obliga a duplicar lógica.

## Terminado cuando
- `chispamovil` expone:
  - `TokenizarE5`;
  - `DecidirL0` con L0TF;
  - `CabezaConjunta(simsJSON)`.
- Con tests nativos de paridad frente a las funciones del servidor, sobre los fixtures que ya hay en el repo
  (`model/l2/tests/fixtures_conjunta/` y los de L0TF).
- `sdk/android/`:
  - la cascada en Kotlin usa L0TF y, si el `.chispa` trae `CONJ`, L2c: similitudes por ORT y cabeza por gomobile;
  - tests JVM con dependencias falsas, como los que ya hay.
- `sdk/ios/`: lo mismo en Swift, sin compilar, igual que hasta ahora.
- `docs/05-sdks.md`: actualiza la sección de lo que falta.
- No hay Android SDK ni Xcode aquí. Instala Go en tu directorio, sin sudo, y corre `go test` y `go vet` del paquete. Kotlin
  y Swift quedan sin compilar: dilo. La compilación del AAR se hará en AWS con `sdk/android/aws/arranque.sh`; si ese
  script necesita cambios, hazlos.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `sdk/movil/**`, `sdk/android/**`, `sdk/ios/**` y `docs/05-sdks.md`.
- Si hace falta un paquete compartido, `runtime/` o `server/decide/` **solo para mover código sin cambiar su
  comportamiento**, con sus tests en verde.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- Host Linux con red, sin Go, torch, Android SDK ni Xcode.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 120 min de reloj · ≤ 7 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 12 líneas:
- rama y sha;
- la paridad;
- qué quedó sin compilar;
- qué hay que cambiar para compilar en AWS.
