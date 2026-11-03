Fixtures de `decide/caida_unido_test.go`: el L0 de cada pregunta de Caída (`colocacion`, `riesgo`, `completa`) y 30 turnos.

Regenerar, desde la raíz del repositorio (n = 60: con ≥ 10 ejemplos por opción se entrena L0):

    (cd demos/caida && python3 -m caida.entrenar_fewshot --salida /tmp/fs --n 60)
    for q in colocacion riesgo completa; do
      PYTHONPATH=sdk/python python3 -m chispa train --ejemplos /tmp/fs/ejemplos-$q.jsonl \
        --esquema /tmp/fs/esquema-$q.json --salida server/testdata/caida/$q.chispa
    done

`turnos.json`: cada sexto ejemplo (10 por pregunta) con el esquema de `esquema-<q>.json` (`estado` es el texto del ejemplo).
