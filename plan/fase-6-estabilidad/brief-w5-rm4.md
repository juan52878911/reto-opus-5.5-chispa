# W5 Arreglos de paridad de la revisión RM4 en `model/` (antes del segundo ajuste fino)

## Antecedentes
- La otra sesión revisó W4, en solo lectura, contra el runtime Go. El informe completo, con `fichero:línea` de los dos
  lados, está en `plan/fase-6-estabilidad/rm4/REVISION-RM4.md`. **Léelo entero.**
- Los hallazgos 1, 2, 3, 5 y 6 son de `model/` y tocan la calibración (τ y confianza) y el entrenamiento con soporte. Tienen
  que estar arreglados **antes** del segundo ajuste fino (`model/l2/aws/ajuste.sh`).
- El 4 es del runtime y no se toca aquí.

## Terminado cuando
1. **RM4-1.** `calibrar.py` calcula el τ global con los **mismos parámetros que se escriben en CALIB**: por cabeza, no por
   `(tarea, clave)`. Así la confianza que sirve el runtime es la que eligió τ.
2. **RM4-2, noul.** La confianza y el acierto para τ siguen la regla del runtime: `true` si `pt ≥ θ`, y la confianza es la
   probabilidad de la clase decidida (`pt` si es true, `1 − pt` si es false). Mira `server/decide/l1.go` (solo lectura).
3. **RM4-3, score.** La confianza es `p[etiqueta_coral(p)]`, como `server/decide/l2.go`, no `max(p)`.
4. **RM4-5.** En `modelo.py`, `_ajuste` de score con soporte ordena `sp` por `niveles_score` antes del linspace. Así la
   misma fila da las mismas probabilidades por id con `[1,2,3]` y con `[3,2,1]`.
5. **RM4-6.** El exportador escribe en CALIB **todas** las cabezas score del checkpoint (cualquier K que tenga
   `modelo.coral`), no solo `CABEZAS_L2`.
6. **RM4-7, decisión del orquestador:** Python se alinea con Go. En `normalizar_mayusculas`, la conversión a minúsculas es
   **carácter a carácter, quedándose con el primer punto de código de `c.lower()`**. Así «İ» → «i» y la sigma final da «σ»,
   como `strings.ToLower`.
   - Añade esos dos casos a `model/l2/tests/fixtures/normalizacion.json` (pasará a 15 casos) y actualiza el conteo del test y
     `contrato-normalizacion.md`.
   - Comprueba que los 13 casos anteriores no cambian.
7. **Un test por hallazgo, que falle antes del arreglo y pase después.** En el 2 y el 3, con los ejemplos numéricos del
   informe:
   - θ = 0,3 y pt = 0,4 → true con confianza 0,40;
   - p = [.40, .15, .45] → nivel «2» con confianza 0,15.
8. **Prueba en seco** de `model/l2/aws/ajuste.sh` y de `model/l2/aws/estabilidad.sh` (`CHISPA_LOCAL=1`), sin `FALLO`.
9. `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde **después** del último cambio. Si
   `make smoke` falla por un puerto ocupado, repítelo una vez y anótalo.
- Parada: si algo falla 2 veces, márcalo y para. **No lances nada en AWS.**

## Zona
- `model/l2/**` (salvo `resultados/`) y `model/datos/comun.py`.
- No toques `server/`, `sdk/` ni `format/`.
- Rama: la que te da delega. Base: `integracion-limpia`. Commits simples, sin firmas ni `Co-Authored-By`. Sin push ni
  merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, Go en `~/go-sdk/bin`, modelos en `~/hf` y datos en `~/datos`. Sin red salvo la
  API de Claude.

## Tope
- ≤ 75 min de reloj · ≤ 5 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 10 líneas:
- rama y sha;
- cada hallazgo con su arreglo y su test;
- la tabla de `estado.tsv` de las dos pruebas en seco.
