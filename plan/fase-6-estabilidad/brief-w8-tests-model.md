# W8 Dos fallos reales de tests en `model/l2` vistos en el clon limpio (VF19)

## Antecedentes
La verificación en clon limpio de la otra sesión (VF19, `sdk` `fb1db4d`, ya en tu base) vio dos fallos reales en `model/l2`.
Los otros tres que salen son de red (HuggingFace) y no se tocan.
1. **`model/l2/tests/test_r9_claves.py::test_fixture_r9_al_dia`.** La fixture difiere en el último dígito de un float.
   Sospecha: el valor se regenera con aritmética que depende de la CPU o de FMA y se compara con igualdad exacta, igual que
   pasó con los dorados del servidor (que se arreglaron guardando el entorno y con tolerancia documentada).
2. **`model/l2/tests/test_t24_exportar.py::test_empaquetar_apaga_el_go_work`.** Espera `-mod=mod` en la orden de Go y sale
   `-buildvcs=false`. Algo cambió en cómo `exportar.py` o `empaquetar_go` arman los flags de `go`.

## Terminado cuando
- **Reproduce cada fallo, explica la causa en el informe y arréglala de raíz:**
  - si la fixture está bien y el test es frágil, compara con la tolerancia adecuada y documenta por qué;
  - si el código está mal, arregla el código.
  - **No regeneres la fixture para que pase** sin explicar por qué el valor nuevo es el correcto.
- `python -m unittest discover -s model -t .` sin fallos, salvo los tres de red, que se listan. `make test` y `make smoke` en
  verde **después** del último cambio.
- Parada: si algo falla 2 veces, márcalo y para. No lances nada en AWS.

## Zona
- `model/l2/**` (salvo `resultados/`).
- No toques `server/`, `sdk/` ni `format/`.
- Rama: la que te da delega. Base: `integracion-limpia`. Commits simples, sin firmas ni `Co-Authored-By`. Sin push ni
  merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, Go en `~/go-sdk/bin` y modelos en `~/hf`. Sin red salvo la API de Claude.

## Tope
- ≤ 40 min de reloj · ≤ 3 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 8 líneas:
- rama y sha;
- causa y arreglo de cada fallo;
- tests.
