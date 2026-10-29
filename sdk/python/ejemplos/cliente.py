"""Cliente de /v1/decide con el esquema de ferretería. Necesita un chispa-server cargado con un .chispa
(ver docs/02-inicio-rapido.md):

    python cliente.py [--url http://127.0.0.1:8090] ["texto a clasificar"]
"""
import argparse
import sys

from chispa import Choice, Chispa, ChispaError

OPCIONES = [
    ("cotizacion", "pide precio o disponibilidad de un producto, o una cotización de materiales"),
    ("pedido", "quiere comprar y recibir productos, o pregunta por el estado de un pedido ya hecho"),
    ("garantia", "reclama por una herramienta defectuosa, un cambio o una devolución"),
    ("asesoria", "pide ayuda técnica para elegir o usar un material o una herramienta"),
    ("factura", "pide una factura, un RUT o corregir datos de facturación"),
]

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--url", default="http://127.0.0.1:8090")
ap.add_argument("texto", nargs="?", default="Buenas, ¿cuánto vale el bulto de cemento gris de 50 kg y tienen hoy?")
a = ap.parse_args()

try:
    r = Chispa(a.url, reintentos=1).decidir(
        a.texto, [Choice("q1", "¿Qué necesita la persona que escribe a la ferretería?", OPCIONES)])[0]
except ChispaError as e:
    sys.exit(f"cliente: {e} (¿está chispa-server en {a.url}?)")
print(f"{r.answer} (capa {r.layer}, escalar: {r.escalate})")
for op, p in sorted(r.probs.items(), key=lambda kv: -kv[1]):
    print(f"  {op:11s} {p:.3f}")
