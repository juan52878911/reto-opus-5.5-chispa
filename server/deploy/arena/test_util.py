"""Pruebas de arena_util.py y curvas.py con datos inventados. Uso: python -I server/deploy/arena/test_util.py"""
import gzip
import json
import subprocess
import sys
import tempfile
import unittest
import xml.dom.minidom
from pathlib import Path

AQUI = Path(__file__).resolve().parent


def correr(script, *args):
    return subprocess.run([sys.executable, "-I", str(AQUI / script), *map(str, args)], capture_output=True, text=True)


def escribir(ruta, filas):
    Path(ruta).write_text("".join(json.dumps(r) + "\n" for r in filas))


class TestCurvas(unittest.TestCase):
    def test_tabla_svg_y_cobertura(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "pred").mkdir()
            # 20 filas: las 10 más confiadas aciertan, las 10 menos fallan
            verdad = [{"id": f"t:{i}", "etiqueta": "a", "split": "test"} for i in range(20)]
            preds = [{"id": f"t:{i}", "probs": {"a": 0.99 - i * 0.01, "b": 0.01 + i * 0.01} if i < 10 else {"a": 0.2, "b": 0.8 - i * 0.001}, "ms": 1}
                     for i in range(20)]
            escribir(d / "v.jsonl", verdad)
            escribir(d / "pred" / "t.jsonl", preds)
            r = correr("curvas.py", "--pred", d / "pred", "--verdad", f"t={d / 'v.jsonl'}", "--salida", d / "s")
            self.assertEqual(r.returncode, 0, r.stderr)
            res = json.loads((d / "s" / "curvas.json").read_text())["t"]
            self.assertEqual(res["n"], 20)
            self.assertAlmostEqual(res["cobertura_p95"], 0.5)
            self.assertEqual(len(res["tabla"]), 20)   # una fila cada 5 %
            self.assertAlmostEqual(res["tabla"][9]["precision"], 1.0)    # 50 %
            self.assertAlmostEqual(res["tabla"][-1]["precision"], 0.5)   # 100 %
            xml.dom.minidom.parse(str(d / "s" / "t.svg"))

    def test_sin_coincidencias_falla(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "pred").mkdir()
            escribir(d / "v.jsonl", [{"id": "x", "etiqueta": "a"}])
            escribir(d / "pred" / "t.jsonl", [{"id": "y", "probs": {"a": 1.0}}])
            self.assertNotEqual(correr("curvas.py", "--pred", d / "pred", "--verdad", f"t={d / 'v.jsonl'}", "--salida", d / "s").returncode, 0)


class TestAsr(unittest.TestCase):
    def test_asr_por_dimension_y_detector(self):
        def ronda(dim, enj_fooled, dets):
            return {"swarm": {"dimension": dim, "fooled": enj_fooled, "escalated": False},
                    "detectors": [{"detector_id": k, "fooled": f, "escalate": False, **({"error": "down"} if e else {})} for k, f, e in dets]}
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            rondas = [ronda("spam", i < 1, [(f"spam-chispa-cascada-r{i % 2 + 1}", i < 2, False), ("spam-rules-r1", False, i == 3)]) for i in range(4)]
            escribir(d / "l.jsonl", rondas)
            r = correr("arena_util.py", "asr", "--ledger", d / "l.jsonl", "--salida", d / "s", "--max-ataques", 4)
            self.assertEqual(r.returncode, 0, r.stderr)
            a = json.loads((d / "s" / "asr.json").read_text())
            self.assertAlmostEqual(a["enjambre"]["spam"]["asr"], 0.25)
            self.assertAlmostEqual(a["detectores"]["spam-chispa-cascada"]["asr"], 0.5)
            self.assertEqual(a["detectores"]["spam-rules"]["errores"], 1)
            self.assertEqual(a["detectores"]["spam-rules"]["ataques"], 3)
            self.assertEqual(correr("arena_util.py", "asr", "--ledger", d / "l.jsonl", "--salida", d / "s", "--max-ataques", 5).returncode, 1)

    def test_preparar(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for dim, (pos, neg) in {"spam": ("spam", "legit"), "injection": ("injection", "safe")}.items():
                (d / "a" / dim).mkdir(parents=True)
                for sp in ("train", "valid", "test"):
                    escribir(d / "a" / dim / f"{sp}.jsonl", [{"id": f"{sp}{i}", "text": f"texto {i}", "label": pos if i % 2 else neg, "template": "t"} for i in range(4)])
            r = correr("arena_util.py", "preparar", "--datos", d / "a", "--salida", d / "p")
            self.assertEqual(r.returncode, 0, r.stderr)
            dev = [json.loads(l) for l in (d / "p" / "dev.jsonl").read_text().splitlines()]
            self.assertEqual({x["split"] for x in dev}, {"dev"})
            self.assertEqual(len(dev), 8)
            self.assertEqual(json.loads((d / "p" / "spam" / "esquema.json").read_text())["tipo"], "choice")
            self.assertEqual(len((d / "p" / "injection" / "ejemplos.jsonl").read_text().splitlines()), 4)


if __name__ == "__main__":
    unittest.main()
