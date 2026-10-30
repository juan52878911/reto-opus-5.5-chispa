"""Regresiones de R14 en la batería: estabilidad multi con renombrar, línea base completa, puerta de latencia y resumen de CALIB."""
import json
import os
import unittest
from unittest import mock

from chispa import bateria as B
from chispa.evaluar import parsear_calib

from test_bateria import Base, CASOS_ROB, Servidor, _por_descripcion, fila


def _una_activa(state, q):
    ops = q["options"]
    if q["kind"] == "multi":
        act = [o["id"] for o in ops if o.get("description") == "def a"]
        return {"answer": act[0], "answers": act, "probs": {o["id"]: (0.9 if o["id"] in act else 0.1) for o in ops}}
    return _por_descripcion(state, q)


def _sin_activas_y_error_si_renombra(state, q):
    if any(o["id"] not in ("a", "b", "c", "d") for o in q["options"]):
        raise KeyError("ids opacos")
    return {"answer": "", "answers": [], "probs": {}}


class Rob(Base):
    def correr_con(self, regla_fn, casos, **k):
        srv = Servidor(regla_fn)
        self.addCleanup(srv.cerrar)
        for n, v in casos.items():
            self.jsonl(f"{n}.jsonl", v)
        self.man = self.manifiesto([{"nombre": n, "ruta": f"{n}.jsonl", "tipo": n, "grupo": "rob"} for n in casos])
        self.srv = srv
        return self.correr(robustez=True, **k)


class TestEstabilidadMulti(Rob):
    def test_una_sola_activa_con_renombrar_es_estable(self):  # hallazgo 1
        r = self.correr_con(_una_activa, {"multi": CASOS_ROB["multi"]})
        self.assertEqual(r["conjuntos"]["multi"]["transformaciones"]["renombrar"]["estabilidad"], 1.0)
        self.assertEqual(r["conjuntos"]["multi"]["estabilidad"], 1.0)

    def test_variante_con_error_nunca_es_estable(self):  # hallazgo 13
        r = self.correr_con(_sin_activas_y_error_si_renombra, {"multi": CASOS_ROB["multi"]})
        self.assertEqual(r["conjuntos"]["multi"]["transformaciones"]["renombrar"]["estabilidad"], 0.0)


class TestLineaBase(Base):
    def test_solo_no_guarda_linea_base(self):  # hallazgo 2
        base = self.ruta("base.json")
        self.assertEqual(self.cli("--solo", "choice", "--guardar-linea-base", base)[0], 2)
        self.assertFalse(os.path.exists(base))

    def test_omitidos_no_guardan_linea_base(self):  # hallazgo 2
        self.man = self.manifiesto([{"nombre": k, "ruta": f"{k}.jsonl", "tipo": k, "grupo": "p"} for k in DATOS_OK]
                                   + [{"nombre": "x", "ruta": "no_esta.jsonl", "tipo": "choice", "opcional": True}])
        base = self.ruta("base.json")
        rc, err = self.cli("--guardar-linea-base", base)
        self.assertEqual(rc, 2)
        self.assertFalse(os.path.exists(base))

    def test_comparar_rechaza_base_parcial_para_la_puerta_completa(self):  # hallazgo 2
        r = self.correr()
        b = B.json_reporte(r)
        b["parcial"] = True
        self.assertFalse(B.comparar(r, b, B.UMBRALES)["ok"])
        self.assertTrue(B.comparar(r, b, B.UMBRALES, parcial=True)["ok"])

    def test_guardar_conserva_estabilidad_min(self):  # hallazgo 3
        base = self.ruta("base.json")
        self.assertEqual(self.cli("--robustez", "--guardar-linea-base", base)[0], 0)
        with open(base) as f:
            b = json.load(f)
        self.assertNotIn("estabilidad_min", b)
        b["estabilidad_min"] = 0.0
        b["conjuntos"]["choice"]["estabilidad_min"] = 0.0
        self.jsn("base.json", b)
        nueva = self.ruta("nueva.json")
        self.assertEqual(self.cli("--robustez", "--linea-base", base, "--guardar-linea-base", nueva)[0], 0)
        with open(nueva) as f:
            n = json.load(f)
        self.assertEqual(n["estabilidad_min"], 0.0)
        self.assertEqual(n["conjuntos"]["choice"]["estabilidad_min"], 0.0)
        # y regenerar sobre la misma ruta, sin --linea-base, tampoco la pierde
        self.assertEqual(self.cli("--robustez", "--guardar-linea-base", base)[0], 0)
        with open(base) as f:
            self.assertEqual(json.load(f)["estabilidad_min"], 0.0)


DATOS_OK = ["choice", "noul"]


class TestLatencia(unittest.TestCase):
    def rep(self, p50, n=100):
        return {"global": {"n": n, "p50_ms": p50, "p99_ms": p50}, "conjuntos": {}, "tipos": {}, "grupos": {}}

    def test_ruido_de_pocos_ms_no_falla(self):  # hallazgo 6
        self.assertTrue(B.comparar(self.rep(10.84), self.rep(6.797), B.UMBRALES)["ok"])

    def test_regresion_real_falla(self):
        self.assertFalse(B.comparar(self.rep(40.0), self.rep(20.0), B.UMBRALES)["ok"])

    def test_pocas_muestras_no_juzgan_latencia(self):
        c = B.comparar(self.rep(400.0, n=5), self.rep(20.0, n=5), B.UMBRALES)
        self.assertTrue(c["ok"])
        self.assertTrue(any("muestras" in a for a in c["avisos"]))

    def test_cinco_corridas_locales_dan_cero(self):  # hallazgo 6
        man = Base.manifiesto
        b = Base()
        b.setUp()
        try:
            b.man = man(b, [{"nombre": "choice", "ruta": "choice.jsonl", "tipo": "choice"}], umbrales={})
            base = b.ruta("base.json")
            self.assertEqual(b.cli("--guardar-linea-base", base)[0], 0)
            for _ in range(5):
                self.assertEqual(b.cli("--linea-base", base)[0], 0)
        finally:
            b.d.cleanup()
            b.srv.cerrar()


METRICAS = '''chispa_calib{capa="L1",tipo="choice",origen="calib",param="T"} 1.2
chispa_calib_defecto_total{capa="L1",tipo="score"} 3
'''


class TestCalibEnInforme(Base):
    def test_informe_con_calib_y_aviso_de_defecto(self):
        self.srv.metrics = METRICAS
        avisos = []
        final = parsear_calib(METRICAS)
        antes = dict(final, defecto={k: 0.0 for k in final["defecto"]})  # el contador crece 3 durante la corrida; lo previo no cuenta
        with mock.patch.object(B, "calib_servidor", side_effect=[antes, final]):
            r = self.correr(aviso=avisos.append)
        self.assertIn("## CALIB del servidor", r["informe"])
        self.assertIn("AVISO", r["informe"].split("## CALIB del servidor")[1])
        self.assertEqual(r["calib_servidor"]["defecto"], {"L1/score": 3.0})
        self.assertTrue(any("CALIB" in a and "defecto" in a for a in avisos))

    def test_sin_metrics_no_rompe(self):
        r = self.correr()
        self.assertIn("CALIB del servidor", r["informe"])
        self.assertIn("error", r["calib_servidor"])


if __name__ == "__main__":
    unittest.main()
