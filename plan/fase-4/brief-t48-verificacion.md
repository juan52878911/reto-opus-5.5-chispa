# T4.8 Verificación independiente del repo y etiqueta de capa en la cascada

## Antecedentes
- En el día se integraron muchas ramas de workers distintos:
  - `format/chispa3` con CONJ, L0TF y `tau_l2c`;
  - `sdk/python` con `chispa train --conjunta`;
  - `server/decide` con L2c, L0TF, simproto int8 y `tau_l2c`;
  - `runtime/tok`;
  - `arena/internal/detectors/cascada.go`.
- El último worker (T4.6b, `bd1b62a`) no repitió `make test` ni `make smoke` después de añadir sus tests de Python.
- En los informes de la cascada (`server/deploy/aws/e2e.sh` y `server/deploy/abstencion/`), la fila de lo que escala sale
  como «L3», y eso confunde.

## Hipótesis
La rama actual pasa todas sus pruebas en una máquina limpia. Se refuta si algo falla: en ese caso, lo arreglas solo si el
arreglo es local y evidente (≤ 20 líneas). Si no, lo describes y paras.

## Terminado cuando
- Instala en tu directorio de trabajo, sin sudo y sin tocar el sistema, lo que haga falta:
  - Go según `go.mod`, con `GOTOOLCHAIN=local` si hace falta;
  - un venv de Python con las dependencias del repo (torch en CPU).
  - Si algo no se puede instalar, dilo.
- Corre y anota el resultado de:
  - `make test` y `make smoke`;
  - `cd server && go vet ./... && go test -race ./...`;
  - `cd format/chispa3 && go test ./...`, más 60 s de cada fuzz;
  - `cd runtime/l1 && go test ./...` y `cd runtime/tok && go test ./...`, este último sin el modelo de HF;
  - `python -m unittest discover -s model -t .` y los tests de `sdk/python`;
  - `cd arena && go test ./...`.
- **Etiqueta de capa.** En la respuesta de la cascada o en los informes, cuando ninguna capa acepta, la capa debe decir
  `escalar` (o lo que fije `server/decide/cascada.go`; decide y justifica) y no «L3». No cambies el contrato de
  `arena/contracts/` ni la forma JSON de `/v1/decide`. Si para eso hay que cambiar el contrato, solo descríbelo.
- Arregla solo lo que sea pequeño y evidente, con commits separados.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `server/decide/cascada.go`, `server/deploy/aws/e2e.sh` (la parte del informe), `server/deploy/abstencion/medir.py` y
  los arreglos pequeños que encuentres.
- No toques `contracts/` ni `arena/contracts/`.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- Host Linux con red, 12 hilos y 7 GB de RAM, sin Go ni torch instalados.
- No hay datos en `~/hf`: los tests que los necesiten deben saltarse solos. Si no lo hacen, dilo.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 90 min de reloj · ≤ 6 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 12 líneas:
- rama y sha;
- una tabla de suites con OK, fallo o saltada;
- qué arreglaste;
- qué queda.
