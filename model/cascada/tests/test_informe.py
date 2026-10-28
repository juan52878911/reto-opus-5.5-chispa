import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from model.cascada import capas as C
from model.cascada import fixtures as F
from model.cascada import informe as I
from model.cascada.tests.falso import PotionFalso


class Extremo(unittest.TestCase):
    def test_de_fixtures_al_informe(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            F.crear_datos(d / "datos")
            F.crear_l2(d / "b", d / "datos", 0.7, 1)
            F.crear_l2(d / "c", d / "datos", 0.8, 2)
            with mock.patch.object(C, "cargar_potion", return_value=PotionFalso()):
                C.main(["--datos", str(d / "datos"), "--salida", str(d / "pred"), "--tareas", ",".join(F.TAREAS),
                        "--l0-pred", str(d / "no_hay")])
            base = d / "base.json"   # referencias inventadas
            base.write_text(json.dumps({t: {"l0_tfidf_lr": {"macro_f1": 0.8}, "e5_knn32": {"macro_f1": 0.7}} for t in F.TAREAS}))
            args = ["--datos", str(d / "datos"), "--pred", str(d / "pred"), "--tareas", ",".join(F.TAREAS), "--fecha", "2000-01-01",
                    "--salida", str(d / "out"), "--base", str(base)]
            I.main(args + ["--l2b", str(d / "b"), "--l2c", str(d / "c")])
            res = json.loads((d / "out" / "2000-01-01" / "resultados.json").read_text())
            md = (d / "out" / "2000-01-01" / "informe.md").read_text()
            self.assertEqual(set(res["tareas"]), set(F.TAREAS))
            t = res["tareas"]["tarea_a"]
            self.assertAlmostEqual(t["referencias"]["liston"], 0.76)
            # 4 formas × 4 variantes de L2 (b, b-sop, c, c-sop)
            self.assertEqual(len(t["cascadas"]), 16)
            for nombre, r in t["cascadas"].items():
                for modo in I.MODOS:
                    self.assertAlmostEqual(sum(r[modo]["fraccion"].values()), 1.0)
                    self.assertEqual(r[modo]["n"], 60)
                self.assertGreaterEqual(r["oraculo"]["macro_f1"], r["mejor_sola"] - 1e-9)
            self.assertIn("L0 → L1-proto → L2c-sop", md)
            self.assertIn("quedan fuera", md)
            self.assertIn("L1-proto = capa candidata", md)
            self.assertEqual(len(res["resumen"]), 32)
            # sin L2: prueba en seco, dos cascadas
            I.main(args + ["--salida", str(d / "seco")])
            seco = json.loads((d / "seco" / "2000-01-01" / "resultados.json").read_text())
            self.assertEqual(set(seco["tareas"]["tarea_b"]["cascadas"]), {"L0 → L1-zs", "L0 → L1-proto"})
            self.assertIn("Prueba en seco", (d / "seco" / "2000-01-01" / "informe.md").read_text())

    def test_costos_y_fuentes(self):
        self.assertEqual(I.costo("L2b-sop"), 30.6)
        self.assertEqual(I.costo("L1-proto"), 0.166)
        self.assertEqual(I.costo("L0"), 0.006)


if __name__ == "__main__":
    unittest.main()
