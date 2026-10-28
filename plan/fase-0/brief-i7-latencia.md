# Latencia en el i7-8700T (pve): e5-small int8 podado y runtime L1

Encargo: `plan/fase-0/encargo.md`. Es la regla de p99 < 50 ms a 64 tokens, que el criterio (b) de G1
y la parte de latencia de G2 heredan.

Ya hay cifras de sustitutos:
- i3 de kindling, sin AVX2: 200 ms;
- c6a en AWS, con AVX2: 19,3 ms;
- c6i, con VNNI: 10,7 ms.

Esto cierra la medida en el hardware objetivo. Corres en el nodo `kindling-pve-personal`: una microVM
de 2,5 GB en un contenedor de 4 GB sobre el i7-8700T. Ese host comparte máquina con otras VM (AuraCRM,
nodo-c), así que **habrá ruido**.

## Hipótesis
- En el i7, e5 int8 podado da p99 < 50 ms a 64 tokens con 1 hilo: entre 19 y 35 ms, porque el i7
  sostiene menos frecuencia que el EPYC.
- L1 (`runtime/l1`) da p99 < 1 ms a 64 tokens.
- Se refuta midiendo.

## Terminado cuando
- `model/bench/codificadores.py`, con las variables que ya admite (`CHISPA_WORK`, `CHISPA_REPS`,
  `CHISPA_SALIDA`), solo para e5-small, sin mmBERT ni potion en esta tabla:
  - variantes: int8 podado (la que importa), fp32 podado y fp32 sin podar;
  - 16, 64 y 256 tokens, con 1 y 4 hilos;
  - 20 de calentamiento y ≥ 300 repeticiones;
  - **tres tandas** separadas por 1 min, informando la mediana de los p99 y su rango, por el ruido del host.
- L1:
  - exporta el `.chispa-l1` de `minishlab/potion-multilingual-128M` con `runtime/l1/exportar.py`
    (está en `~/hf`) a `/tmp`;
  - comprueba el hash del cuerpo (`01fe1e57dc1bb1917757723e35264b146c25c4d81a3950a8ec7bb0f6a4ba8808`);
  - corre `runtime/l1/cmd/l1medir` a 16, 64 y 256 tokens, también en tres tandas.
- Anota `lscpu` (banderas AVX2/FMA), `nproc`, memoria y `/proc/loadavg` antes y después de cada tanda.
- Resultado en `model/bench/i7/resultados.md`, con una tabla comparativa:

  | Variante | i3 kindling | c6a | c6i | **i7** |
  |---|---|---|---|---|

  Más una frase que diga si el p99 < 50 ms a 64 tokens se cumple en el i7.
- No metas el `.chispa-l1` ni los ONNX en git. `make test` en verde. Esta VM es pequeña: si
  `make smoke` no cabe en memoria, dilo y no lo fuerces.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- Solo `model/bench/i7/`. **No tocar** el resto de `model/bench/` ni `runtime/`; solo se usan.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, Go en `~/go-sdk/bin`, modelos en `~/hf`. No hay red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 75 min de reloj · ≤ 3 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 12 líneas: la rama y el sha, la tabla del p99 a 64 tokens (int8 con 1 y 4
hilos, y L1), el ruido observado y el veredicto.
