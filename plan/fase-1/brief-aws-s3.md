# `arranque.sh` con S3 en vez de scp

Encargo: `plan/fase-1/brief-i7-aws.md` (sigue vigente; esto solo cambia cómo entra el código y cómo
salen los resultados). Tú no llamas a AWS; el orquestador lanza las instancias.

## Hipótesis
- Con un cambio pequeño en `model/bench/aws/arranque.sh`, la instancia baja el código de S3 y sube
  ahí sus resultados, sin SSH. Se refuta con la prueba en seco, si el modo local no llega a
  `resultados.tgz` en el «s3» simulado.

## Terminado cuando
- La instancia tendrá el rol `chispa-pruebas-ec2`, con `s3:GetObject` y `s3:PutObject` sobre
  `s3://chispa-pruebas-879381269751/` (sin List ni Delete). Amazon Linux 2023 trae la aws cli.
- Primera línea tras el shebang: `CHISPA_S3=__CHISPA_S3__`. El orquestador sustituye el marcador
  por un prefijo, p. ej. `s3://chispa-pruebas-879381269751/lat-20261027/c6a`.
- Baja `$CHISPA_S3/codigo.tgz` con `aws s3 cp`, reintentando cada 30 s hasta 45 min. Eso sustituye
  la espera de `/opt/chispa/codigo.tgz`.
- Al terminar, bien o mal, un `trap` sube `$CHISPA_S3/log.txt` y, si existe,
  `$CHISPA_S3/resultados.tgz`; después, `shutdown -h now`. Quita el `sleep 1200`, pero deja el
  `shutdown -h +170` del principio.
- `CHISPA_LOCAL=1` simula S3 con el directorio `/tmp/chispa/s3/<prefijo>` (cp en vez de aws s3 cp).
  Repite la prueba en seco de punta a punta con 20 repeticiones, poniendo `codigo.tgz` en ese
  directorio. Pega la cola del log y el listado del «s3» simulado.
- `bash -n` pasa. `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde.
- Parada: si algo falla 2 veces, márcalo en el informe y para.

## Zona
- Solo `model/bench/aws/`. **No tocar** nada más.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, modelos en `~/hf` (sin red salvo la API de Claude).
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 45 min de reloj · ≤ 1,5 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 15 líneas: qué cambiaste, rama y sha, la cola del log de la prueba en
seco, el listado del «s3» simulado, qué quedó sin verificar y qué recomiendas.
