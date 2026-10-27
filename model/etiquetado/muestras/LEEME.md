# Muestras para etiquetar

## lote-1.jsonl (T1.5b)

1113 filas, solo `split: test`, estratificadas por clase. Conserva la columna `etiqueta` (para medir);
la herramienta `etiquetar.html` la oculta. Parseo comprobado con `parseJSONL` de la herramienta (node): 1113 filas, 0 errores.

Generado con semilla 7 y 300 por tarea:

```
python -m model.datos.convertir --salida /tmp/conv
python -m model.etiquetado.preparar --entrada model/sondeo/whatsapp_comercio.jsonl model/sondeo/intencion.jsonl \
  model/herramientas/test.jsonl /tmp/conv/hatecheck.jsonl --por-tarea 300 --semilla 7 \
  --salida model/etiquetado/muestras/lote-1.jsonl
```

Los ids de los sondeos (que no los traen) son `<fichero>:<split>:<n>`, con n desde 0 en el orden del fichero,
igual que `chispa_eval.asignar_ids` (misma función; test en `tests/test_etiquetado.py`).

| tarea | filas | clases |
|---|---|---|
| whatsapp_comercio | 213 (todas las del test: hay menos de 300) | compra 54, queja 54, soporte 53, saludo 52 |
| intencion | 300 | 12 clases de 23 y alarm_set 24 (13 clases) |
| herramientas | 300 | escalate 9; 31 clases de 9-10 |
| toxicidad (HateCheck-ES) | 300 | true 196, false 104 (todas las false) |
| pqrs | fuera de este lote (no hay test) | - |

Todas las clases del test quedan representadas en cada tarea.
