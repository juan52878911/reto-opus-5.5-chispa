"""«Nadie opinó»: aviso de train sin TORR, escalate_reason en la respuesta y alerta de la batería."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from chispa import bateria as B
from chispa import formato
from chispa.cliente import Chispa
from chispa.train import entrenar, resumen_capas, _torre_junto_al_ckpt

from tests.test_bateria import Base
from tests.test_train import ESQ, PAL
from tests.test_torre_train import SINTETICO

SIN_TORRE = {"capas": {"L0": False, "L1": False, "L2": True, "L3": False}, "torre_al_vuelo": False}
CON_TORRE = {"capas": {"L0": False, "L1": False, "L2": True, "L3": False}, "torre_al_vuelo": True}


def nadie(state, q):
    ops = [o["id"] for o in q["options"]]
    return {"answer": "", "probs": {}, "escalate": True, "layer": "escalar", "escalate_reason": "sin_opinion"}


def con_probs(state, q):
    ops = [o["id"] for o in q["options"]] or ["false", "true"]
    return {"answer": "", "probs": {o: 1 / len(ops) if o != ops[0] else 1 - (len(ops) - 1) / len(ops) * 0.5 for o in ops},
            "escalate": True, "layer": "escalar", "escalate_reason": "baja_confianza"}


class BateriaNadieOpino(Base):
    def test_sin_torre_alerta_con_causa_y_cuenta_aparte(self):
        self.srv.regla, self.srv.healthz = nadie, SIN_TORRE
        avisos = []
        r = B.bateria(self.man, url=self.srv.url, concurrencia=2, aviso=avisos.append)
        g = r["global"]
        self.assertEqual((g["nadie_opino"], g["baja_confianza"], g["sin_probs"]), (1.0, 0.0, 1.0))
        self.assertEqual(len(r["alertas"]), 1 + len(r["conjuntos"]))
        self.assertIn("falta de torre", r["alertas"][0])
        self.assertIn("## Alertas", r["informe"])
        self.assertTrue(any("no puede opinar sobre esquemas" in a for a in avisos), avisos)
        self.assertEqual(r["capacidades_servidor"], SIN_TORRE)

    def test_con_torre_escala_con_probs_y_entra_en_exactitud(self):
        self.srv.regla, self.srv.healthz = con_probs, CON_TORRE
        avisos = []
        r = B.bateria(self.man, url=self.srv.url, concurrencia=2, aviso=avisos.append)
        g = r["global"]
        self.assertEqual((g["nadie_opino"], g["baja_confianza"], g["sin_probs"]), (0.0, 1.0, 0.0))
        self.assertIsNotNone(g["exactitud"])
        self.assertEqual(r["alertas"], [])
        self.assertNotIn("## Alertas", r["informe"])
        self.assertFalse(any("no puede opinar" in a for a in avisos), avisos)

    def test_servidor_antiguo_sin_motivo_escalar_sin_probs_es_nadie_opino(self):
        self.srv.regla = lambda s, q: {"answer": "", "probs": {}, "escalate": True, "layer": "escalar"}
        r = self.correr()
        self.assertEqual(r["global"]["nadie_opino"], 1.0)
        self.assertIn("no expone sus capas", r["alertas"][0])

    def test_servidor_nuevo_sin_motivo_es_incompleta_y_sin_alerta_de_torre(self):
        self.srv.regla, self.srv.healthz = (lambda s, q: {"answer": "", "probs": {}, "escalate": True, "layer": "escalar"}), SIN_TORRE
        r = self.correr()
        g = r["global"]
        self.assertEqual((g["nadie_opino"], g["incompletas"], g["baja_confianza"]), (0.0, 1.0, 0.0))
        self.assertFalse(any("nadie opinó" in a for a in r["alertas"]), r["alertas"])  # no es la alerta de torre; sí la de incompletas
        self.assertTrue(any("escaladas incompletas" in a for a in r["alertas"]), r["alertas"])

    def test_servidor_nuevo_motivo_incompleta(self):
        self.srv.regla, self.srv.healthz = (lambda s, q: {"answer": "", "probs": {}, "escalate": True, "layer": "escalar", "escalate_reason": "incompleta"}), CON_TORRE
        g = self.correr()["global"]
        self.assertEqual((g["nadie_opino"], g["incompletas"]), (0.0, 1.0))

    def test_sin_presupuesto_torres_es_incompleta_y_alerta(self):
        self.srv.regla, self.srv.healthz = (lambda s, q: {"answer": "", "probs": {}, "escalate": True, "layer": "escalar", "escalate_reason": "sin_presupuesto_torres"}), CON_TORRE
        r = self.correr()
        g = r["global"]
        self.assertEqual((g["nadie_opino"], g["incompletas"], g["sin_presupuesto_torres"]), (0.0, 1.0, 1.0))
        self.assertTrue(any("escaladas incompletas" in a and "presupuesto de torres" in a and "/metrics" in a for a in r["alertas"]), r["alertas"])
        self.assertIn("sin presup. torres", r["informe"])
        self.assertIn("incompletas", r["informe"])

    def test_pocas_incompletas_no_alertan(self):
        rep = {"global": {"incompletas": 0.2}, "conjuntos": {}}
        self.assertEqual(B.alertas_incompletas(rep), [])
        rep["global"]["incompletas"] = 0.21
        self.assertEqual(len(B.alertas_incompletas(rep)), 1)

    def test_sin_opinion_atajo_solo_con_servidor_antiguo(self):
        fila = {"error": "", "escalate": True, "escalate_reason": "", "probs": {}}
        self.assertFalse(B._sin_opinion(fila))
        self.assertTrue(B._incompleta(fila))
        antigua = dict(fila, servidor_antiguo=True)
        self.assertTrue(B._sin_opinion(antigua))
        self.assertFalse(B._incompleta(antigua))

    def test_cliente_lee_escalate_reason(self):
        self.srv.regla = nadie
        x = Chispa(self.srv.url).decidir("hola", [B.cargar_filas(self.ruta("choice.jsonl"))[0].q])[0]
        self.assertEqual((x.escalate, x.escalate_reason), (True, "sin_opinion"))


class TrainSinTorre(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d)
        (self.d / "e.json").write_text(json.dumps(ESQ))
        with open(self.d / "ej.jsonl", "w") as f:
            for c in ("alta", "baja"):
                for i in range(5):
                    f.write(json.dumps({"texto": f"{PAL[c]} caso{i}", "etiqueta": c}) + "\n")

    def entrenar(self, **kw):
        logs = []
        entrenar(self.d / "ej.jsonl", self.d / "e.json", self.d / "s.chispa", usar_go=False, log=logs.append, **kw)
        return logs

    def test_sin_torre_avisa_y_resume_las_capas(self):
        logs = self.entrenar()
        self.assertTrue(any(m.startswith("AVISO: sin TORR") and "escalate_reason sin_opinion" in m for m in logs), logs)
        self.assertTrue(any(m.startswith("capas del .chispa:") and "torre al vuelo (TORR) no" in m and "L2 no" in m for m in logs), logs)

    def test_sin_torre_explicito_no_avisa(self):
        logs = self.entrenar(sin_torre=True)
        self.assertFalse(any(m.startswith("AVISO: sin TORR") for m in logs), logs)
        self.assertTrue(any("--sin-torre" in m for m in logs), logs)

    def test_con_torre_no_avisa(self):
        logs = self.entrenar(torre=SINTETICO)
        self.assertFalse(any(m.startswith("AVISO: sin TORR") for m in logs), logs)
        self.assertTrue(any("torre al vuelo (TORR) sí" in m for m in logs), logs)
        self.assertIn(formato.TORR, formato.leer((self.d / "s.chispa").read_bytes()))

    def test_torre_y_sin_torre_a_la_vez(self):
        with self.assertRaises(Exception):
            self.entrenar(torre=SINTETICO, sin_torre=True)

    def test_onnx_junto_al_checkpoint(self):
        ck = self.d / "ckpt"
        ck.mkdir()
        self.assertIsNone(_torre_junto_al_ckpt(ck, lambda m: None))
        shutil.copy(SINTETICO, ck / "torre.onnx")
        logs = []
        self.assertEqual(_torre_junto_al_ckpt(ck, logs.append), ck / "torre.onnx")
        self.assertIn("junto al checkpoint", logs[0])


if __name__ == "__main__":
    unittest.main()


class BateriaHealthzPasajero(Base):
    """Un /healthz que falla (una vez o siempre) no debe cambiar la semántica de un servidor nuevo."""

    def parcheado(self, fallos):
        llamadas = []
        original = B.capacidades_servidor

        def falso(url, timeout=10.0):
            llamadas.append(1)
            return None if len(llamadas) <= fallos else original(url, timeout)
        B.capacidades_servidor, B.time.sleep = falso, lambda s: None
        self.addCleanup(setattr, B, "capacidades_servidor", original)
        self.addCleanup(setattr, B.time, "sleep", __import__("time").sleep)
        return llamadas

    def test_un_fallo_pasajero_se_reintenta(self):
        self.srv.regla, self.srv.healthz = (lambda s, q: {"answer": "", "probs": {}, "escalate": True, "layer": "escalar"}), SIN_TORRE
        llamadas = self.parcheado(1)
        r = self.correr()
        self.assertEqual(len(llamadas), 2)
        self.assertEqual(r["capacidades_servidor"], SIN_TORRE)
        self.assertEqual(r["global"]["incompletas"], 1.0)  # semántica de servidor nuevo

    def test_healthz_caido_con_escalate_reason_es_servidor_nuevo(self):
        self.srv.regla, self.srv.healthz = (lambda s, q: {"answer": "", "probs": {}, "escalate": True, "layer": "escalar", "escalate_reason": "incompleta"}), SIN_TORRE
        llamadas = self.parcheado(99)
        avisos = []
        r = self.correr(aviso=avisos.append)
        self.assertEqual(len(llamadas), 3)
        self.assertNotIn("capacidades_servidor", r)
        self.assertEqual((r["global"]["incompletas"], r["global"]["nadie_opino"]), (1.0, 0.0))
        self.assertTrue(any("escalate_reason" in a for a in avisos), avisos)

    def test_healthz_caido_sin_escalate_reason_sigue_siendo_antiguo(self):
        self.srv.regla = lambda s, q: {"answer": "", "probs": {}, "escalate": True, "layer": "escalar"}
        self.parcheado(99)
        r = self.correr()
        self.assertEqual(r["global"]["nadie_opino"], 1.0)
