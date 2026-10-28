"""somosnlp/suicide-comments-es: `riesgo_suicida`. Solo si está en ~/hf; hoy no está (FuenteAusente → «no disponible»)."""
from pathlib import Path

from .comun import FuenteAusente, raiz_hf

REPO = "somosnlp/suicide-comments-es"
CORTO = "riesgo-suicida"


def convertir(raiz=None):
    raiz = Path(raiz or raiz_hf(REPO))  # FuenteAusente si no está
    if not raiz.is_dir():
        raise FuenteAusente(REPO)
    raise NotImplementedError("%s está en %s pero su formato no se ha revisado: añadir el conversor" % (REPO, raiz))
