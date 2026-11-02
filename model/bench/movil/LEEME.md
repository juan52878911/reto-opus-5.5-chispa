# Medir los perfiles móviles en un Android real

`aws/modelos.sh` construye en AWS los ficheros que lee la pantalla «Medir» de la demo y los sube a `$CHISPA_S3/movil/`:
`modelo-fp16.chispa`, `modelo-int8.chispa`, `e5.chispa-tok`, `esquema.json` y `manifiesto.json` (tamaño, sha256, perfil, checkpoint,
versión del texto de torre y si el `.chispa` trae TORR). `medir.sh` los baja y los mide en el móvil.

## Requisitos
- `adb` y `aws` (con lectura sobre `$CHISPA_S3/movil/`) en el PATH del Mac. Nada se compila.
- El móvil con depuración USB y `com.chispa.demo` ya instalada (el APK debug del SDK: `run-as` solo funciona con apps debug).
- Un solo móvil conectado, o `ADB_SERIAL=<serie de adb devices>`.

## Uso
```bash
export CHISPA_S3=s3://chispa-pruebas-879381269751/movil-AAAAMMDD   # el prefijo en el que corrió modelos.sh (con movil/ dentro)
ADB_SERIAL=XXXXXXXX bash model/bench/movil/medir.sh                # fp16 e int8
bash model/bench/movil/medir.sh int8                               # solo un perfil
MEDIR_N=300 bash model/bench/movil/medir.sh fp16                   # prueba rápida (N por escenario; por defecto 1000)
```
Por perfil: `adb push` a `/data/local/tmp`, `run-as com.chispa.demo cp` a `files/elegido/` (con renombrado atómico),
`am start -n com.chispa.demo/.MedirActivity --ei n N --ez auto true` y espera a los trozos `RESULTADO_JSON i/n` de
`adb logcat -s ChispaMedir` (la app guarda además un JSON en su carpeta externa). Deja el móvil quieto (pantalla encendida,
enchufado, sin otras apps).

Resultado en `model/bench/movil/resultados-<fecha>/`:
- `<perfil>.json`: el JSON de la app (p50/p95/p99 por escenario y proveedor CPU/XNNPACK/NNAPI, dispositivo, notas) más el campo
  `adicional`: PSS total final y máximo durante la medida (`dumpsys meminfo`), RSS, APK, datos de la app (`du` con `run-as`) y tamaño
  y sha256 del modelo instalado.
- `<perfil>.meminfo.txt` y `manifiesto.json` (con el que se verificó el sha256 de cada descarga).

Cómo leerlo: «L0/L1» y «L2 con la torre en caché» usan la pregunta de `esquema.json`; «L2 con esquema nuevo» es `Medidor.ZERO_SHOT`, que
el `.chispa` no trae (la torre se calcula al vuelo). Un escenario con `errores > 0` o con `nota` no vale como medida.

## Qué toca en el móvil
Solo `com.chispa.demo` (su `files/elegido/`, `force-stop` y arranque de la app) y los temporales que sube a `/data/local/tmp`, que
borra. No limpia logcat ni instala nada.

## Desinstalar al terminar
```bash
adb shell run-as com.chispa.demo rm -r files/elegido                       # solo los modelos (≈ 100 MB)
adb shell rm -f /sdcard/Android/data/com.chispa.demo/files/chispa-medir-*.json
adb uninstall com.chispa.demo                                              # la demo entera, con sus datos
```
(`adb -s <serie>` si hay más de un móvil.) Los JSON que la app copió a Descargas (`chispa-medir-*.json`) se borran a mano desde el móvil.
