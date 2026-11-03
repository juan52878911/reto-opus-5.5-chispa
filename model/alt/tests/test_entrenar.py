import json
import tempfile
import unittest
from pathlib import Path

import torch

from model.alt import entrenar as EN
from model.alt import evaluar as EV
from model.alt import manifiesto as M
from model.alt.modelo import CrossEncoder, opciones_ordenadas

from .diminuto import filas, modelo

JEV = Path(__file__).parent / "fixtures" / "jev.jsonl"


def manifiesto_demo():
    return M.Manifiesto({"conjuntos": [{"nombre": "demo", "fuente": "org/demo", "licencia": "cc-by-4.0", "uso_comercial": True,
                                        "fichero": "demo.jsonl", "filas": None, "sha256": None}]})


def escribir_datos(d, fs):
    (Path(d) / "demo.jsonl").write_text("\n".join(json.dumps(f) for f in fs) + "\n", encoding="utf-8")


class Modelo(unittest.TestCase):
    def test_probs_suman_uno_y_score_va_por_id(self):
        with tempfile.TemporaryDirectory() as d:
            m = modelo(d)
            fs = filas(6)
            for f, p in zip(fs, m.probs(fs)):
                self.assertEqual(set(p), set(f["opciones"]))
                self.assertAlmostEqual(sum(p.values()), 1.0, places=6)
            sc = next(f for f in fs if f["tipo"] == "score")
            sc = dict(sc, opciones=["3", "1", "2"])
            self.assertEqual(opciones_ordenadas(sc), ["1", "2", "3"])

    def test_entrada_lleva_prefijo_pregunta_texto_y_descripcion(self):
        with tempfile.TemporaryDirectory() as d:
            m = modelo(d)
            m.prefijo = "query: "
            f = filas(1)[0]
            ids, mask, tams = m.codificar([f])
            self.assertEqual(tams, [3])
            txt = m.tok.decode(ids[1], skip_special_tokens=False)
            self.assertTrue(txt.startswith("[CLS] query"), txt)
            self.assertEqual(txt.count("[SEP]"), 3)
            self.assertIn("segunda", m.tok.decode(ids[1]))

    def test_noul_usa_no_y_si_sin_descripcion(self):
        with tempfile.TemporaryDirectory() as d:
            m = modelo(d)
            f = next(f for f in filas(6) if f["tipo"] == "noul")
            ids, _, tams = m.codificar([f])
            self.assertEqual(tams, [2])
            self.assertIn("no", m.tok.decode(ids[0]).split("[SEP]")[-2])

    def test_perdida_con_blanda_difiere_de_dura(self):
        with tempfile.TemporaryDirectory() as d:
            m = modelo(d)
            m.eval()
            f = dict(filas(1)[0], blanda={"a": 0.1, "b": 0.1, "c": 0.8}, etiqueta="a")
            dura = m.perdida([dict(f, blanda=None)], 0.5)
            mezcla = m.perdida([f], 0.5)
            self.assertNotAlmostEqual(float(dura), float(mezcla), places=4)


class EntrenarEnSeco(unittest.TestCase):
    def test_dos_pasos_guardar_cargar_evaluar(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            datos = d / "datos"
            datos.mkdir()
            fs = filas(20)
            escribir_datos(datos, fs)
            man = manifiesto_demo().sellar(datos)
            man.validar(datos, sellado=True)
            train, dev = EN.cargar_filas(man, datos)
            self.assertEqual((len(train), len(dev)), (16, 4))
            EN.fijar_semilla(0)
            m = modelo(d)
            hist = EN.entrenar(m, man, train, dev, d / "sal", epocas=1, lote=4, pasos=2)
            self.assertEqual(hist[0]["pasos"], 2)
            self.assertTrue((d / "sal" / "mejor" / "modelo.pt").is_file())
            self.assertTrue((d / "sal" / "mejor" / "manifiesto-entrenamiento.json").is_file())
            antes = m.probs(dev)
            c = CrossEncoder.cargar(d / "sal" / "mejor")
            despues = c.probs(dev)
            for a, b in zip(antes, despues):
                for k in a:
                    self.assertAlmostEqual(a[k], b[k], places=5)
            ev = EV.evaluar_filas(c, dev + train[:4], lote=4)
            self.assertEqual(ev["global"]["n"], 8)
            for k in ("exactitud", "macro_f1", "ece", "cobertura_p95"):
                self.assertIn(k, ev["global"])

    def test_el_entrenamiento_baja_la_perdida(self):
        with tempfile.TemporaryDirectory() as d:
            EN.fijar_semilla(0)
            m = modelo(d)
            fs = [f for f in filas(12) if f["tipo"] == "choice"]
            opt = torch.optim.AdamW(m.parameters(), lr=3e-3)
            m.train()
            primera = float(m.perdida(fs))
            for _ in range(40):
                opt.zero_grad()
                p = m.perdida(fs)
                p.backward()
                opt.step()
            self.assertLess(float(p), primera)

    def test_semilla_fija_misma_perdida(self):
        with tempfile.TemporaryDirectory() as d:
            res = []
            for _ in range(2):
                EN.fijar_semilla(3)
                m = modelo(d)
                m.eval()
                res.append(float(m.perdida(filas(6))))
            self.assertEqual(res[0], res[1])

    def test_se_niega_si_el_manifiesto_no_valida(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            mal = {"conjuntos": [{"nombre": "demo", "fuente": "x", "licencia": "cc-by-sa-4.0", "uso_comercial": True, "fichero": "demo.jsonl"}]}
            (d / "m.json").write_text(json.dumps(mal), encoding="utf-8")
            self.assertEqual(EN.main(["--datos", str(d), "--salida", str(d / "s"), "--manifiesto", str(d / "m.json")]), 2)
            ok = manifiesto_demo().datos
            (d / "m.json").write_text(json.dumps(ok), encoding="utf-8")   # válido pero sin sellar
            self.assertEqual(EN.main(["--datos", str(d), "--salida", str(d / "s"), "--manifiesto", str(d / "m.json")]), 2)

    def test_se_niega_con_fila_no_comercial_en_train(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            fs = filas(20)
            fs[0]["uso_comercial"] = False
            escribir_datos(d, fs)
            (d / "m.json").write_text(json.dumps(manifiesto_demo().datos), encoding="utf-8")
            self.assertEqual(EN.main(["--datos", str(d), "--salida", str(d / "s"), "--manifiesto", str(d / "m.json"), "--sellar"]), 2)


class JevBench(unittest.TestCase):
    def test_arnes_sobre_fixture(self):
        with tempfile.TemporaryDirectory() as d:
            m = modelo(d)
            from model.evaluacion.jevbench import cargar_jevbench
            fs = cargar_jevbench(JEV)
            self.assertEqual(len(fs), 6)
            ev = EV.evaluar_filas(m, fs, lote=3)
            self.assertEqual(ev["global"]["n"], 6)
            self.assertEqual(set(ev["por_tarea"]), {"intent", "safety", "rating"})
            lat = EV.medir_latencia(m, fs, n=4, hilos=1)
            self.assertEqual(lat["n"], 4)
            self.assertGreater(lat["p50_ms"], 0)

    def test_main_escribe_informe(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            modelo(d).guardar(d / "ck")
            self.assertEqual(EV.main(["--ckpt", str(d / "ck"), "--jevbench", str(JEV), "--salida", str(d / "s"), "--n-latencia", "3"]), 0)
            for f in ("jevbench.json", "latencia.json", "informe.md"):
                self.assertTrue((d / "s" / f).is_file(), f)
            self.assertIn("cob@.95", (d / "s" / "informe.md").read_text(encoding="utf-8"))

    def test_bateria_filtra_split_test_y_conjuntos(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            fs = []
            for i, (pref, split) in enumerate([("massive", "test"), ("massive", "train"), ("herr", "test"), ("otro", "test")]):
                f = dict(filas(3)[0], split=split, id="%s:%s:%d" % (pref, split, i), tarea="herramientas" if pref == "herr" else "intencion")
                fs.append(f)
            (d / "b.jsonl").write_text("\n".join(json.dumps(f) for f in fs), encoding="utf-8")
            evs = EV.bateria(modelo(d), [str(d / "b.jsonl")])
            self.assertEqual(set(evs), {"massive", "herramientas"})
            self.assertEqual(evs["massive"]["global"]["n"], 1)


if __name__ == "__main__":
    unittest.main()
