import json
import tempfile
import unittest
from pathlib import Path

from chispa import formato
from chispa.train import ChispaError, anadir_tau_l2_esquema_nuevo, entrenar


class TestTauL2EsquemaNuevo(unittest.TestCase):
    def test_calib_sin_y_con_campo(self):
        self.assertNotIn("tau_l2_esquema_nuevo", json.loads(formato.calib({}, 0.7)))
        self.assertEqual(json.loads(formato.calib({}, 0.7, tau_l2_esquema_nuevo=0.3))["tau_l2_esquema_nuevo"], 0.3)
        self.assertEqual(json.loads(formato.calib({}, 0.7, 0.4, 0.3))["tau_l2c"], 0.4)

    def test_reescribe_calib_y_conserva_el_resto(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "f.chispa"
            ruta.write_bytes(formato.escribir({formato.META: b"{}", formato.CALIB: formato.calib({}, 0.6, 0.4)}))
            anadir_tau_l2_esquema_nuevo(ruta, 0.25)
            s = formato.leer(ruta.read_bytes())
            c = json.loads(s[formato.CALIB])
            self.assertEqual((c["tau_l2_esquema_nuevo"], c["tau_escalate"], c["tau_l2c"]), (0.25, 0.6, 0.4))
            self.assertEqual(s[formato.META], b"{}")

    def test_fuera_de_rango_se_rechaza(self):
        for malo in (1.5, -0.1, float("nan")):
            with self.assertRaises(ChispaError):
                entrenar(None, "no-importa.yaml", "x.chispa", tau_l2_esquema_nuevo=malo)


if __name__ == "__main__":
    unittest.main()
