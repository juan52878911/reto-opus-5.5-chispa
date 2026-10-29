"""Genera paridad_textos.json: textos de torre (L2) de model/l2/modelo.py (texto_opcion/texto_consulta) y textos de L1 de
sdk/python/chispa/multi.py (texto_opcion, el de chispa train). Uso: python gen_paridad.py <raíz del repo> > paridad_textos.json"""
import json, sys
raiz = sys.argv[1]
sys.path.insert(0, raiz + "/model/l2"); sys.path.insert(0, raiz + "/sdk/python")
import modelo
from chispa import multi

class O:
    def __init__(s, i, d): s.id, s.description = i, d
class Q:
    def __init__(s, q, ops): s.question, s.options = q, [O(i, d) for i, d in ops]

CASOS = [
 ("choice", "¿Qué quiere el cliente?", [("fraude", "cargo no reconocido"), ("saldo", ""), ("tarjeta", "bloqueo o reposición")]),
 ("choice", "Intención", [("b", ""), ("a", ""), ("c", "")]),
 ("choice", "Tema del mensaje", [("zeta", "última"), ("alfa", "primera"), ("medio", "")]),
 ("choice", "¿Es spam?", [("sí", "publicidad no pedida"), ("no", "")]),
 ("choice", "Idioma: ¿ñandú · ¿qué?", [("es", "español"), ("en", "inglés")]),
 ("choice", "Una sola", [("única", "")]),
 ("choice", "", [("x", "d")]),
 ("noul", "¿Hay una queja?", [("false", ""), ("true", "")]),
 ("noul", "¿Contiene datos personales?", [("true", "nombre, cédula o teléfono"), ("false", "")]),
 ("noul", "¿Es urgente?", [("true", ""), ("false", "no")]),
 ("noul", "¿Odio?", [("false", "no hay"), ("true", "sí hay")]),
 ("score", "Gravedad", [("1", ""), ("2", ""), ("3", "")]),
 ("score", "Gravedad desordenada", [("3", "alta"), ("1", "baja"), ("2", "media")]),
 ("score", "Diez niveles", [("2", ""), ("10", "máximo"), ("9", "")]),
 ("score", "Satisfacción", [("5", "muy satisfecho"), ("4", ""), ("3", ""), ("2", ""), ("1", "nada")]),
 ("multi", "Etiquetas del ticket", [("pago", "problemas de pago"), ("envío", ""), ("cuenta", "acceso")]),
 ("multi", "Temas", [("b", ""), ("a", "")]),
 ("multi", "Un tema", [("t", "d")]),
 ("choice", "Descripción con espacios", [("op", "  con espacios  "), ("otra", "")]),
 ("choice", "Pregunta con salto\nde línea", [("a", "x\ty"), ("b", "")]),
]
out = []
for kind, preg, ops in CASOS:
    fila = {"pregunta": preg, "opciones": [i for i, _ in ops], "descripciones": {i: d for i, d in ops if d}, "tipo": kind}
    # multi se trata como choice (una torre por opción)
    if kind in ("noul", "score"):
        torre = [modelo.texto_consulta(fila)]
    else:
        torre = [modelo.texto_opcion(fila, i) for i, _ in ops]
    q = Q(preg, ops)
    out.append({"kind": kind, "pregunta": preg, "opciones": [{"id": i, "description": d} for i, d in ops],
                "torre": torre, "l1": [multi.texto_opcion(q, o) for o in q.options]})
json.dump(out, sys.stdout, ensure_ascii=False, indent=1)
