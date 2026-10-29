# G.3 Modo por defecto multipropósito: la cabeza conjunta y L0 TF-IDF pasan a opcionales

## Antecedentes
Juan quiere un producto multipropósito, como Laya o Jev. La cabeza conjunta (CONJ) y L0 TF-IDF (L0TF) necesitan train
etiquetado de cada tarea. Deben quedar como modo opcional «con datos del cliente», no como el camino por defecto. Hoy:
- `docs/02-inicio-rapido.md` lleva a `chispa train --conjunta`;
- `chispa-server` usa CONJ y L0TF si el `.chispa` los trae.

## Hipótesis
Sin cambiar el comportamiento cuando hay datos, el camino por defecto queda así:
1. **Zero-shot:** L2 con esquema y sin ejemplos, para decidir sobre un esquema nunca visto con solo la pregunta y las
   opciones.
2. **Few-shot:** `chispa train` sin `--conjunta`.
3. **Con datos del cliente:** `--conjunta`.

Se refuta si el servidor no puede servir un esquema nuevo sin un `.chispa` entrenado para él.

## Terminado cuando
- **Leer y decir qué pasa hoy:**
  - ¿`chispa-server` decide sobre un esquema que llega en la petición y que ningún `.chispa` trae, usando solo L2 (torres
    calculadas al vuelo) y L1-zs?
  - Si no puede, ¿qué falta? Mira `server/decide/l2.go`, `l1.go` y `modelo.go`, y la caché de esquemas.
- **Si falta poco** (calcular la torre de un esquema nuevo con el ONNX y cachearla): impleméntalo, con tests usando un
  codificador falso.
- **Si es grande:** descríbelo en `docs/` como trabajo pendiente y no lo implementes.
- **`docs/`:** reordena el inicio rápido en los tres modos (zero-shot, few-shot y con datos del cliente), cada uno con sus
  cifras medidas y sus límites. Cita como pruebas de funcionalidad massive, clinc y las demás, no como objetivo.
- **`chispa train`:** que `--conjunta` diga en su ayuda que es el modo «con datos del cliente» y necesita train
  etiquetado.
- **Tests:** Go y Python en verde. El venv y Go están en `~/orquestador/herr` (`. ~/orquestador/herr/env.sh`); corre a
  mano las recetas de `make`.
- **Parada:** si algo falla 2 veces, márcalo y para.

## Zona
- `server/decide/**`, `docs/**` y `sdk/python/chispa/cli.py` (solo la ayuda).
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Tope
- ≤ 90 min de reloj · ≤ 6 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 10 líneas:
- rama y sha;
- qué pasaba hoy con un esquema nuevo;
- qué implementaste o qué quedó descrito.
