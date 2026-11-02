# AVISO: este script ya NO es la fuente de texto_torre_v2.json. Ese fichero lo genera model/ (el entrenamiento) y aquí se
# copia tal cual; no se regenera desde este repositorio. Se conserva solo como referencia histórica del formato antiguo
# (lista plana de casos, no el dict {opciones, preguntas} actual).
"""Genera texto_torre_v2.json: textos de torre v1 y v2 (META.texto_torre «v1» / «v2_sin_id») por caso.
Uso: python gen_texto_torre_v2.py <raíz del repo> > texto_torre_v2.json

v1 es texto_opcion/texto_consulta de model/l2/modelo.py. Esa referencia aún no tiene v2, y aquí se implementa la regla
del contrato (model/l2/contrato-torre.md, «Texto de torre versión 2») en este generador: si strip(descripción) no está
vacía, «passage: » + pregunta + « · » + descripción (la descripción tal cual); si está vacía, el texto v1 exacto. Excepción:
las opciones de la misma pregunta cuya descripción (igualdad exacta tras strip(), no vacía; dos o más) se repite usan el texto v1.
modelo.py importa torch: si se puede importar se comprueba que su v1 coincide con la copia local; si no, se usa la copia."""
import json, sys

SEP = " · "

def v1(fila, op):  # copia literal de modelo.texto_opcion
    return "passage: %s%s%s%s%s" % (fila["pregunta"], SEP, op, SEP, fila["descripciones"].get(op, ""))

def repetida(fila, op):
    d = fila["descripciones"].get(op, "").strip()
    return bool(d) and sum(1 for o in fila["opciones"] if fila["descripciones"].get(o, "").strip() == d) >= 2

def v2(fila, op):
    d = fila["descripciones"].get(op, "")
    if d.strip() and not repetida(fila, op):
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
 ("choice", "Dos descripciones iguales", [("a", "pedir ayuda"), ("b", "pedir ayuda"), ("c", "otra cosa")]),
 ("choice", "Iguales salvo espacios en los extremos", [("a", "reclamo"), ("b", "  reclamo\t"), ("c", "\x1creclamo\n"), ("d", "recl amo")]),
 ("choice", "Tres con dos iguales", [("a", "x"), ("b", "y"), ("c", "x")]),
 ("choice", "Tres iguales y una distinta", [("a", "z"), ("b", "z"), ("c", "z"), ("d", "w")]),
 ("choice", "Vacías repetidas no cuentan", [("a", ""), ("b", "  "), ("c", "uno")]),
 ("choice", "Distintas por mayúsculas", [("a", "Saldo"), ("b", "saldo")]),
 ("multi", "Etiquetas repetidas", [("pago", "problema"), ("envío", "problema"), ("cuenta", "acceso"), ("v", "  problema ")]),
 ("noul", "¿Repetida en noul?", [("false", "no hay"), ("true", "no hay")]),
 ("noul", "¿Repetida distinta?", [("false", "otra"), ("true", "datos")]),
 ("score", "Repetidas en score", [("1", "igual"), ("2", "igual"), ("3", "alta")]),
 ("choice", "Espacios Unicode son espacio", [("a", "\u00a0"), ("b", "\u3000"), ("c", "\u2028"), ("d", "\x85"), ("e", "x")]),
 ("choice", "Espacios Unicode alrededor", [("a", "\u00a0saldo\u3000"), ("b", "saldo"), ("c", "\u2028saldo\x85"), ("d", "otra")]),
 ("choice", "U+200B no es espacio", [("a", "\u200b"), ("b", "\u200b"), ("c", "\u200bx"), ("d", "x")]),
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
