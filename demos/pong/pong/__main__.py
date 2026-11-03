"""`python -m pong jugar --chispa URL --laya URL --salida traza.json` (o `--optimo` en un lado, para probar) · `python -m pong renderizar …`"""
import argparse
import json
import sys

from .motor import Juego
from .partida import AgenteChispa, AgenteLaya, AgenteOptimo, Partida


def jugar(argv) -> int:
    ap = argparse.ArgumentParser(prog="jugar")
    ap.add_argument("--chispa", help="URL del servidor de Chispa (pala derecha)")
    ap.add_argument("--laya", help="URL de laya_servidor.py (pala izquierda)")
    ap.add_argument("--semilla", type=int, default=1)
    ap.add_argument("--salida", required=True)
    ap.add_argument("--texto", choices=("px", "cualitativo"), default="px", help="redacción de las opciones (la misma para los dos)")
    ap.add_argument("--ritmo", type=float, default=1.0, help="1 = tiempo real (30 tics/s)")
    a = ap.parse_args(argv)
    agentes = {"izquierda": AgenteLaya(a.laya, texto=a.texto) if a.laya else AgenteOptimo(),
               "derecha": AgenteChispa(a.chispa, texto=a.texto) if a.chispa else AgenteOptimo()}
    p = Partida(Juego(a.semilla), agentes, a.semilla, a.texto)
    p.jugar(a.ritmo)
    p.guardar(a.salida)
    print(json.dumps(p.resumen(), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    orden = sys.argv[1] if len(sys.argv) > 1 else ""
    if orden == "jugar":
        raise SystemExit(jugar(sys.argv[2:]))
    if orden == "renderizar":
        from . import renderizar
        raise SystemExit(renderizar.main(sys.argv[2:]))
    if orden == "vertical":
        from . import vertical
        raise SystemExit(vertical.main(sys.argv[2:]))
    print("uso: python -m pong {jugar|renderizar|vertical} …", file=sys.stderr)
    raise SystemExit(2)
