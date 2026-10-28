"""toxicity-Constitution-ES (bgonzalezbustamante): tuits sobre la Convención Constitucional de Chile, `toxicidad` `noul`."""
from .toxicidad_comun import convertir_toxicidad

REPO = "bgonzalezbustamante/toxicity-Constitution-ES"
CORTO = "tox-constitucion"


def convertir(raiz=None):
    return convertir_toxicidad(raiz, REPO, CORTO, "goldstd_Convention.csv", lambda r: "cl")
