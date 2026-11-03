"""Manifiesto de entrenamiento de la alternativa (b): qué conjuntos entran a train y con qué licencia.

Rechaza AL CONSTRUIRSE (`Manifiesto(...)` / `cargar`) cualquier conjunto con licencia SA, NC, ND, «sin verificar»/desconocida o vacía,
con `uso_comercial` distinto de true, o que esté en la lista de exclusión (SIB-200, Clandestino, PQRS de datos.gov.co, blandas de
Qwen3.5, XNLI, clima y ALIA) aunque venga marcado como comercial. Para que el peso se pueda publicar bajo Apache desde el principio,
`entrenar` copia el manifiesto junto al checkpoint (`escribir_junto`).

Los conjuntos de train se sellan (`sellar`: filas y sha256 del fichero) cuando existen los ficheros; `validar(sellado=True)` exige el sello
y que el fichero coincida. `tsjev` no es un fichero fijo: lista las tareas admitidas de `sources.yaml` (`tsjev_tareas`).

    python -m model.alt.manifiesto tsjev [--fuentes sources.yaml]   # tabla de tareas admitidas / excluidas
    python -m model.alt.manifiesto filtrar --entrada DIR... --salida tsjev-admitido.jsonl.gz
"""
import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from model.meta.comun import prohibida
from model.meta.tasksource_jev import censo_yaml

AQUI = Path(__file__).parent
RUTA = AQUI / "manifiesto-entrenamiento.json"

SA = re.compile(r"(^|[^a-z])sa([^a-z]|$)|share[\s-]*alike", re.I)
NC = re.compile(r"(^|[^a-z])nc([^a-z]|$)|non[\s-]*commercial|no[\s-]*comercial", re.I)
ND = re.compile(r"(^|[^a-z])nd([^a-z]|$)|no[\s-]*deriv", re.I)
NO_VERIFICADA = re.compile(r"sin verificar|unspecified|unknown|desconocida|no clara|contradictoria|^\s*$", re.I)
# Exclusión explícita mientras Juan no decida: se compara con nombre, fuente y origen de blandas del conjunto.
EXCLUIDOS = re.compile(
    r"sib-?200|clandestino|pqrs|datos\.gov\.co|qwen|model/maestro|xnli|clima|climate|(^|[^a-z])alia([^a-z]|$)|(^|[^a-z])anli([^a-z]|$)|gliclass", re.I)


class ManifiestoInvalido(ValueError):
    pass


def motivo_licencia(lic):
    """Por qué una licencia no sirve (SA, NC, ND, no verificada) o None. Mira cada componente de «a, b (DPI), c (original source)»."""
    lic = "" if lic is None else str(lic)
    if NO_VERIFICADA.search(lic):
        return "sin verificar"
    for nombre, rx in (("SA", SA), ("NC", NC), ("ND", ND)):
        if rx.search(lic):
            return nombre
    return None


def errores_conjunto(c):
    e = []
    nombre = c.get("nombre") or "?"
    m = motivo_licencia(c.get("licencia"))
    if m:
        e.append("%s: licencia %r no admitida (%s)" % (nombre, c.get("licencia"), m))
    if c.get("uso_comercial") is not True:
        e.append("%s: uso_comercial debe ser true" % nombre)
    for campo in ("nombre", "fuente"):
        if not c.get(campo):
            e.append("%s: falta %s" % (nombre, campo))
    for campo in ("nombre", "fuente", "blandas"):
        x = prohibida_exclusion(c.get(campo))
        if x:
            e.append("%s: %s «%s» está en la lista de exclusión (%s)" % (nombre, campo, c.get(campo), x))
    return e


def prohibida_exclusion(texto):
    if not texto:
        return None
    m = EXCLUIDOS.search(str(texto))
    return m.group(0) if m else None


def sha256(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def contar_filas(ruta):
    import gzip
    ab = gzip.open if str(ruta).endswith(".gz") else open
    with ab(ruta, "rt", encoding="utf-8") as f:
        return sum(1 for l in f if l.strip())


class Manifiesto:
    """Se construye desde un dict (`{"conjuntos": [...]}`); lanza `ManifiestoInvalido` con TODOS los motivos."""

    def __init__(self, datos):
        self.datos = datos
        e = []
        cs = datos.get("conjuntos")
        if not cs:
            e.append("sin conjuntos de train")
        nombres = Counter(c.get("nombre") for c in cs or [])
        e += ["nombre repetido: %s" % n for n, k in nombres.items() if k > 1]
        for c in cs or []:
            e += errores_conjunto(c)
            if c.get("nombre") == "tsjev":
                e += self._errores_tsjev(c)
        if e:
            raise ManifiestoInvalido("; ".join(e))

    @staticmethod
    def _errores_tsjev(c):
        e = []
        for t in c.get("tareas") or []:
            m = motivo_licencia(t.get("licencia"))
            if m or t.get("license_use") != "commercial":
                e.append("tsjev/%s: licencia %r (%s) no admitida" % (t.get("tarea"), t.get("licencia"), m or t.get("license_use")))
            x = prohibida(t.get("tarea"))
            if x or prohibida_exclusion(t.get("tarea")):
                e.append("tsjev/%s: tarea excluida (%s)" % (t.get("tarea"), x or "lista de exclusión"))
        if not c.get("tareas"):
            e.append("tsjev: sin tareas admitidas")
        return e

    @property
    def conjuntos(self):
        return self.datos["conjuntos"]

    def tareas_tsjev(self):
        return {t["tarea"] for c in self.conjuntos if c["nombre"] == "tsjev" for t in c["tareas"]}

    def validar(self, raiz=None, sellado=False):
        """Con `sellado`, cada conjunto debe traer sha256 y filas, y (si hay `raiz`) el fichero debe coincidir."""
        e = []
        for c in self.conjuntos:
            if sellado:
                if not c.get("sha256") or c.get("filas") is None:
                    e.append("%s: sin sellar (filas/sha256)" % c["nombre"])
                elif raiz is not None:
                    f = Path(raiz) / c["fichero"]
                    if not f.is_file():
                        e.append("%s: falta %s" % (c["nombre"], f))
                    elif sha256(f) != c["sha256"]:
                        e.append("%s: sha256 de %s no coincide" % (c["nombre"], f))
        if e:
            raise ManifiestoInvalido("; ".join(e))
        return self

    def sellar(self, raiz):
        """Rellena filas y sha256 de los conjuntos cuyo fichero existe bajo `raiz`."""
        for c in self.conjuntos:
            f = Path(raiz) / c["fichero"] if c.get("fichero") else None
            if f and f.is_file():
                c["filas"], c["sha256"] = contar_filas(f), sha256(f)
        return self

    def escribir_junto(self, directorio):
        directorio = Path(directorio)
        directorio.mkdir(parents=True, exist_ok=True)
        p = directorio / "manifiesto-entrenamiento.json"
        p.write_text(json.dumps(self.datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return p


def cargar(ruta=RUTA):
    return Manifiesto(json.loads(Path(ruta).read_text(encoding="utf-8")))


def verificar_filas(filas, manifiesto=None):
    """Falla si una fila de train (o dev) tiene uso_comercial false, licencia no admitida o es de tarea tsjev no admitida."""
    tsjev = manifiesto.tareas_tsjev() if manifiesto else None
    for r in filas:
        if r.get("split") in ("train", "dev") and r.get("uso_comercial") is not True:
            raise ManifiestoInvalido("fila %s: uso_comercial=false en %s" % (r.get("id"), r.get("split")))
        m = motivo_licencia(r.get("licencia", "")) if "licencia" in r else None
        if m:
            raise ManifiestoInvalido("fila %s: licencia %r (%s)" % (r.get("id"), r.get("licencia"), m))
        if tsjev is not None and str(r.get("id", "")).startswith("tsjev:") and r.get("tarea") not in tsjev:
            raise ManifiestoInvalido("fila %s: tarea tsjev %r no admitida" % (r.get("id"), r.get("tarea")))
    return filas


def tsjev_tareas(fuentes):
    """(admitidas, excluidas, resumen) desde el dict `sources` de sources.yaml.

    Admitida: `license_use == commercial`, licencia sin SA/NC/ND/sin verificar en ninguno de sus componentes, y fuera de la lista
    de exclusión y de GLiClass/XNLI/ANLI. Excluida: lo demás, con el motivo."""
    adm, exc = [], []
    for tarea, f in sorted(fuentes.items()):
        filas = f.get("rows") or {}
        lic = f.get("license")
        motivos = []
        if f.get("license_use") != "commercial":
            motivos.append("license_use=%s" % (f.get("license_use") or "vacio"))
        m = motivo_licencia(lic)
        if m:
            motivos.append(m)
        x = prohibida(tarea, f.get("dataset"), f.get("originals"), list(f.get("revisions") or ()), f.get("data_files_from"),
                      f.get("source_urls"))
        if x or prohibida_exclusion(tarea) or prohibida_exclusion(f.get("dataset")):
            motivos.append("lista de exclusión")
        ficha = {"tarea": tarea, "licencia": lic, "license_use": f.get("license_use"), "filas": dict(filas)}
        if motivos:
            exc.append(dict(ficha, motivos=motivos))
        else:
            adm.append(ficha)
    def suma(xs, split=None):
        return sum(v for x in xs for k, v in x["filas"].items() if split is None or k == split)
    por_motivo = defaultdict(lambda: {"tareas": 0, "filas": 0})
    for x in exc:
        k = "+".join(x["motivos"])
        por_motivo[k]["tareas"] += 1
        por_motivo[k]["filas"] += suma([x])
    resumen = {
        "tareas_total": len(fuentes), "filas_total": suma(adm + exc), "filas_train_total": suma(adm + exc, "train"),
        "tareas_admitidas": len(adm), "filas_admitidas": suma(adm), "filas_train_admitidas": suma(adm, "train"),
        "tareas_excluidas": len(exc), "filas_excluidas": suma(exc), "excluidas_por_motivo": dict(sorted(por_motivo.items())),
        "censo_license_use": censo_yaml(fuentes),
    }
    return adm, exc, resumen


def filtrar_tsjev(rutas, manifiesto, salida):
    """Escribe en `salida` (.jsonl.gz) las filas train/dev de tsjev cuya tarea admite el manifiesto. Devuelve (escritas, descartadas)."""
    import gzip
    from model.l2.datos import iterar
    ok, mal = manifiesto.tareas_tsjev(), 0
    n = 0
    with gzip.open(salida, "wt", encoding="utf-8") as out:
        for r in iterar(rutas):
            if r.get("split") not in ("train", "dev"):
                continue
            if r.get("tarea") in ok and r.get("uso_comercial") is True:
                out.write(json.dumps(r, ensure_ascii=False) + "\n")
                n += 1
            else:
                mal += 1
    return n, mal


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("orden", choices=("tsjev", "validar", "filtrar"))
    ap.add_argument("--entrada", nargs="*", help="orden filtrar: directorios o ficheros de filas tsjev")
    ap.add_argument("--fuentes", help="sources.yaml (por defecto el de ~/hf)")
    ap.add_argument("--salida", help="escribe aquí el JSON de tareas (orden tsjev)")
    a = ap.parse_args(argv)
    if a.orden == "validar":
        m = cargar()
        print("manifiesto válido: %d conjuntos" % len(m.conjuntos))
        return 0
    if a.orden == "filtrar":
        n, mal = filtrar_tsjev(a.entrada, cargar(), a.salida)
        print("tsjev filtrado: %d filas escritas, %d descartadas" % (n, mal))
        return 0
    import yaml
    from model.meta.comun import raiz_hf
    from model.meta.tasksource_jev import REPO
    ruta = Path(a.fuentes) if a.fuentes else raiz_hf(REPO) / "sources.yaml"
    fuentes = (yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}).get("sources") or {}
    adm, exc, res = tsjev_tareas(fuentes)
    out = {"resumen": res, "admitidas": adm, "excluidas": exc}
    if a.salida:
        Path(a.salida).write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
