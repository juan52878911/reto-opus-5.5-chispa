# Shrinkage de los prototipos de soporte hacia la descripción (G.8)

Para el runtime en Go y en el móvil. Referencia ejecutable: `model/l2/modelo.py`, `prototipos(..., kappa)` y `mezcla_prototipos`.
Sin cambios en nada más: κ = 0 da exactamente el prototipo de T2.1b.

## Por qué
Con 1 o 2 ejemplos por clase la media de las ranuras es ruido, y `β · simproto` pasa por encima de la torre de la descripción en
lugar de completarla. El shrinkage deja que mande la descripción cuando hay pocos ejemplos y la media cuando hay muchos.

## Entradas (por tarea y por clase c con n_c ≥ 1 ejemplos de soporte)
- `S_i ∈ R^{K×d}` (K = 16, d = 256): ranuras de cada ejemplo i de soporte, ya normalizadas por ranura (salida del ONNX de la
  consulta, como hoy). Para el mensaje de soporte se usa el mismo tokenizador y el mismo truncado que para la consulta
  (`max_len` de la consulta: 256 en G.8; ver abajo).
- `h_c ∈ R^d`, norma 1: la torre de la descripción de la clase, `torre("passage: " + pregunta + " · " + id_c + " · " + descripcion_c)`
  (`texto_opcion` de `modelo.py`; `SEP = " · "`, `descripcion_c` = "" si la tarea no la trae). Es el mismo vector `h` que la caché por
  clave de ESQUEMAS ya guarda para `choice`; en `noul` y `score` hay que pedir también la clase que no es la «consulta»
  (`false`, o los niveles que no son el máximo): sale del mismo ONNX de la torre, un texto por clase.
- `κ ≥ 0`: escalar. `κ = 0` desactiva el shrinkage.

## Fórmula (orden de operaciones)
1. `n_c` = número de ejemplos de soporte de la clase c.
2. `M_{c,k} = (1 / n_c) · Σ_{i ∈ c} S_{i,k}` para cada ranura k. **Media sin normalizar** (su norma es ≤ 1).
3. `λ_c = κ / (κ + n_c)`.
4. `Q_{c,k} = λ_c · h_c + (1 − λ_c) · M_{c,k}`: el mismo `h_c` se suma a las K ranuras.
5. `P_{c,k} = Q_{c,k} / ‖Q_{c,k}‖₂` (por ranura; si la norma es 0, deja el vector en 0).
6. Sin cambios desde aquí: `simproto(S, P)_c = mean_k max_{k'} (S_k · P_{c,k'})`, y la puntuación sigue siendo
   `sim_opción + β_tipo · ajuste(simproto)` con los β de CALIB.

Con κ = 0, λ = 0 y el paso 5 es la media normalizada de siempre. Con κ > 0 y n_c = 1: λ = κ/(κ+1) (0,8 con κ = 4). Con n_c = 32 y
κ = 4: λ ≈ 0,11.

## κ por defecto y dónde va
- **κ por defecto: 4** (el valor del brief). El entrenamiento de G.8 lo mide: `entrenamiento.json` lleva `kappa_dev`
  (rejilla `--elegir-kappa`, macro-F1 de dev con k = 2): `kappa` es el mejor de la rejilla (0 incluido) y `kappa_pos` el mejor
  mayor que 0, que es el que compara general.sh. Si el dev da `kappa` = 0, el shrinkage no ayuda en dev y el runtime puede dejarlo apagado;
  si sale otro κ, ese manda sobre el 4.
- **Basta un campo nuevo en CALIB: `kappa`** (float, ≥ 0), global y no por tipo, con el mismo valor para todas las tareas. En Go:
  `Calib.Kappa *float64 \`json:"kappa,omitempty"\``, con `nil` = 0 (los `.chispa` anteriores siguen igual) y validación
  `kappa ≥ 0 && finito` en `Calib.validar`. No hace falta tocar ninguna sección ni tensor: las torres de las descripciones ya
  se calculan al vuelo.
- Las clases del soporte sin descripción siguen siendo válidas: se usa `texto_opcion` con descripción vacía.

## Convención de λ del runtime (G.8b)

La sesión SDK implementa `p = norm((1−w)·p_desc + w·media_ejemplos)` con `w = k/(k+λ)`, `k` = ejemplos de la clase. Es la fórmula de
G.8 con **κ = λ** (`λ_c` de arriba, el peso de la descripción, es `1−w`; no lo confundas con el `λ` de esta sección). `p_desc` = `h_c`; la media va
sin normalizar. En código, `prototipos(..., kappa=λ)`.

- λ = 0: `w = 1`, solo cuentan los ejemplos (el prototipo de T2.1b).
- λ = ∞: `w = 0`, solo la descripción. **El runtime usa λ = ∞ por defecto: solo la torre de la descripción, es decir, zero-shot** (no se
  construyen prototipos ni se suma `β · simproto`). Es lo que mide `barrido.py` como «λ=∞» (k = 0). `mezcla_prototipos(..., inf)` da
  P = `h_c`, que no es lo mismo que zero-shot: añadiría `β · simproto` con la descripción como prototipo.

| κ = λ | peso de los ejemplos w, n = 1 | n = 2 | n = 8 | n = 32 |
|---|---|---|---|---|
| 0 | 1 | 1 | 1 | 1 |
| 1 | 0,50 | 0,67 | 0,89 | 0,97 |
| 2 | 0,33 | 0,50 | 0,80 | 0,94 |
| 4 | 0,20 | 0,33 | 0,67 | 0,89 |
| 8 | 0,11 | 0,20 | 0,50 | 0,80 |
| 16 | 0,06 | 0,11 | 0,33 | 0,67 |
| ∞ | 0 | 0 | 0 | 0 |

El peso de la descripción (el `λ_c` de la fórmula de arriba) es `1 − w`. Barrido en test: `model/l2/barrido.py` (`aws/barrido.sh`).

## score: etiqueta por la mediana CORAL
La etiqueta predicha de una pregunta `score` es el número de umbrales `j` con `P(y>j) > 0,5` (nivel = cuenta + 1), no el argmax de `P(y=k)`;
coincide con el runtime. Se cuentan todos los umbrales, no el primer cruce, así que vale con acumuladas no monótonas. La confianza para τ sigue
siendo la probabilidad máxima de la distribución.

## Casos límite
- Clase de la tarea sin ningún ejemplo de soporte: sigue sin prototipo (simproto = 0), como hoy; no se inventa uno con la descripción.
- `n_c` grande: λ → 0 y P → media normalizada. Un solo ejemplo con κ muy grande: P → `h_c` en las K ranuras.
- Prototipos cacheados por (tarea, hash del soporte, κ): si cambia κ hay que recalcular.

## Dependencia de max_len
G.8 entrena con `max_tok = 256` (`--max-tok`; el checkpoint lo guarda como `max_tok`). Un `.chispa` exportado de ese checkpoint debe
truncar mensaje y torre a 256, no a 128: `exportar.py` y `contrato-torre.md` (`chispa.torre.max_len`, `max_tok` de la sección de la
consulta) tienen el 128 fijo y quedan fuera de la zona de G.8. **Hay que cambiarlos antes de exportar**.
