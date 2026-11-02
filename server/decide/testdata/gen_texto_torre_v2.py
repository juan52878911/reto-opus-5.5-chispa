"""Genera texto_torre_v2.json: textos de torre v1 y v2 (META.texto_torre «v1» / «v2_sin_id») por caso.
Uso: python gen_texto_torre_v2.py <raíz del repo> > texto_torre_v2.json

v1 es texto_opcion/texto_consulta de model/l2/modelo.py. Esa referencia aún no tiene v2, y aquí se implementa la regla
del contrato (model/l2/contrato-torre.md, «Texto de torre versión 2») en este generador: si strip(descripción) no está
vacía, «passage: » + pregunta + « · » + descripción (la descripción tal cual); si está vacía, el texto v1 exacto.
modelo.py importa torch: si se puede importar se comprueba que su v1 coincide con la copia local; si no, se usa la copia."""
import json, sys

SEP = " · "

def v1(fila, op):  # copia literal de modelo.texto_opcion
    return "passage: %s%s%s%s%s" % (fila["pregunta"], SEP, op, SEP, fila["descripciones"].get(op, ""))

def v2(fila, op):
    d = fila["descripciones"].get(op, "")
    if d.strip():
        return "passage: %s%s%s" % (fila["pregunta"], SEP, d)
    return v1(fila, op)

def consulta(fila, f):  # texto_consulta: «true» en noul, el nivel máximo en score
    if fila["tipo"] == "noul":
        return [f(fila, "true")]
    if fila["tipo"] == "score":
        return [f(fila, str(max(int(o) for o in fila["opciones"])))]
    return [f(fila, o) for o in fila["opciones"]]

try:
    sys.path.insert(0, sys.argv[1] + "/model/l2")
    import modelo
    REF = modelo.texto_opcion
except Exception:
    REF = None

CASOS = [
 ("choice", "¿Qué quiere el cliente?", [("fraude", "cargo no reconocido"), ("saldo", ""), ("tarjeta", "bloqueo o reposición")]),
 ("choice", "Solo descripciones", [("a", "primera"), ("b", "segunda")]),
 ("choice", "Sin ninguna", [("a", ""), ("b", "")]),
 ("choice", "Solo espacios", [("a", "   "), ("b", "\t\n"), ("c", "  "), ("d", "\x1c\x1f"), ("e", "x")]),
 ("choice", "Espacios alrededor", [("op", "  con espacios  "), ("otra", "")]),
 ("choice", "Acentos y ñ: ¿qué pasó?", [("español", "señal · año nuevo"), ("sí", "café, ñandú"), ("日本", "日本語")]),
 ("choice", "", [("x", "d")]),
 ("choice", "Salto\nde línea", [("a", "x\ty"), ("b", "")]),
 ("multi", "Etiquetas del ticket", [("pago", "problemas de pago"), ("envío", ""), ("cuenta", "acceso"), ("v", "  ")]),
 ("noul", "¿Contiene datos personales?", [("false", "no"), ("true", "nombre, cédula o teléfono")]),
 ("noul", "¿Es urgente?", [("true", ""), ("false", "no")]),
 ("noul", "¿Odio?", [("true", "   "), ("false", "no hay")]),
 ("score", "Gravedad", [("1", "baja"), ("2", "media"), ("3", "alta")]),
 ("score", "Satisfacción desordenada", [("5", "muy satisfecho"), ("4", ""), ("1", "nada"), ("3", ""), ("2", "")]),
 ("score", "Máximo sin descripción", [("2", " "), ("1", "bajo")]),
]
out = []
for kind, preg, ops in CASOS:
    fila = {"pregunta": preg, "opciones": [i for i, _ in ops], "descripciones": {i: d for i, d in ops if d}, "tipo": kind}
    t1, t2 = consulta(fila, v1), consulta(fila, v2)
    if REF is not None:
        assert t1 == consulta(fila, REF), "v1 local ≠ modelo.texto_opcion"
    out.append({"kind": kind, "pregunta": preg, "opciones": [{"id": i, "description": d} for i, d in ops],
                "v1": t1, "v2_sin_id": t2})
json.dump(out, sys.stdout, ensure_ascii=False, indent=1)
print()
