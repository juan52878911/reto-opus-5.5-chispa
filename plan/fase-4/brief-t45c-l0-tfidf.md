# T4.5c L0 TF-IDF de caracteres en el servidor, como fuente de la cabeza conjunta

## Antecedentes
La ablación de H2 (`server/deploy/resultados/ablacion-20261028/LEEME.md`) encontró la causa del hueco de punta a punta de
la cabeza conjunta L2c: el L0. Con el L0 TF-IDF de sklearn y su cabeza, el servidor sube +4,7 puntos en massive y +4,1 en
clinc150. Si en cambio se reentrena la cabeza sobre el L0 de Chispa (`pkg/chispa` de kindling), solo se recupera ~1 punto.

El L0 que alimenta a la cabeza en `model/l2/conjunta.py` y en `sdk/python/chispa/conjunta.py` es el de
`model/lineas_base/correr.py`:
- `TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True, lowercase=True)`;
- `LogisticRegression(C=10.0, max_iter=1000)`;
- entrenado con todo el train, y fuera de pliegue para entrenar la cabeza.

## Hipótesis
- H1: un L0 «tfidf» en Go puro reproduce el `predict_proba` de sklearn con |Δp| ≤ 1e-5. Para eso implementa:
  - el analizador `char_wb` de sklearn (minúsculas, padding con espacio por palabra, n-gramas de 2 a 5 por palabra);
  - el vocabulario y el idf exportados;
  - `sublinear_tf` y la norma l2;
  - los coeficientes y la intercepción de la LR multinomial.
- H2: en el `.chispa` cabe en ≤ 48 MB para clinc150, con vocabulario podado por frecuencia o `max_features`. La pérdida es
  ≤ 0,3 puntos de macro-F1 frente a sin podar; mídelo en Python.
- H3: con este L0 alimentando a CONJ (y la cabeza entrenada sobre él en `chispa train --conjunta`), la prueba de punta a
  punta queda a ≤ 1 punto de `conjunta.py`: massive 0,817 y clinc150 0,890. Esto se mide en AWS después.
- Se refuta midiendo.

## Terminado cuando
- `format/chispa3/`: una sección nueva, `L0TF`, añadida al final del enum sin renumerar. Lleva:
  - el vocabulario de n-gramas (cadenas o un hash con lista de colisiones; justifica la elección y que sea exacta);
  - el idf;
  - los coeficientes en float32 o float16 (mide el efecto en |Δp|);
  - las intercepciones;
  - las etiquetas.

  Con escritor, lector, validación, ida y vuelta, y 5 min de fuzz. Los ficheros sin `L0TF` siguen igual.
- `sdk/python/chispa/`:
  - `chispa train --conjunta` entrena este L0 con el mismo código que `model/lineas_base/correr.py` (impórtalo) y lo
    escribe en `L0TF`;
  - la cabeza conjunta se entrena con sus probabilidades fuera de pliegue, que es lo que hace hoy
    `sdk/python/chispa/conjunta.py`;
  - sin `--conjunta`, nada cambia.
- `server/decide/`:
  - si el `.chispa` trae `L0TF`, la capa L0 de la cascada y la entrada de L0 de L2c usan el L0 tfidf;
  - si no, se usa el de Chispa, como hoy;
  - test de paridad Go ↔ sklearn con un fixture (≥ 200 frases con tildes, emojis, mayúsculas y espacios raros;
    |Δp| ≤ 1e-5);
  - bench de latencia por consulta con 150 clases;
  - `go test ./...` y `go vet ./...` sin la etiqueta `ort`.
- `server/deploy/aws/e2e.sh` no se toca: debe funcionar igual, porque `chispa train --conjunta` ya genera `L0TF`.
- `make test`, `make smoke` y `python -m unittest discover -s model -t .` en verde.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `format/chispa3/**`, `sdk/python/**` y `server/decide/**`.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Go en `~/go-sdk/bin`, Python en `~/venv` y modelos en `~/hf`. Sin GPU y sin red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.
- No vuelques datos en el contexto.

## Tope
- ≤ 150 min de reloj · ≤ 8 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 12 líneas:
- rama y sha;
- paridad (|Δp| máx);
- MB y pérdida de H2;
- latencia;
- qué quedó sin verificar.
