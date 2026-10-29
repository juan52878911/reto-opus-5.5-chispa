# G.5 Exportar la torre de esquemas de L2 a ONNX int8

## Antecedentes
Hoy `chispa-server` no puede decidir con L2 sobre un esquema que no venga en el `.chispa`: las torres solo existen
precalculadas en ESQUEMAS. Para el multipropósito hace falta calcularlas al vuelo. El contrato está en
`model/l2/contrato-torre.md`: léelo primero, porque manda sobre este brief. La sesión de SDK hace el lado Go a partir
de ese contrato.

Ya existe `model/l2/exportar.py`, que genera el ONNX de la consulta (e5 + ranuras → S): int8 por canal, solo del
codificador, con la tabla del vocabulario podado dentro del grafo y con paridad.

## Hipótesis
Un segundo ONNX, el de la torre (`input_ids` y `attention_mask` → `h` (B,256) normalizada), cuantizado int8 por canal
solo en e5, cumple:
- coseno medio ≥ 0,999 con la `h` de PyTorch fp32;
- con torres al vuelo, top-1 en choice ≥ 0,98 frente a las torres de PyTorch;
- tamaño ≤ 50 MB si comparte el vocabulario podado.

Se refuta midiendo.

## Terminado cuando
- `model/l2/exportar.py --torre-onnx SALIDA` exporta la torre siguiendo el contrato al pie de la letra: nombres, prefijo
  «passage: », truncado a 128 y GELU erf.
- La paridad se mide con e5 de `~/hf` y un checkpoint con pesos aleatorios y semilla fija, porque aquí no hay el real. La
  fidelidad de e5 y de la torre no depende de que estén entrenados.
  - Coseno medio y mínimo de `h` en 300 textos de las tareas del golden.
  - Acuerdo top-1 de choice usando las S del ONNX de consulta con torres ONNX, frente a torres PyTorch.
  - Tabla en `model/l2/resultados/torre-onnx/LEEME.md`.
- Un fixture de paridad para Go en `model/l2/tests/fixtures_torre/` (≤ 200 KB): 20 textos, sus ids de entrada y la `h`
  esperada. Así la sesión de SDK prueba su runtime sin PyTorch.
- Tests en `model/l2/tests/test_exportar_torre.py`.
- `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde, **después** del último cambio.
- Si algo del contrato es inexacto, corrige `contrato-torre.md` en un commit aparte y dilo en el informe.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `model/l2/exportar.py`, `model/l2/contrato-torre.md`, `model/l2/tests/**` y `model/l2/resultados/torre-onnx/**`.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv` y modelos en `~/hf`. Sin GPU y sin red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 90 min de reloj · ≤ 5 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 10 líneas:
- rama y sha;
- la paridad (coseno y top-1);
- MB;
- si el contrato cambió.
