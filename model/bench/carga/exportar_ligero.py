"""model.l2.exportar en tres procesos, para que quepa en la VM de 2,5 GB.

Cuantizar dentro del proceso del export (torch + 3 copias de e5) pasa de 2 GB y el kernel lo mata (OOM). Aquí:
  1. `fase1`: el export de siempre (E.main) con `cuantizar` y `empaquetar` interceptadas: deja l2-fp32.onnx y los JSON
     de META, ESQUEMAS y CALIB en TRABAJO y sale (sin torch en la fase 2);
  2. `fase2`: cuantiza con la misma función `E.cuantizar` (sola, ~1,1 GB) y empaqueta con `E.empaquetar` (`empaquetar_go`).

    python exportar_ligero.py RAIZ <los argumentos de model.l2.exportar, con --trabajo y --salida>
"""
import json
import os
import subprocess
import sys

RAIZ = sys.argv[1]
sys.path.insert(0, RAIZ)


def arg(nombre, args):
    return args[args.index(nombre) + 1]


def fase1(args):
    import model.l2.exportar as E
    trabajo = arg("--trabajo", args)

    def cuantizar(fp32, int8, modo="codificador", per_channel=True):
        pass

    def empaquetar(meta, onnx, esquemas, calib, salida):
        for n, c in (("meta", meta), ("esquemas", esquemas), ("calib", calib)):
            json.dump(c, open(os.path.join(trabajo, n + ".json"), "w"))
        sys.exit(0)

    E.cuantizar, E.empaquetar = cuantizar, empaquetar
    E.main(args)


def fase2(args):
    import model.l2.exportar as E
    trabajo, salida = arg("--trabajo", args), arg("--salida", args)
    fp32, int8 = os.path.join(trabajo, "l2-fp32.onnx"), os.path.join(trabajo, "l2-int8.onnx")
    E.cuantizar(fp32, int8, "codificador", True)
    J = lambda n: json.load(open(os.path.join(trabajo, n + ".json")))
    E.empaquetar(J("meta"), int8, J("esquemas"), J("calib"), salida)
    print("l2: %.1f MB int8 (%.1f MB fp32), %s: %.1f MB" % (os.path.getsize(int8) / 1e6, os.path.getsize(fp32) / 1e6,
                                                         salida, os.path.getsize(salida) / 1e6))


if __name__ == "__main__":
    args = sys.argv[3:]
    if sys.argv[2] == "fase1":
        fase1(args)
    elif sys.argv[2] == "fase2":
        fase2(args)
    else:
        for f in ("fase1", "fase2"):
            subprocess.run([sys.executable, os.path.abspath(__file__), RAIZ, f, *sys.argv[2:]], check=True)
