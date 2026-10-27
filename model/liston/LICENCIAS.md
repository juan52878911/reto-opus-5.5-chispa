# Licencias del listón humano

Leídas de la tarjeta (`license:` del README) de cada dataset en `~/hf`; el conversor
(`model.datos.comun.licencia_fuente`) las confirma en cada ejecución y, si la tarjeta no coincide, marca la fila
`uso_comercial: false`. Todas las filas van a `split: test`, así que aun siendo no comerciales valdrían.

| Fuente | Repo en Hugging Face | Licencia (tarjeta) | `uso_comercial` | Nota |
|---|---|---|---|---|
| MultiPICo (ironía, español) | Multilingual-Perspectivist-NLU/MultiPICo | CC-BY-4.0 | true | Atribuir a los autores del corpus. Datos demográficos de anotadores anonimizados. |
| ALIA (odio, muestra humana) | SINAI/ALIA-es-discriminative-hate-speech | CC-BY-4.0 | true | Solo `human_sample` (3 anotadores humanos); las etiquetas de LLM del corpus grande no se usan. |
| toxicity-protests-ES | bgonzalezbustamante/toxicity-protests-ES | CC-BY-4.0 | true | Tuits de protestas en Argentina y Chile. |
| toxicity-Constitution-ES | bgonzalezbustamante/toxicity-Constitution-ES | CC-BY-4.0 | true | Tuits sobre el proceso constitucional chileno. |
| GoEmotions `raw` | google-research-datasets/go_emotions | Apache-2.0 | true | Comentarios de Reddit en inglés. |
| GoEmotions en español | mrm8488/go_emotions-es-mt | Apache-2.0 | true | Traducción automática (EasyNMT); fuente del `texto`. |

Ninguna fuente es no comercial. Los textos son comentarios de redes sociales reales y pueden contener
lenguaje ofensivo o datos personales; las salidas convertidas viven en `/tmp`, no en git.
