#!/usr/bin/env bash
# Para el Mac (o cualquier equipo con adb y aws): mide la latencia de los dos perfiles móviles en el Android conectado con la pantalla «Medir» de la demo
# (com.chispa.demo, debug). Solo usa adb, `aws s3 cp` y ficheros: no compila nada. Los .chispa los deja modelos.sh en $CHISPA_S3/movil/.
# Uso:   CHISPA_S3=s3://bucket/prefijo [ADB_SERIAL=XXXX] bash model/bench/movil/medir.sh [fp16] [int8]      (sin argumentos: los dos)
# Sin S3: MEDIR_LOCAL=dir con los mismos ficheros (manifiesto.json incluido) en vez de CHISPA_S3; no hace falta aws.
# Opcionales: MEDIR_N (decisiones por escenario, 1000) · MEDIR_TIMEOUT (segundos por perfil, 2400) · MEDIR_CACHE (descargas, $TMPDIR/chispa-movil)
#             MEDIR_FECHA (sufijo del directorio, AAAAMMDD-HHMMSS) · MEDIR_SALIDA (por defecto resultados-<fecha> junto a este script)
# Salida: resultados-<fecha>/<perfil>.json (el JSON de la app + «adicional»: memoria y tamaño instalado), <perfil>.meminfo.txt, manifiesto.json.
# Dentro del móvil solo toca com.chispa.demo (su filesDir vía run-as, am force-stop/start de la app) y los ficheros que él mismo sube a /data/local/tmp
# (los borra al terminar). No limpia logcat, no instala ni desinstala nada.
set -uo pipefail
PAQ=com.chispa.demo
AQUI=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
N=${MEDIR_N:-1000}; TIMEOUT=${MEDIR_TIMEOUT:-2400}
FECHA=${MEDIR_FECHA:-$(date +%Y%m%d-%H%M%S)}
SALIDA=${MEDIR_SALIDA:-$AQUI/resultados-$FECHA}
CACHE=${MEDIR_LOCAL:-${MEDIR_CACHE:-${TMPDIR:-/tmp}/chispa-movil}}
PERFILES=("$@"); [ ${#PERFILES[@]} -gt 0 ] || PERFILES=(fp16 int8)
TMPD=/data/local/tmp
die() { echo "medir.sh: $*" >&2; exit 1; }
[ -n "${CHISPA_S3:-}${MEDIR_LOCAL:-}" ] || die "falta CHISPA_S3 (s3://bucket/prefijo con movil/ dentro) o MEDIR_LOCAL"
for p in "${PERFILES[@]}"; do case $p in fp16|int8) ;; *) die "perfil '$p': fp16 o int8";; esac; done
command -v adb >/dev/null || die "no hay adb en el PATH"
[ -n "${MEDIR_LOCAL:-}" ] || command -v aws >/dev/null || die "no hay aws en el PATH"
SHA=$(command -v sha256sum || true); [ -n "$SHA" ] || SHA="shasum -a 256"
adb() { command adb ${ADB_SERIAL:+-s "$ADB_SERIAL"} "$@"; }
sh_movil() { adb shell "$@" | tr -d '\r'; }
if [ -z "${ADB_SERIAL:-}" ]; then
  n=$(command adb devices | awk 'NR>1 && $2=="device"' | wc -l | tr -d ' ')
  [ "$n" = 1 ] || die "hay $n dispositivos conectados: pon ADB_SERIAL (adb devices)"
fi
[ "$(adb get-state 2>/dev/null)" = device ] || die "el dispositivo no está listo (adb get-state)"
sh_movil pm path "$PAQ" | grep -q '^package:' || die "$PAQ no está instalada (instala el APK debug de sdk/android/demo)"
sh_movil run-as "$PAQ" true >/dev/null 2>&1 || die "run-as $PAQ no funciona: la app tiene que ser debug"
echo "dispositivo: $(sh_movil getprop ro.product.manufacturer) $(sh_movil getprop ro.product.model), Android $(sh_movil getprop ro.build.version.release), $(sh_movil getprop ro.product.cpu.abi)"

# --- 1. descargas (aws s3 cp, fichero a fichero) y sha256 contra el manifiesto ------------------------------------------------------------
mkdir -p "$CACHE" "$SALIDA"
for f in manifiesto.json modelo-fp16.chispa modelo-int8.chispa e5.chispa-tok esquema.json; do
  case $f in modelo-fp16.chispa) [[ " ${PERFILES[*]} " == *" fp16 "* ]] || continue;; modelo-int8.chispa) [[ " ${PERFILES[*]} " == *" int8 "* ]] || continue;; esac
  if [ -n "${MEDIR_LOCAL:-}" ]; then [ -s "$CACHE/$f" ] || die "falta $CACHE/$f"; continue; fi
  aws s3 cp --only-show-errors "$CHISPA_S3/movil/$f" "$CACHE/$f" || die "no se pudo bajar $CHISPA_S3/movil/$f"
done
cp "$CACHE/manifiesto.json" "$SALIDA/manifiesto.json"
verifica() {   # fichero: el sha256 del manifiesto (json.dump indent=1: «"nombre": {"bytes": N, "sha256": "…»», sin espacios tras quitar saltos de línea)
  local esperado real
  esperado=$(tr -d '\n ' < "$CACHE/manifiesto.json" | grep -o "\"$1\":{\"bytes\":[0-9]*,\"sha256\":\"[0-9a-f]*\"" | grep -o '[0-9a-f]\{64\}')
  real=$($SHA "$CACHE/$1" | cut -d' ' -f1)
  [ -n "$esperado" ] && [ "$esperado" = "$real" ] || die "sha256 de $1 no coincide con el manifiesto (esperado '${esperado:-?}', real $real)"
}
for f in modelo-fp16.chispa modelo-int8.chispa e5.chispa-tok esquema.json; do [ -f "$CACHE/$f" ] && verifica "$f"; done
echo "descargas verificadas en $CACHE"

# --- 2. por perfil: copiar a files/elegido/, lanzar Medir y esperar el JSON ---------------------------------------------------------------
subidos=()
limpiar() { for f in "${subidos[@]:-}"; do [ -n "$f" ] && adb shell rm -f "$TMPD/$f" >/dev/null 2>&1; done; }
trap limpiar EXIT
instala() {   # fichero local → nombre en files/elegido/ (adb push + run-as cp a un temporal + mv: el .chispa viejo puede estar mapeado)
  local origen=$1 destino=$2 tmp="chispa-medir-$2"
  adb push "$CACHE/$origen" "$TMPD/$tmp" >/dev/null || die "adb push $origen"
  subidos+=("$tmp"); adb shell chmod 644 "$TMPD/$tmp"
  adb shell "run-as $PAQ sh -c 'mkdir -p files/elegido && cp $TMPD/$tmp files/elegido/$destino.nuevo && mv files/elegido/$destino.nuevo files/elegido/$destino'" \
    || die "run-as cp $destino"
  adb shell rm -f "$TMPD/$tmp"
}
pss_kb() { grep -o 'TOTAL PSS: *[0-9]*' | grep -o '[0-9]*$' | head -1; }
num() { case ${1:-} in ''|*[!0-9]*) echo null;; *) echo "$1";; esac; }
for p in "${PERFILES[@]}"; do
  echo "== perfil $p"
  adb shell am force-stop "$PAQ"
  instala "modelo-$p.chispa" modelo.chispa; instala e5.chispa-tok e5.chispa-tok; instala esquema.json esquema.json
  t0=$(sh_movil date +'%m-%d %H:%M:%S.000')
  t_ini=$(date +%s)
  adb shell am start -n "$PAQ/.MedirActivity" --ei n "$N" --ez auto true >/dev/null || die "no arrancó MedirActivity"
  pss_max=0; ok=0; log="$SALIDA/$p.logcat.txt"
  while :; do
    sleep 10
    adb logcat -d -T "$t0" -v raw -s ChispaMedir:V 2>/dev/null | tr -d '\r' > "$log"
    v=$(sh_movil dumpsys meminfo "$PAQ" | pss_kb); [ -n "$v" ] && [ "$v" -gt "$pss_max" ] && pss_max=$v
    if grep -q 'medida fallida' "$log"; then ok=0; break; fi
    tot=$(grep -o '^RESULTADO_JSON [0-9]*/[0-9]*' "$log" | head -1 | cut -d/ -f2)
    if [ -n "$tot" ] && [ "$(grep -o '^RESULTADO_JSON [0-9]*/' "$log" | sort -u | wc -l | tr -d ' ')" = "$tot" ]; then ok=1; break; fi
    [ $(( $(date +%s) - t_ini )) -lt "$TIMEOUT" ] || { echo "tiempo agotado (${TIMEOUT}s)"; break; }
  done
  if [ "$ok" != 1 ]; then tail -5 "$log" >&2; echo "FALLO perfil $p: sin JSON (log en $log)" >&2; adb shell am force-stop "$PAQ"; continue; fi
  # el JSON: los trozos «RESULTADO_JSON i/n <texto>» por orden de i (un trozo repetido se descarta)
  awk '/^RESULTADO_JSON [0-9]+\/[0-9]+ /{ split($2, a, "/"); i = a[1] + 0; if (!(i in t)) { t[i] = substr($0, length($1) + length($2) + 3); if (i > m) m = i } } END { for (i = 1; i <= m; i++) printf "%s", t[i] }' \
    "$log" > "$SALIDA/$p.json.tmp"
  # memoria (la última lectura y el máximo visto durante la medida) y tamaño instalado
  sh_movil dumpsys meminfo "$PAQ" > "$SALIDA/$p.meminfo.txt"
  fin=$(pss_kb < "$SALIDA/$p.meminfo.txt"); rss=$(grep -o 'TOTAL RSS: *[0-9]*' "$SALIDA/$p.meminfo.txt" | grep -o '[0-9]*$' | head -1)
  apk=$(sh_movil pm path "$PAQ" | head -1 | sed 's/^package://'); apk_b=$(sh_movil stat -c %s "$apk" 2>/dev/null | head -1)
  datos_kb=$(sh_movil run-as "$PAQ" du -sk . 2>/dev/null | cut -f1 | head -1)
  mod_b=$(sh_movil run-as "$PAQ" stat -c %s files/elegido/modelo.chispa 2>/dev/null | head -1)
  sha_m=$($SHA "$CACHE/modelo-$p.chispa" | cut -d' ' -f1)
  extra=$(printf '"adicional":{"perfil":"%s","n":%s,"total_pss_kb":%s,"total_pss_max_kb":%s,"total_rss_kb":%s,"apk_bytes":%s,"datos_app_kb":%s,"modelo_instalado_bytes":%s,"modelo_sha256":"%s","segundos":%s}' \
    "$p" "$N" "$(num "$fin")" "$(num "$pss_max")" "$(num "$rss")" "$(num "$apk_b")" "$(num "$datos_kb")" "$(num "$mod_b")" "$sha_m" "$(( $(date +%s) - t_ini ))")
  # «adicional» como último campo del objeto de la app (el JSON de org.json termina en «}»)
  sed '$ s/}[[:space:]]*$//' "$SALIDA/$p.json.tmp" | { cat; printf ',%s}\n' "$extra"; } > "$SALIDA/$p.json"; rm -f "$SALIDA/$p.json.tmp" "$log"
  adb shell am force-stop "$PAQ"
  echo "perfil $p: $SALIDA/$p.json (PSS final ${fin:-?} kB, máx. ${pss_max} kB; APK ${apk_b:-?} B; datos ${datos_kb:-?} kB)"
done
echo "listo: $SALIDA (los modelos siguen en files/elegido/ de $PAQ; para quitarlos, ver el LEEME)"
