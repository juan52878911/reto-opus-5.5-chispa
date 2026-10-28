"""toxicity-protests-ES (bgonzalezbustamante): tuits de protestas en Argentina y Chile, `toxicidad` `noul`."""
from .toxicidad_comun import convertir_toxicidad

REPO = "bgonzalezbustamante/toxicity-protests-ES"
CORTO = "tox-protestas"
VARIEDAD = {"Argentina": "ar", "Chile": "cl"}


def convertir(raiz=None):
    return convertir_toxicidad(raiz, REPO, CORTO, "goldstd_protests.csv", lambda r: VARIEDAD.get(r.get("country")))
