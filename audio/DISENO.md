# Jev de audio (fase 5): diseño

Estado: diseño + esqueleto en `audio/chispa_audio/` sin modelos ni datos. Nada de esto está entrenado ni medido.
Origen: notas de la bóveda de Juan (2026-10-23/24). Las cifras de terceros (Prosodia, DJ R3X, LLM-as-Jev, WhisperRT, EfficientAT)
vienen de esas notas y **no las he verificado**.

## 1. Objetivo
Clasificar o decidir sobre **audio de llamadas, en streaming y sin transcribir antes**, con las mismas preguntas tipadas de Chispa
(`choice`, `score`, `noul`; esquemas y opciones nuevos en zero-shot o con pocos ejemplos) y la misma respuesta
(`answer`, `probs` calibradas, `layer`, `escalate`). Lo que se pierde al transcribir (tono, emoción, hablante, entorno) es el valor.

## 2. Casos de uso en Colombia
Todos son preguntas sobre un trozo de llamada; ninguno necesita texto.
- Cobranza y banca (banca y cobranza; mismo patrón en Colombia): «¿el cliente está molesto?» (noul),
  «nivel de alteración» (score 1-5), «¿quiere hablar con un humano?» (noul).
- Calidad (QA) de líneas de atención: ¿el agente saludó/cerró? (noul), ¿hay gritos o solapamiento? (score), tipo de ruido (choice).
- Triaje de PQRS por voz y de líneas de emergencia: ¿hay ruido ambiente que indique riesgo? (choice).
- Detección de buzón de voz / contestadora / IVR frente a persona (choice), útil en marcadores salientes.
- Señales de fraude por voz (¿lee un guion?, ¿voz sintética?): idea; exige datos que no hay públicos.
Restricción propia de Colombia: la **telefonía llega a 8 kHz (G.711 μ-law/A-law)**, no a 16 kHz. El esqueleto exige WAV 16 kHz;
la etapa 1 añade un remuestreo 8→16 kHz, y el entrenamiento debe incluir aumento con códec telefónico (si no, el modelo
entrenado con audio de banda ancha falla en producción).

## 3. Arquitectura
```
muestras 16 kHz → log-mel causal (25 ms/10 ms, 64 bandas) → Codificador causal con caché → vector de estado (dim D, norma 1)
                                                              └→ Cabeza tipada ← torres de opción (texto → espacio de audio)
```
- **Log-mel** (`logmel.py`): sin relleno centrado, así que el fotograma t solo ve muestras ya llegadas; `LogMelFlujo` da exactamente lo mismo que el cálculo por lote (test).
- **Codificador** (`codificador.py`): interfaz `Codificador.abrir() → Sesion.empujar(fotogramas) → vector`. Cada trozo (por defecto 32 fotogramas = 320 ms; rango de las notas, 100-500 ms)
  actualiza un estado compartido. El audio se codifica **una vez** por trozo y cada pregunta nueva cuesta un producto punto por opción.
  Candidatos reales: EfficientAT (CNN pequeña, fácil de volver causal con convoluciones causales y caché), Whisper-encoder causal (WhisperRT) o preentrenar con Audio-JEPA. Se decide en la etapa 1 con medidas.
- **Cabeza** (`cabeza.py`): `softmax(cos(audio, torre_opción)/T)`; es el mismo mecanismo que L2 de texto (similitud contra torres de opción), por eso el esquema nuevo funciona sin reentrenar.
  `score` queda como softmax sobre K torres; la pérdida ordinal se añade en la etapa 2. `noul` es `choice` sobre `false`/`true`.
  Si la confianza top-1 < τ: `layer: "escalar"`, `escalate: true`, y `answer`/`probs` son la mejor pista (igual que `decide.Cascada`).
  Sin señal (silencio), `answer: ""` y `probs: {}`, como el servidor cuando ninguna capa opina.
- **Torres de opción**: hoy `TorresFalsas` (hash). Real: el texto de la opción (e5 de Chispa) proyectado al espacio de audio con una cabeza lineal entrenada contra el codificador (alineación tipo CLAP). Sin esa alineación no hay zero-shot sobre audio: es el riesgo central.
- **Streaming** (`flujo.py`): una `Lectura` por trozo. `Flujo.decision(i)` solo contesta si las últimas `acuerdo` lecturas (3 por defecto) coinciden y ninguna escaló, como DJ R3X. La compuerta de silencio evita decidir sobre nada.
- **Latencia y CPU (objetivos, sin medir)**: respuesta ≤ 500 ms desde el final del trozo; codificador ≤ 40 ms por trozo de 320 ms en 1 hilo del i7-8700T / 4 vCPU (≤ 12 % de un núcleo por llamada, ≈ 8 llamadas por núcleo); cabeza < 1 ms por pregunta. Exportar a ONNX int8 y correr con ORT, que es lo que ya usa Chispa; las notas piden OpenVINO (VibeVoiceNix): vale para medir en la VM de Python, pero **el servidor Go de Chispa no lo usa**, así que el entregable es ONNX.
- **Híbrido (opcional)**: la transcripción parcial de whisper pasa por la cascada de texto ya existente; las dos señales se combinan por `acuerdo` o con una cabeza conjunta (como `CONJ`). No requiere cambios en el contrato de texto.

## 4. Encaje con `/v1/decide` y el `.chispa`
**Incompatibilidades con lo actual (la hipótesis se refuta en parte):**
1. `/v1/decide` recibe `state` (string ≤ 256 KiB), rechaza campos desconocidos con 400 y su cascada L0 (TF-IDF) → L1 (Model2Vec) → L2 (e5) es de texto: **el audio no entra por L0/L1/L2**. El audio es una cascada paralela.
2. Una petición en streaming no cabe en un POST de un solo cuerpo: hace falta flujo (WebSocket o HTTP troceado).
3. Las notas dicen «reutiliza las torres, cabezas y calibración» de Chispa: las torres de texto sí, pero necesitan la proyección al espacio de audio; el L2 actual no sirve tal cual.

**Propuesta:**
- **Endpoint nuevo `POST /v1/decide-audio`** (lote: WAV 16 kHz ≤ 30 s en base64 o multipart) y **`GET /v1/decide-audio/stream`** (WebSocket, trozos PCM). Mismas `questions`; el resultado por pregunta tiene **exactamente** las claves de `/v1/decide`, con `layer ∈ {A1, escalar}` más `t_ms` por lectura en el flujo. `/v1/decide` no cambia (contrato congelado).
- **Sección nueva `AUDIO` en `.chispa` (tipo 10, al final del enum, sin renumerar; los ficheros sin ella cargan igual, como pasó con `CONJ`/`L0TF`/`TORR`)**: versión, `dim`, `n_mels`, fotogramas por trozo, τ y T, proyección de torres, y el ONNX int8 del codificador (patrón de `TORR`). La torre de un esquema nuevo se calcula con la `TORR` de texto y se proyecta con la matriz de `AUDIO`. Esto lo hace la sesión principal con `format/chispa3`; aquí no se toca.
- La calibración se guarda en `CALIB`, como hoy.

## 5. Datos públicos candidatos
Licencias de memoria, **sin verificar ni descargar nada**; hay que leer la licencia de cada conjunto antes de usarlo. Regla del esquema de filas: `uso_comercial: false` solo a `test`.
| Conjunto | Uso | Licencia (a verificar) | ¿Entrenar con fines comerciales? |
|---|---|---|---|
| Common Voice (es) | habla en español, aumento | CC0 | sí |
| OpenSLR 72 (español colombiano) | acento colombiano | CC BY-SA 4.0 | sí, con atribución y compartir igual |
| Multilingual LibriSpeech (es) | habla | CC BY 4.0 | sí |
| Speech Commands | órdenes cortas | CC BY 4.0 | sí |
| MUSAN | ruido/música/habla para aumento | mayoría CC BY 4.0 | sí, revisar partes |
| FSD50K | sonidos | por clip: CC0/CC BY/CC BY-NC | solo clips no NC |
| AudioSet | etiquetas de sonido | etiquetas CC BY 4.0; el audio es de YouTube, sin redistribución | no es claro |
| CREMA-D | emoción actuada (inglés) | ODbL | probable, verificar |
| MELD | emoción (Friends) | GPL-3.0 y material con copyright | no |
| RAVDESS | emoción actuada | CC BY-NC-SA 4.0 | no (solo evaluar) |
| IEMOCAP, MSP-Podcast | emoción | licencia académica | no |
| CALLHOME/Fisher español (LDC) | telefonía real | de pago | no |
Hueco grave: **no hay corpus público de llamadas colombianas con etiquetas de emoción o intención**. La emoción en español colombiano exigirá grabar y etiquetar datos propios (con consentimiento) o sintetizar con TTS y códec telefónico; ambas cosas son decisiones de Juan, no de esta fase.

## 6. Métrica y listón
- Métricas por tipo: choice → exactitud y F1 macro; noul → AUC y F1; score → error absoluto medio y kappa ponderado; todas con **ECE** y Brier. Latencia p50/p95 por trozo y CPU por llamada. Medir además la tasa de escalada y la exactitud **cuando no escala**.
- **Listón (notas)**: (a) EfficientAT con etiquetas fijas en la misma CPU; (b) whisper en streaming + Jev (o la cascada de texto de Chispa) para preguntas semánticas; DJ R3X como referencia de latencia (mediana 197 ms de transcripción a orden). Criterio de las notas: si el Jev de audio no gana a (a) o (b) en mAP por latencia o en calibración, **no compensa**. Criterio de éxito del prototipo: ECE < 0,1 en validación.
- Aviso: (a) y (b) responden preguntas distintas (etiquetas fijas vs semánticas); se comparan cada una en su terreno. Comparar solo en emoción actuada en inglés no dice nada de llamadas colombianas: el conjunto de evaluación final debe ser telefónico y en español.

## 7. Plan por etapas
| Etapa | Entregable | Criterio medible |
|---|---|---|
| 0 (esta) | Diseño + esqueleto, tests unittest con audio sintético | tests en verde en la VM con numpy; `a_dict()` con las claves de `/v1/decide` |
| 1 Listón | Tabla de (a) y (b) en la CPU de producción, con remuestreo 8→16 kHz | p50/p95, aciertos y coste por referencia, guardados; decisión continuar/parar |
| 2 Prototipo | Codificador causal pequeño + torres proyectadas, entrenado con CE + Brier (+ pérdida ordinal para `score`) sobre 3 preguntas (emoción, ¿orden?, hablante) | ECE < 0,1 en validación; ≤ 40 ms por trozo en 1 hilo; salida causal verificada (el prefijo no cambia) |
| 3 Zero-shot | Esquemas no vistos en entrenamiento | exactitud zero-shot ≥ listón (b) en preguntas semánticas, o se documenta que no |
| 4 Servidor | `AUDIO` en `format/chispa3`, `/v1/decide-audio` y WebSocket, ONNX int8 en ORT | paridad Python↔Go |Δp| < 1e-4 como en L0TF/L2c; p95 por trozo en la VM; `-race` limpio |
| 5 Seguridad al actuar | Acuerdo de k lecturas calibrado | falsos disparos medidos en llamadas reales (objetivo de las notas: 0 en un conjunto de ≥ 300) |

## 8. Esqueleto y límites (esta fase)
`wav.py` (WAV 16 kHz/16 bits con `wave`), `logmel.py`, `codificador.py` (`CodificadorFalso`: proyección aleatoria de la media móvil del log-mel, no aprende nada),
`cabeza.py` (validación con rutas como el 400 del servidor, `Resultado.a_dict()`), `flujo.py`, `tests/test_audio.py`.
`CodificadorFalso` y `TorresFalsas` no tienen significado acústico: los tests comprueban forma, causalidad, equivalencia flujo/lote y contrato, **no calidad**.
Ejecutar: `cd audio && python3 -m unittest discover -s tests -t .` (requiere numpy).
