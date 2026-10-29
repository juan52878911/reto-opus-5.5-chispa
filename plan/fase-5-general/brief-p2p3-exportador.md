# P2 + P3 Exportador: torre fp32 completa (servidor), int8 con poda ampliada (móvil) y clave de ESQUEMAS/CONJ con descripción

## Antecedentes
- **Configuración que eligió Juan:** en el servidor, sin cuantizar; en el móvil, cuantizado. G.7
  (`model/bench/torre/resultados-20261029-variantes/LEEME.md`) midió con el checkpoint real:
  - la torre fp32 **sin** `<unk>` cumple la paridad (coseno 1,000, top-1 1,000);
  - la poda a 55 k (`model/bench/vocab-podado-e5-small.json`) manda a `<unk>` el 7,5 % de los tokens de massive-es y
    cuesta entre 3 y 8 puntos de top-1;
  - el int8 dinámico da 0,986.
- **Clave de ESQUEMAS y CONJ.** Hoy `exportar.py` escribe `HashEsquema(pregunta, [opción])`, sin la descripción. La torre
  al vuelo del runtime usa `HashEsquema(pregunta, [opción, descripción])`. Hay que alinearlas con una versión de formato
  nueva y compatibilidad hacia atrás. Es el pendiente registrado en `plan/fase-2/encargo.md`.
- **Reparto:** el runtime en Go y en el móvil lo cambia la otra sesión. Tú haces el exportador, el contrato y los fixtures.

## Hipótesis
- **Servidor:** perfil `servidor`, con consulta y torre en fp32 y vocabulario completo. Paridad exacta (coseno ≥ 0,9999,
  top-1 1,0) y unos 470 MB.
- **Móvil:** perfil `movil`, int8 dinámico por canal con poda **ampliada**. La poda es la unión del vocabulario podado
  actual, los tokens de un corpus de español del golden (`~/datos`, las tareas en español) y los tokens del train del
  cliente (los ejemplos de `chispa train`). Esa ampliación deja los `<unk>` por debajo del 0,5 % en massive-es y el
  top-1 ≥ 0,93, con ≤ 60 MB.
- Se refuta midiendo.

## Terminado cuando
- **P2.** `model/l2/exportar.py` acepta `--perfil servidor|movil`:
  - `servidor` equivale a `--cuant ninguna --cuant-torre ninguna --sin-poda`;
  - `movil` equivale a int8 dinámico por canal en consulta y torre, con poda ampliada;
  - `--vocab-ampliar <jsonl|txt>…` (repetible) une al vocabulario podado los tokens de esos textos. El informe de paridad
    da el % de `<unk>` antes y después.
  - Paridad y tamaño medidos aquí con e5 de `~/hf` y pesos aleatorios: la fidelidad del codificador y el % de `<unk>` no
    dependen del entrenamiento. Tabla en `model/l2/resultados/perfiles/LEEME.md`.
- **P3.** Clave nueva `HashEsquema(pregunta, [opción, descripción])`, igual que la torre al vuelo; en noul y score, la
  lista de opciones con sus descripciones.
  - El `.chispa` lleva la versión nueva (`ESQUEMAS v2` / `CONJ v2`, o un campo de versión: decide y documenta).
  - El exportador siempre escribe v2.
  - Los fixtures de prueba con v1 siguen como están, para que el runtime pruebe la compatibilidad.
  - Documéntalo en `model/l2/contrato-torre.md` y en `docs/04-formato-chispa.md`, con un ejemplo de clave.
  - Añade el fixture `model/l2/tests/fixtures/esquemas-v2.chispa` (pequeño, pocos KB) más su JSON con las claves
    esperadas, para la paridad del runtime.
- `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde **después** del último cambio.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `model/l2/exportar.py`, `model/l2/contrato-torre.md`, `model/l2/tests/**`, `model/l2/resultados/perfiles/**`,
  `model/bench/**` y `docs/04-formato-chispa.md`.
- No toques `server/`, `sdk/`, `runtime/` ni `format/`: el runtime es de la otra sesión. Si `format/chispa3` necesita un
  cambio de lectura para v2, descríbelo en el informe.
- Rama: la que te da delega. Base: `integracion`. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, Go en `~/go-sdk/bin`, modelos en `~/hf` y datos en `~/datos`. Sin GPU y sin
  red salvo la API de Claude.

## Tope
- ≤ 120 min de reloj · ≤ 7 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 12 líneas:
- rama y sha;
- la tabla de perfiles (MB, coseno, top-1 y % de `<unk>`);
- el formato v2 y el fixture;
- qué tiene que hacer el runtime.
