"""Empaqueta el entrenador de Go con las fuentes de `format/chispa3` y `runtime/l1` (sin tests) como datos del paquete,
para que `chispa train` compile sin el repositorio al lado. Se copian al construir desde el repositorio."""
import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.command.sdist import sdist

AQUI = Path(__file__).resolve().parent
VENDOR = AQUI / "chispa" / "entrenador_go" / "vendor"
FUENTES = {"chispa3": AQUI / "../../format/chispa3", "l1": AQUI / "../../runtime/l1"}


def copiar_fuentes():
    for nombre, origen in FUENTES.items():
        if not (origen / "go.mod").is_file():
            continue  # sdist/arbol sin repo: se usa lo ya copiado, si hay
        destino = VENDOR / nombre
        shutil.rmtree(destino, ignore_errors=True)
        destino.mkdir(parents=True)
        for f in origen.glob("*.go"):
            if not f.name.endswith("_test.go"):
                shutil.copy(f, destino / f.name)
        for f in ("go.mod", "go.sum"):
            if (origen / f).is_file():
                shutil.copy(origen / f, destino / f)


class BuildPy(build_py):
    def run(self):
        copiar_fuentes()
        super().run()


class Sdist(sdist):
    """Genera `vendor` antes de listar ficheros: así el .tar.gz lo lleva y el wheel construido desde él también."""

    def run(self):
        copiar_fuentes()
        super().run()


setup(cmdclass={"build_py": BuildPy, "sdist": Sdist})
