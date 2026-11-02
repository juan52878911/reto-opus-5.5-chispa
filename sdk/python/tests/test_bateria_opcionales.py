"""Línea base con conjuntos opcionales ausentes: se guarda, y la comparación distingue ausentes de --solo."""
import json
import unittest

from chispa import bateria as B

from tests.test_bateria import Base


class Opcionales(Base):
    def setUp(self):
        super().setUp()
        self.completo = [{"nombre": "choice", "ruta": "choice.jsonl"}, {"nombre": "noul", "ruta": "noul.jsonl"}]

    def rep(self, extra=()):
        self.man = self.manifiesto(self.completo + list(extra))
        return self.correr()

    def test_guardar_con_opcional_ausente_registra_la_lista(self):
        r = self.rep([{"nombre": "fuera", "ruta": "${NO_EXISTE_CHISPA_X}/f.jsonl", "opcional": True}])
        self.assertNotIn("parcial", r)
        lb = B.linea_base(r)
        self.assertEqual(lb["opcionales_ausentes"], ["fuera"])

    def test_solo_sigue_sin_guardar(self):
        self.man = self.manifiesto(self.completo)
        r = self.correr(solo=["choice"])
        with self.assertRaises(B.ErrorBateria):
            B.linea_base(r)

    def test_base_con_mas_conjuntos_ausentes_en_la_corrida_avisa(self):
        r = self.rep()
        b = json.loads(json.dumps(B.linea_base(r)))
        b["conjuntos"]["extra"] = dict(b["conjuntos"]["choice"])
        r2 = dict(r, opcionales_ausentes=["extra"])
        c = B.comparar(r2, b, B.UMBRALES)
        self.assertTrue(c["ok"], c)
        self.assertTrue(any("extra" in a and "falta" in a for a in c["avisos"]))
        self.assertTrue(any("solo por conjunto" in a for a in c["avisos"]))

    def test_conjunto_ausente_no_declarado_sigue_fallando(self):
        r = self.rep()
        b = json.loads(json.dumps(B.linea_base(r)))
        b["conjuntos"]["extra"] = dict(b["conjuntos"]["choice"])
        self.assertFalse(B.comparar(r, b, B.UMBRALES)["ok"])

    def test_base_con_menos_conjuntos_es_nuevo_sin_base_y_no_oculta_regresion(self):
        r = self.rep()
        b = json.loads(json.dumps(B.linea_base(r)))
        del b["conjuntos"]["noul"]
        c = B.comparar(r, b, B.UMBRALES)
        self.assertTrue(c["ok"], c)
        self.assertTrue(any("noul" in a and "nuevo, sin base" in a for a in c["avisos"]))
        b["conjuntos"]["choice"]["exactitud"] = 1.0
        r["conjuntos"]["choice"]["exactitud"] = 0.0
        self.assertFalse(B.comparar(r, b, B.UMBRALES)["ok"])

    def test_mismos_conjuntos_comparan_global(self):
        r = self.rep()
        b = json.loads(json.dumps(B.linea_base(r)))
        b["global"]["exactitud"] = 1.0
        r["global"]["exactitud"] = 0.0
        r["conjuntos"] = b["conjuntos"]
        self.assertFalse(B.comparar(r, b, B.UMBRALES)["ok"])

    def test_base_vieja_parcial_por_omitidos_se_usa_con_aviso(self):
        r = self.rep()
        b = json.loads(json.dumps(B.linea_base(r)))
        b.update(parcial=True, omitidos={"fuera": "sin datos"})
        c = B.comparar(r, b, B.UMBRALES)
        self.assertTrue(c["ok"], c)
        self.assertTrue(any("antigua" in a for a in c["avisos"]))
        del b["conjuntos"]["noul"]
        self.assertFalse(B.comparar(r, b, B.UMBRALES)["ok"])


if __name__ == "__main__":
    unittest.main()
