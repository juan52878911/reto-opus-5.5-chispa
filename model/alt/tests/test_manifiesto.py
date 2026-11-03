import copy
import json
import tempfile
import unittest
from pathlib import Path

from model.alt import manifiesto as M


def conj(**kw):
    c = {"nombre": "demo", "fuente": "org/demo", "licencia": "cc-by-4.0", "uso_comercial": True, "fichero": "demo.jsonl",
         "filas": None, "sha256": None}
    c.update(kw)
    return c


def man(*cs):
    return {"conjuntos": list(cs)}


class Rechazos(unittest.TestCase):
    def rechaza(self, **kw):
        with self.assertRaises(M.ManifiestoInvalido):
            M.Manifiesto(man(conj(**kw)))

    def test_sa(self):
        self.rechaza(licencia="cc-by-sa-4.0")
        self.rechaza(licencia="CC BY-SA 4.0 (DPI)")
        self.rechaza(licencia="Creative Commons Share Alike")

    def test_nc(self):
        self.rechaza(licencia="cc-by-nc-4.0")
        self.rechaza(licencia="cc-by-nc-sa-4.0")
        self.rechaza(licencia="Non Commercial (DPI)")

    def test_nd(self):
        self.rechaza(licencia="cc-by-nd-4.0")

    def test_sin_verificar_o_vacia(self):
        self.rechaza(licencia="sin verificar")
        self.rechaza(licencia="")
        self.rechaza(licencia=None)
        self.rechaza(licencia="unspecified")

    def test_un_componente_malo_basta(self):
        self.rechaza(licencia="cc-by-4.0, CC BY-NC 4.0 (DPI)")

    def test_no_comercial(self):
        self.rechaza(uso_comercial=False)

    def test_excluidos_aunque_vengan_como_comerciales(self):
        for nombre, fuente in [("sib200", "Davlan/sib200"), ("sib-200", "x"), ("clandestino", "microsoft/Clandestino"),
                               ("pqrs_gb9w", "datos.gov.co"), ("x", "datos.gov.co gb9w"), ("xnli_es", "facebook/xnli"),
                               ("clima", "somosnlp/spa_climate_detection"), ("odio_alia", "SINAI/ALIA-es-discriminative-hate-speech")]:
            with self.subTest(nombre):
                self.rechaza(nombre=nombre, fuente=fuente, licencia="cc-by-4.0", uso_comercial=True)

    def test_blandas_de_qwen(self):
        self.rechaza(blandas="model/maestro Qwen3.5")

    def test_vacio_y_repetidos(self):
        with self.assertRaises(M.ManifiestoInvalido):
            M.Manifiesto({"conjuntos": []})
        with self.assertRaises(M.ManifiestoInvalido):
            M.Manifiesto(man(conj(), conj()))

    def test_el_error_lista_todos_los_motivos(self):
        with self.assertRaises(M.ManifiestoInvalido) as cm:
            M.Manifiesto(man(conj(nombre="a", licencia="cc-by-sa-4.0"), conj(nombre="b", licencia="cc-by-nc-4.0")))
        self.assertIn("a:", str(cm.exception))
        self.assertIn("b:", str(cm.exception))


class Aceptados(unittest.TestCase):
    def test_cc_by_y_apache(self):
        m = M.Manifiesto(man(conj(nombre="a", licencia="cc-by-4.0"), conj(nombre="b", licencia="apache-2.0"),
                             conj(nombre="c", licencia="MIT"), conj(nombre="d", licencia="cc0-1.0"), conj(nombre="e", licencia="bsd")))
        self.assertEqual(len(m.conjuntos), 5)

    def test_manifiesto_del_repositorio_valido(self):
        m = M.cargar()
        self.assertGreater(len(m.tareas_tsjev()), 100)
        for c in m.conjuntos:
            self.assertIsNone(M.motivo_licencia(c["licencia"]) if c["nombre"] != "tsjev" else None, c["nombre"])

    def test_tsjev_del_repositorio_sin_sa_nc_nd(self):
        m = M.cargar()
        tsjev = next(c for c in m.conjuntos if c["nombre"] == "tsjev")
        for t in tsjev["tareas"]:
            self.assertEqual(t["license_use"], "commercial")
            self.assertIsNone(M.motivo_licencia(t["licencia"]), t)


class Sellado(unittest.TestCase):
    def test_sellar_y_validar(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "demo.jsonl").write_text('{"a": 1}\n{"a": 2}\n', encoding="utf-8")
            m = M.Manifiesto(man(conj()))
            with self.assertRaises(M.ManifiestoInvalido):
                m.validar(d, sellado=True)           # sin sellar
            m.sellar(d)
            self.assertEqual(m.conjuntos[0]["filas"], 2)
            m.validar(d, sellado=True)
            (Path(d) / "demo.jsonl").write_text('{"a": 3}\n', encoding="utf-8")
            with self.assertRaises(M.ManifiestoInvalido):
                m.validar(d, sellado=True)           # el fichero cambió

    def test_escribir_junto(self):
        with tempfile.TemporaryDirectory() as d:
            p = M.Manifiesto(man(conj())).escribir_junto(Path(d) / "ckpt")
            self.assertEqual(json.loads(p.read_text())["conjuntos"][0]["nombre"], "demo")


class Filas(unittest.TestCase):
    def test_fila_no_comercial_en_train(self):
        with self.assertRaises(M.ManifiestoInvalido):
            M.verificar_filas([{"id": "x", "split": "train", "uso_comercial": False}])
        M.verificar_filas([{"id": "x", "split": "test", "uso_comercial": False}])   # en test se permite

    def test_fila_con_licencia_sa(self):
        with self.assertRaises(M.ManifiestoInvalido):
            M.verificar_filas([{"id": "x", "split": "train", "uso_comercial": True, "licencia": "cc-by-sa-4.0"}])

    def test_tarea_tsjev_no_admitida(self):
        m = M.cargar()
        ok = sorted(m.tareas_tsjev())[0]
        M.verificar_filas([{"id": "tsjev:train:1", "split": "train", "uso_comercial": True, "tarea": ok}], m)
        with self.assertRaises(M.ManifiestoInvalido):
            M.verificar_filas([{"id": "tsjev:train:2", "split": "train", "uso_comercial": True, "tarea": "no/existe"}], m)


class Tsjev(unittest.TestCase):
    FUENTES = {
        "ok/a": {"rows": {"train": 10, "validation": 1}, "license": "cc-by-4.0", "license_use": "commercial", "dataset": "x/a"},
        "sa/b": {"rows": {"train": 20}, "license": "cc-by-sa-4.0", "license_use": "commercial", "dataset": "x/b"},
        "nc/c": {"rows": {"train": 30}, "license": "cc-by-nc-4.0", "license_use": "non-commercial", "dataset": "x/c"},
        "nd/d": {"rows": {"train": 40}, "license": "cc-by-nd-4.0", "license_use": "commercial", "dataset": "x/d"},
        "sv/e": {"rows": {"train": 50}, "license": "unspecified", "license_use": "unspecified", "dataset": "x/e"},
        "mix/f": {"rows": {"train": 60}, "license": "mit, CC BY-SA 4.0 (DPI)", "license_use": "commercial", "dataset": "x/f"},
        "xnli": {"rows": {"train": 70}, "license": "mit", "license_use": "commercial", "dataset": "facebook/xnli"},
        "sib": {"rows": {"train": 80}, "license": "mit", "license_use": "commercial", "dataset": "Davlan/sib200"},
    }

    def test_tabla(self):
        adm, exc, res = M.tsjev_tareas(self.FUENTES)
        self.assertEqual([t["tarea"] for t in adm], ["ok/a"])
        self.assertEqual({t["tarea"] for t in exc}, set(self.FUENTES) - {"ok/a"})
        self.assertEqual((res["tareas_total"], res["tareas_admitidas"], res["tareas_excluidas"]), (8, 1, 7))
        self.assertEqual((res["filas_admitidas"], res["filas_excluidas"]), (11, 350))

    def test_filtrar(self):
        import gzip
        with tempfile.TemporaryDirectory() as d:
            m = M.Manifiesto(man(conj(nombre="tsjev", licencia="por tarea", tareas=[
                {"tarea": "ok/a", "licencia": "cc-by-4.0", "license_use": "commercial"}])))
            ent = Path(d) / "ent.jsonl"
            base = {"split": "train", "uso_comercial": True, "tipo": "choice", "pregunta": "p", "texto": "t", "opciones": ["a", "b"],
                    "descripciones": {"a": "a", "b": "b"}, "etiqueta": "a"}
            ent.write_text("\n".join(json.dumps(dict(base, id="tsjev:train:%d" % i, tarea=t, split=s)) for i, (t, s) in enumerate(
                [("ok/a", "train"), ("sa/b", "train"), ("ok/a", "test"), ("ok/a", "dev")])), encoding="utf-8")
            n, mal = M.filtrar_tsjev([str(ent)], m, str(Path(d) / "sal.jsonl.gz"))
            self.assertEqual((n, mal), (2, 1))   # el test no cuenta como descartado ni se escribe


if __name__ == "__main__":
    unittest.main()
