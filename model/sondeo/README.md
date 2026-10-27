# Sondeo (T0.2)

Regenerar: `python construir.py . <dir>` con `<dir>` = salida de `dataset.Generate(dir, 1)` de la Arena.

- Tareas: `intencion` (MASSIVE es, 13 intenciones, ≤30 por intención), `toxicidad` (HateCheck es, partido por
  plantilla, 150/150), `whatsapp_comercio` (Arena, dimensión `intencion`: compra/soporte/queja/saludo; las
  otras dimensiones de la Arena tienen <200 ejemplos de test), `herramientas` (212 peticiones escritas a mano,
  15 herramientas + `escalate` = 15,1 %).
- `train_<tarea>.jsonl`: 32 por clase, sin texto repetido con el test; `idx_clase < 8` = subconjunto de k=8.
  Excepciones: `toxicidad` solo tiene 2 clases (32 por clase = 64); en `herramientas` las primeras 14 por
  clase (20 en `escalate`) son semillas a mano y el resto son esas semillas con envoltura de registro.
- «noul» del brief no está definido en el dataset; se usó `test.csv` entero sin los casos con desacuerdo de anotadores.
- Campos extra: `descripciones` (id → frase en español, para zero-shot), `split`, `idx_clase`.
