# V1 Verificar el sha final de `integracion` (perfil móvil fp16)

## Antecedentes
- `integracion` acaba de fusionar `chispa-sdk` (`f91e143`) y D1b, y cambia:
  - el perfil `movil` de `model/l2/exportar.py`, que pasa a fp16 con poda ampliada;
  - el nuevo perfil `movil-int8`, el int8 dinámico de antes;
  - las peticiones de JevBench (`cuerpo_decide`), que ahora envían descripciones en noul y score.
- Ninguno de estos cambios ha pasado aún `make test` ni `make smoke` sobre el sha final.

## Terminado cuando
- `python -m unittest discover -s model -t .`, `make test` y `make smoke` pasan sobre el HEAD que recibes. Copia en el
  informe la última línea de cada uno.
- **Exportación de humo del perfil móvil**, con pesos aleatorios y e5 de `~/hf`:
  `python -m model.l2.exportar --torre-onnx SAL --ckpt-aleatorio --perfil movil --vocab-ampliar <unos textos de fixture>`.
  - Comprueba que la consulta y la torre son fp16 (tipos de los inicializadores del ONNX) y que pesan menos de 100 MB cada
    una.
  - Comprueba que el ONNX carga y corre en onnxruntime.
  - Haz lo mismo con `--perfil movil-int8`.
- Si algo falla, arréglalo solo dentro de `model/` y vuelve a pasar todo. Si el fallo está en `server/`, `sdk/` o
  `format/`, descríbelo y no lo toques.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `model/**`; el resto, solo lectura.
- Rama: la que te da delega. Base: `integracion`. Commits simples, sin firmas ni `Co-Authored-By`. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, Go en `~/go-sdk/bin`, ORT en `~/ort` y modelos en `~/hf`. Sin red salvo la
  API de Claude.

## Tope
- ≤ 45 min de reloj · ≤ 3 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 8 líneas:
- rama y sha;
- el resultado de los tres comandos de tests;
- MB y tipo de dato de `movil` y de `movil-int8`;
- arreglos hechos, si los hubo.
