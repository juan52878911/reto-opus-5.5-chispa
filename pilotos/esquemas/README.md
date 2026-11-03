# Plantillas de esquemas

| Fichero | Preguntas (id · tipo) | Ejemplos (5 por opción) |
|---|---|---|
| [`pqrs.yaml`](pqrs.yaml) | `pqrs_tipo` · choice (petición, queja, reclamo, sugerencia, felicitación); `pqrs_urgencia` · score 1–5; `pqrs_urgencia_cat` · choice (baja, media, alta) | `ejemplos/pqrs_*.csv` |
| [`soporte.yaml`](soporte.yaml) | `soporte_categoria` · choice (facturación, acceso, fallo técnico, uso, cancelación); `soporte_escalar` · noul (¿pasa a una persona?) | `ejemplos/soporte_*.csv` |
| [`ventas.yaml`](ventas.yaml) | `ventas_intencion` · choice; `ventas_etapa` · choice (embudo) | `ejemplos/ventas_*.csv` |

Cada YAML trae varias preguntas con `preguntas: [...]`: se elige una con `--pregunta ID` y sale **un `.chispa` por pregunta**
([`datos.py`](../../sdk/python/chispa/datos.py)). Los textos de los ejemplos son inventados, sin datos de nadie, y se pueden usar tal cual para few-shot:

```
PYTHONPATH=sdk/python python -m chispa train --esquema pilotos/esquemas/pqrs.yaml --pregunta pqrs_tipo \
  --ejemplos pilotos/esquemas/ejemplos/pqrs_tipo.csv --salida pqrs_tipo.chispa --l1 potion.chispa-l1
```

- Adapta las descripciones al vocabulario de la empresa (EPS: «autorización», «IPS», «tutela»; comercio: «pedido», «garantía»). En zero-shot son lo único que Chispa ve de la tarea.
- Cambia los ejemplos por mensajes reales anonimizados en cuanto los haya ([`datos-y-consentimiento.md`](../datos-y-consentimiento.md)).
- Los ids de opción (`peticion`, `queja`…) no llevan tildes ni espacios; no los cambies sin cambiar los CSV.
- Con 5 ejemplos por opción (< 10) `chispa train` no entrena L0 y calibra L1 con esos ejemplos; la calibración es ruidosa ([`docs/02`](../../docs/02-inicio-rapido.md#3-few-shot-k-ejemplos-por-opción)).
- `pqrs_urgencia` (score): L1 ya opina sobre los niveles, ya no escala siempre. Para que decida, escribe una descripción por nivel que diga cómo se reconoce en un mensaje (nivel 1: «puede esperar, sin plazo ni daño»; nivel 5: «riesgo inmediato, plazo legal vencido o tutela»), con vocabulario distinto entre niveles y con los niveles en orden de menor a mayor. Niveles sin descripción o con textos casi iguales no se distinguen y el caso escala. Resto del pendiente de producto: [`../README.md`](../README.md#pendiente-de-producto).
- `soporte_escalar` es `noul`: sus opciones son exactamente `"true"` y `"false"` (entre comillas en el YAML para que no se lean como booleanos).
- Verificados en este nodo: los 3 YAML cargan con `cargar_esquema` y los 7 CSV pasan `validar` (cada opción con 5 ejemplos).
  Con esas plantillas y 5 ejemplos por opción, `chispa train` **no** entrena L0 (< 10) y sin `--l1` no sale ninguna capa; para el few-shot con L0 hacen falta ≥ 10 por opción (ver [`../despliegue-minimo.md`](../despliegue-minimo.md)).
  La ruta con L0 se entrenó, unió y sirvió con datos sintéticos (dos preguntas de tres y dos opciones, 12 ejemplos por opción); las plantillas de este directorio no se entrenaron con potion (no está en el repo).
