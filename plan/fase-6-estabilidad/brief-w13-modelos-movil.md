# W13 Modelos del perfil móvil para medir la latencia en un Android real (la demo «Medir»)

## Antecedentes
- Juan conectó un **moto g24 power**: Android 14, arm64-v8a, MediaTek Helio G85, 8 núcleos y 8 GB. La demo ya está instalada
  (`com.chispa.demo`, el APK del SDK).
- **La pantalla «Medir»** (`sdk/android/demo/src/main/kotlin/com/chispa/demo/{MedirActivity,Medidor}.kt`, solo lectura):
  - busca `modelo.chispa`, `e5.chispa-tok` y `esquema.json` en `filesDir/elegido`, en `getExternalFilesDir(null)` o en
    `filesDir`;
  - mide p50, p95 y p99 por escenario (L0/L1, L2 con torre en caché y L2 con esquema nuevo) y por proveedor (CPU, XNNPACK y
    NNAPI);
  - se lanza con `adb shell am start -n com.chispa.demo/.MedirActivity --ei n 1000 --ez auto true`.

  **Lee `Medidor.kt` entero** para saber qué espera exactamente de cada fichero y de `esquema.json`.
- **Perfil móvil decidido:**
  - **fp16 con poda ampliada**, el defecto (≈ 89 MB por ONNX);
  - **int8 dinámico** (`movil-int8`) como opción.

  Lo exporta `model/l2/exportar.py` (`--perfil movil` / `movil-int8`, con `--vocab-ampliar`), y `chispa train` (SDK) los
  empaqueta (`--perfil`, `--torre`, `--l1`).
- **Checkpoint:** el ajuste 1, la línea base oficial (`s3://chispa-pruebas-879381269751/ajuste-80ab8ef/ckpt/mejor.pt`), con
  texto de torre v1.

## Terminado cuando
1. **`model/bench/movil/aws/modelos.sh`** (nuevo): user-data de una **c6a.2xlarge** con el patrón de
   `model/l2/aws/estabilidad.sh`. Lleva `__CHISPA_S3__`, `shutdown -h +60` y el coste declarado (≈ 0,15 USD). Construye y
   sube a `$CHISPA_S3/movil/`:
   - **`modelo-fp16.chispa`** y **`modelo-int8.chispa`**: con L0, L1 (potion, como en `model/l1/README.md`), L2 con su torre
     (TORR) y CALIB, para los perfiles `movil` y `movil-int8`;
     - el esquema de entrenamiento con ejemplos tiene que permitir los escenarios L0/L1 de Medir: unos 16 a 32 ejemplos, uno
       pequeño de choice como el de `model/bench/torre/servidor.py`, o el que espere `Medidor.kt`;
   - **`e5.chispa-tok`**, de `runtime/tok/exportar.py`;
   - **`esquema.json`**, en el formato que lea `Medidor.kt`, con preguntas que cubran «L2 con esquema nuevo»;
   - **`manifiesto.json`**: tamaños, sha256, perfil, checkpoint y versión de texto de torre de cada fichero, y si el
     `.chispa` trae TORR.
2. **Validación en la propia instancia:**
   - el `chispa-server` de amd64 abre cada `.chispa`, y `/healthz` da L0, L1, L2 y `torre_al_vuelo`;
   - una decisión de muestra por escenario.

   Si falla, FALLO en `estado.tsv`: no se sube un fichero roto.
3. **Prueba en seco** (`CHISPA_LOCAL=1`) con checkpoint aleatorio y fixtures, sin `FALLO`.
4. **`model/bench/movil/medir.sh`** (nuevo), un script para **el Mac** que solo usa `adb`, `aws s3 cp` y ficheros, sin compilar
   nada:
   - baja los ficheros de `$CHISPA_S3/movil/`;
   - para cada perfil (fp16 e int8), los copia a la app con `adb push` a `/data/local/tmp` y
     `adb shell run-as com.chispa.demo cp` a `files/elegido/` (es una app debug);
   - lanza Medir con `--ez auto true` y espera al JSON en logcat (`adb logcat -s ChispaMedir`) o en el fichero que diga
     `MedirActivity`;
   - guarda en `model/bench/movil/resultados-<fecha>/<perfil>.json` y añade memoria (`dumpsys meminfo com.chispa.demo`) y el
     tamaño instalado (`dumpsys package` o `du` con `run-as`);
   - acepta `ADB_SERIAL`, y **no toca nada fuera de `com.chispa.demo`**.

   Añade un `LEEME` de cómo usarlo, con la desinstalación al final.
5. `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde **después** del último cambio.
- Parada: si algo falla 2 veces, márcalo y para. **No lances nada en AWS** ni toques ningún móvil.

## Zona
- `model/bench/movil/**`. No toques `server/`, `sdk/` ni `format/`.
- Rama: la que te da delega. Base: `integracion-limpia`. **Commits simples, sin firmas ni `Co-Authored-By`.** Sin push ni
  merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, Go en `~/go-sdk/bin`, ORT en `~/ort` y modelos en `~/hf`. Sin red salvo la API de
  Claude.

## Tope
- ≤ 75 min de reloj · ≤ 5 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 10 líneas:
- rama y sha;
- qué construye `modelos.sh`;
- qué espera Medir de cada fichero;
- la tabla de `estado.tsv` de la prueba en seco;
- cómo se usa `medir.sh`.
