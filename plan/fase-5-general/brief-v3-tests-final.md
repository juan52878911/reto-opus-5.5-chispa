# V3 Tests sobre el sha final de `integracion`

## Antecedentes
- `integracion` ya tiene fusionados:
  - `chispa-sdk` (`a797bd4`);
  - `calib_completa` y su test.
- Hay que confirmar que todo sigue en verde sobre el HEAD que recibes antes de cerrar la tanda.

## Terminado cuando
- `python -m unittest discover -s model -t .`, `make test` y `make smoke` pasan sobre el HEAD que recibes.
- Si `make smoke` falla, guarda la salida completa del fallo en el informe (las últimas 30 líneas) antes de repetirlo. Ya
  falló una vez de forma intermitente y no se capturó.
- No cambies código. Si algo falla de verdad, descríbelo y para.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- Solo lectura; sin commits salvo que sea imprescindible. Rama: la que te da delega. Base: `integracion`. Sin push ni
  merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, Go en `~/go-sdk/bin`, ORT en `~/ort` y modelos en `~/hf`. Sin red salvo la
  API de Claude.

## Tope
- ≤ 30 min de reloj · ≤ 2 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 6 líneas:
- sha;
- la última línea de cada comando;
- la salida de cualquier fallo intermitente.
