"""ZB-4: la batería lee `torre_al_vuelo_motivo` de /healthz y lo marca como alerta del informe."""
from chispa import bateria as B

from tests.test_bateria import Base

DEGRADADO = {"capas": {"L0": False, "L1": True, "L2": True, "L3": False}, "torre_al_vuelo": False, "torre_al_vuelo_motivo": "texto_torre_inconsistente"}
SANO = {"capas": {"L0": False, "L1": True, "L2": True, "L3": False}, "torre_al_vuelo": True}


class AlertaTorreDesactivada(Base):
    def test_motivo_es_alerta(self):
        self.srv.healthz = DEGRADADO
        r = self.correr()
        self.assertEqual(r["capacidades_servidor"]["torre_al_vuelo_motivo"], "texto_torre_inconsistente")
        alertas = [a for a in r["alertas"] if "texto_torre_inconsistente" in a]
        self.assertEqual(len(alertas), 1, r["alertas"])
        self.assertTrue(alertas[0].startswith("ALERTA"), alertas)

    def test_sin_motivo_no_hay_alerta(self):
        self.srv.healthz = SANO
        r = self.correr()
        self.assertFalse([a for a in r["alertas"] if "desactivó la torre" in a], r["alertas"])
        self.assertNotIn("torre_al_vuelo_motivo", r["capacidades_servidor"])

    def test_causa_sin_opinion_nombra_el_motivo(self):
        self.assertIn("texto_torre_inconsistente", B.causa_sin_opinion(DEGRADADO))
        self.assertEqual(B.alerta_torre_desactivada(None), [])
