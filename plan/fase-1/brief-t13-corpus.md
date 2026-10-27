# T1.3 Generador del corpus sintético v2 en español colombiano

Encargo: `plan/fase-1/encargo.md` y `plan/fase-1/brief-i7-aws.md` (patrón de AWS); esquema
`model/esquema.md` (congelado). Plan aprobado: D4 = Haiku 5.5 solo para **generar textos y verificar
etiquetas**, nunca como fuente de distribuciones para destilar (eso es Qwen, T1.6).
Tú no llamas a AWS ni a Bedrock: escribes y pruebas con un backend simulado. El orquestador lanza una
instancia EC2 cuyo rol puede invocar `us.anthropic.claude-haiku-5-5` en Bedrock (us-east-1).

## Hipótesis
- Con prompts por tarea, clase y estilo (registro colombiano, errores de tecleo, mensajes de voz
  transcritos, mezcla de temas), más dedup por n-gramas y embeddings, salen ≥ 2 k ejemplos útiles por
  tarea con ≤ 8 USD de Haiku. Se refuta si la dedup tira > 40 % o si el verificador rechaza > 25 %.

## Terminado cuando
- `model/corpus/generar.py --tareas … --por-clase N --salida <dir> --backend bedrock|simulado
  --tope-usd 8 --precio-in X --precio-out Y`: genera en lotes (p. ej. 20 textos por llamada, JSON
  estricto), cuenta tokens de cada respuesta y **para en seco** al llegar al tope. Reintentos con
  espera exponencial, reanuda desde lo ya escrito.
- Tareas y clases (todas `tipo: choice` salvo que se diga):
  - `whatsapp_comercio`: las de `model/sondeo/` (compra, soporte, queja, saludo) más `escalate`.
  - `pqrs`: petición, queja, reclamo, sugerencia, felicitación, `escalate`.
  - `fintech`: intenciones de una billetera o banco colombiano (saldo, transferencia, bloqueo de
    tarjeta, fraude, crédito, PSE, Nequi/Daviplata como marcas genéricas del dominio, etc.; ≤ 15 clases).
  - `herramientas`: las clases del catálogo `model/herramientas/catalogo.json`, sin texto ni
    plantilla compartidos con `model/herramientas/test.jsonl`.
  - Negativos difíciles: mira `arena/` (ataques de la Arena: spam, inyección) y genera variantes
    que deban ir a `escalate` o a la clase correcta pese al ataque.
- Verificación con Haiku (segunda llamada barata): «¿esta etiqueta es correcta? sí/no»; las filas
  con «no» se descartan y se cuentan.
- Dedup: exacta, por 5-gramas (Jaccard ≥ 0,8) y por coseno de e5-small ≥ 0,95 (en la instancia).
- Salida: un JSONL por tarea en el esquema, `fuente: "chispa T1.3 (Haiku 5.5, Bedrock)"`,
  `licencia: "propia (Chispa)"`, `uso_comercial: true`, `split` train/dev 90/10 por `plantilla`
  (la semilla del prompt), y un `resumen.json` con filas por clase, descartes y USD gastados.
- `model/corpus/aws/arranque.sh`: user-data para Amazon Linux 2023 en c6a.large, mismo patrón que
  `model/bench/aws/arranque.sh` (marcador `CHISPA_S3=__CHISPA_S3__`, código de `$CHISPA_S3/codigo.tgz`,
  resultados a `$CHISPA_S3/corpus.tgz` y `log.txt` con trap, `shutdown -h +170`, sin sleep final).
  Instala boto3, numpy y lo necesario para e5 (torch CPU), y baja e5-small de Hugging Face.
  `model/corpus/aws/empaquetar.sh` como el de bench.
- Prueba en seco aquí, con `--backend simulado` (respuestas falsas con forma real) y `CHISPA_LOCAL=1`,
  de punta a punta, incluida la parada por tope. Tests con `unittest` en `model/corpus/tests/`:
  parsing de JSON roto, tope de USD, dedup, reparto sin fugas, validación contra el esquema.
- `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- Solo `model/corpus/`. **No tocar**: `model/esquema.md`, `model/herramientas/` (solo leer), `arena/` (solo leer).
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, modelos en `~/hf` (sin red salvo la API de Claude, que no usas).
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 120 min de reloj · ≤ 6 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 15 líneas: qué cambiaste, rama y sha, la cola del log de la prueba en
seco, cuántas llamadas y tokens estimas para 2 k por tarea, qué quedó sin verificar y qué recomiendas.
