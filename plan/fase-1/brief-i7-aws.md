# Medida de latencia en AWS (sustituto del i7) y calidad de mmBERT-small

Encargo: `plan/fase-0/encargo.md` (reglas de D3 y de p99 < 50 ms a 64 tokens; no las cambies tú).
Aprobado por Juan el 2026-10-27: c6a.xlarge (AVX2, como el i7) y c6i.xlarge (AVX-512 + VNNI) en
spot, tope de 2 USD de AWS. **Tú no lanzas nada en AWS** (no tienes red): escribes y pruebas los
scripts; el orquestador lanza las instancias.

## Hipótesis
- En x86 con AVX2, e5-small int8 podado baja de 50 ms p99 a 64 tokens con 1 hilo (en el i3 de
  kindling, sin AVX2, dio 200 ms). Se refuta en AWS.
- mmBERT-small con pesos reales, con media de tokens + kNN-32, no saca +3 puntos de macro-F1 sobre
  e5-small + kNN-32 en el sondeo (no está entrenado para embeddings). Se refuta aquí, en kindling.

## Terminado cuando
1. **Calidad de mmBERT, medida aquí**: `model/bench/calidad_codificadores.py` compara e5-small
   (prefijo `query: `, media normalizada) y mmBERT-small (media de la última capa, normalizada) con
   kNN-8 y kNN-32 sobre las 4 tareas de `model/sondeo/` (train_*.jsonl contra *.jsonl), usando
   `model.evaluacion.chispa_eval` para macro-F1 y ECE. Tabla en `model/bench/calidad.md`. Mira cómo
   lo hizo `model/eval0/e5_knn.py` para no desviarte de la cifra de la fase 0 (75,9 con kNN-32).
2. **Script de arranque de AWS**, `model/bench/aws/arranque.sh`, pensado como user-data de una
   Amazon Linux 2023 x86_64 recién creada, como root:
   - Primera línea útil: `shutdown -h +170` (apagado forzoso; la instancia se termina al apagarse).
   - `dnf install -y python3.11 python3.11-pip tar gzip`; venv en `/opt/chispa/venv`; un solo `pip install`
     desde el índice CPU de PyTorch más PyPI (mira `.delega/golden.sh`: torch, transformers,
     onnx, onnxruntime, huggingface_hub, model2vec, numpy); comprueba que torch no trae CUDA.
   - Baja de Hugging Face intfloat/multilingual-e5-small, jhu-clsp/mmBERT-small (con
     `pytorch_model.bin` si no hay safetensors) y minishlab/potion-multilingual-128M.
   - Espera hasta 45 min a que aparezca `/opt/chispa/codigo.tgz` (lo sube el orquestador por scp)
     y lo descomprime en `/opt/chispa/repo`.
   - Corre `model/bench/codificadores.py` con la matriz completa de la fase 0 (e5 y mmBERT, fp32 e
     int8, con y sin poda, 16/64/256 tokens, 1 y 4 hilos, ≥ 200 repeticiones tras 20 de calentamiento,
     potion como static), guarda `lscpu`, `nproc` y las banderas AVX en el resultado.
   - Deja `/opt/chispa/resultados.tgz` y `touch /opt/chispa/LISTO`; todo el log en `/opt/chispa/log.txt`.
     Después, `sleep 1200; shutdown -h now`.
   - Si `codificadores.py` necesita cambios para correr fuera de kindling (rutas de `~/hf`, `HF_HOME`),
     hazlos con una opción o variable de entorno, sin romper su uso actual.
3. `model/bench/aws/empaquetar.sh`: imprime en stdout el tar.gz con lo mínimo que necesita la
   instancia (código de `model/bench/`, `model/evaluacion/` si hace falta, `model/sondeo/`).
4. **Prueba en seco aquí**: corre `arranque.sh` en modo local (`CHISPA_LOCAL=1`: salta dnf, pip y
   descargas, usa `~/venv` y `~/hf`, rutas bajo `/tmp/chispa`, 20 repeticiones, sin shutdown ni
   sleep) de punta a punta, con el `codigo.tgz` de `empaquetar.sh`. Pega en el informe la cola del log.
   `bash -n` y, si está, `shellcheck` sin errores.
- `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde.
- Parada: si algo falla 2 veces, márcalo y avisa con `blocker`.

## Zona
- Solo `model/bench/`. **No tocar**: `model/esquema.md`, `model/evaluacion/` (solo usar),
  `model/sondeo/`, `arena/contracts/`.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, modelos y datos en `~/hf` (sin red salvo la API de Claude).
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 90 min de reloj · ≤ 3 USD de cuenta · cómputo de pago: 0 (no llamas a AWS). Sin subagentes.

## Informe
Termina con un informe de ≤15 líneas: qué cambiaste, rama y sha, la tabla de calidad (macro-F1 por
tarea y media, e5 frente a mmBERT, kNN-8 y kNN-32), la cola del log de la prueba en seco, qué quedó
sin verificar y qué recomiendas.
