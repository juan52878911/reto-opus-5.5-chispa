# W15 Exportación fp16 segura para ARM: normalización y atención en fp32

## Antecedentes
- **El perfil móvil fp16** (`model/l2/exportar.py`, `a_fp16`, con `convert_float_to_float16(..., keep_io_types=True)`):
  - en x86 funciona, porque la CPU de ORT calcula fp16 con Cast a fp32 (comprobado con `chispa-server` amd64);
  - en un Android arm64 con fp16 nativo (moto g24, Helio G85), **las torres al vuelo se rechazan**. La sospecha es que e5
    desborda en fp16 (LayerNorm, Softmax, Pow, ReduceMean, Sqrt, Div o Erf) y sale Inf o NaN.
- El int8 funciona en el mismo teléfono.

## Terminado cuando
1. **`a_fp16`** convierte a fp16 **dejando en fp32**, con `op_block_list` o `node_block_list`, los ops sensibles:
   - al menos LayerNormalization, Softmax, Pow, ReduceMean, Sqrt, Div, Erf y ReduceSum;
   - los que use el grafo de e5 para la normalización y la atención. Lístalos desde el grafo real exportado.
   - Se aplica a la consulta y a la torre de los perfiles `movil` (fp16).
   - Las entradas y salidas siguen en float32.
2. **Tests:**
   - en el ONNX exportado (pesos aleatorios con e5 real de `~/hf`), esos ops quedan en float32 y el resto (MatMul y Gather) en
     fp16;
   - una entrada de **activaciones grandes** (por ejemplo, un texto largo repetido) da salida finita;
   - el coseno con fp32 de la torre sigue ≥ 0,999 en 50 textos;
   - el tamaño de la torre fp16 sigue ≈ 88 MB (los pesos son los que pesan).
3. Si puedes, **simula el fp16 nativo**: corre el ONNX con todos los ops en fp16 con onnxruntime (sin el bloqueo) y comprueba
   si aparecen Inf/NaN con activaciones grandes. Eso confirmaría la causa. Si no se puede, dilo.
4. `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde **después** del último cambio.
- Parada: si algo falla 2 veces, márcalo y para. **No lances nada en AWS.**

## Zona
- `model/l2/exportar.py` y `model/l2/tests/**`.
- Rama: la que te da delega. Base: `integracion-limpia`. **Commits simples, sin firmas ni `Co-Authored-By`.** Sin push ni
  merge.

## Entorno
- `source ~/.profile`. Python en `~/venv` (onnx y onnxruntime), modelos en `~/hf`. Sin red salvo la API de Claude.

## Tope
- ≤ 50 min de reloj · ≤ 3 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 8 líneas:
- rama y sha;
- ops bloqueados;
- si se reprodujo el desbordamiento;
- coseno y tamaño;
- tests.
