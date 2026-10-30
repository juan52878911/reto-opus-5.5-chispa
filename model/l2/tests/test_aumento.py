import io
import re
import tarfile
import unittest
from unittest import mock

from model.l2 import aumento as A
from model.l2 import robustez as R


def fila(i, tipo="choice", texto=None, tarea="intencion"):
    ops = ["saludo", "despedida", "queja"] if tipo == "choice" else ["false", "true"]
    return {"id": "t:train:%d" % i, "tarea": tarea, "tipo": tipo, "pregunta": "¿Qué necesita el cliente del banco?",
            "texto": texto or "Quiero cancelar mi tarjeta porque me cobraron una comisión que no entiendo", "opciones": ops,
            "descripciones": {o: "descripción de " + o for o in ops}, "etiqueta": ops[1], "idioma": "es", "split": "train",
            "blanda": {o: (0.7 if o == ops[1] else 0.15) for o in ops}}


TODAS = {k: 1.0 for k in A.FRACCIONES}


class Aumento(unittest.TestCase):
    def test_determinista_y_no_toca_la_original(self):
        f = fila(1)
        copia = {**f, "opciones": list(f["opciones"])}
        a = A.aumentar_fila(f, 0, 3, TODAS)
        self.assertEqual(a, A.aumentar_fila(f, 0, 3, TODAS))
        self.assertEqual(f, copia)
        self.assertNotEqual(a, A.aumentar_fila(f, 0, 4, TODAS))   # otro paso, otro aumento
        self.assertNotEqual(a, A.aumentar_fila(f, 1, 3, TODAS))   # otra semilla
        filas = [fila(i) for i in range(20)]
        self.assertEqual(A.aumentar_lote(filas, 5, 2), A.aumentar_lote(list(reversed(filas)), 5, 2)[::-1])   # no depende del orden

    def test_fracciones(self):
        filas = [fila(i) for i in range(2000)]
        n = {"ids": sum(a["opciones"][0].startswith("op_") for a in A.aumentar_lote(filas, 0, 0))}
        self.assertAlmostEqual(n["ids"] / 2000, 0.30, delta=0.04)
        self.assertEqual(sum(a["opciones"][0].startswith("op_") for a in A.aumentar_lote(filas, 0, 0, {"ids": 0})), 0)
        self.assertEqual(A.aumentar_lote(filas, 0, 0, {k: 0 for k in A.FRACCIONES}), filas)
        self.assertEqual(A.parsear_fracs("ids=0.5,erratas=0")["erratas"], 0.0)
        with self.assertRaises(ValueError):
            A.parsear_fracs("nada=1")

    def test_etiqueta_tras_renombrar(self):
        for i in range(40):
            f = fila(i)
            g = A.aumentar_fila(f, 0, 0, {"ids": 1.0})
            self.assertTrue(all(re.fullmatch(r"op_[0-9a-f]{4}", o) for o in g["opciones"]))
            self.assertEqual(len(set(g["opciones"])), 3)
            pos = f["opciones"].index(f["etiqueta"])
            self.assertEqual(g["etiqueta"], g["opciones"][pos])          # misma opción, nuevo id
            self.assertEqual(g["descripciones"][g["etiqueta"]], f["descripciones"][f["etiqueta"]])   # la descripción viaja con ella
            self.assertEqual(g["origen"], f["opciones"])
            self.assertEqual(max(g["blanda"], key=g["blanda"].get), g["etiqueta"])
            self.assertEqual(g["texto"], f["texto"])

    def test_ids_no_toca_noul_ni_conserva_origen_previo(self):
        n = fila(1, "noul")
        self.assertEqual(A.aumentar_fila(n, 0, 0, {"ids": 1.0}), n)
        previa = {**fila(2), "origen": ["a", "b", "c"]}
        self.assertEqual(A.aumentar_fila(previa, 0, 0, {"ids": 1.0})["origen"], ["a", "b", "c"])

    def test_relleno_respeta_max_tok(self):
        for max_tok in (40, 64, 128, 256):
            for i in range(60):
                f = fila(i, texto="palabra " * (i % 9))
                g = A.aumentar_fila(f, 0, 0, {"relleno": 1.0}, max_tok)
                self.assertLessEqual(A.tokens_aprox(g["texto"]), max_tok if g["texto"] != f["texto"] else max(max_tok, A.tokens_aprox(f["texto"])))
        corto = A.aumentar_fila(fila(1), 0, 0, {"relleno": 1.0}, 256)
        self.assertGreaterEqual(sum(corto["texto"].count(s) for s in A.RELLENO_ENT), 2)   # 2-4 frases de relleno
        self.assertIn(fila(1)["texto"], corto["texto"])
        largo = fila(2, texto="x" * 2000)   # ya pasa de max_tok: no se le añade nada
        self.assertEqual(A.aumentar_fila(largo, 0, 0, {"relleno": 1.0}, 64)["texto"], largo["texto"])

    def test_resto_de_transformaciones(self):
        f = fila(1)
        self.assertNotEqual(A.aumentar_fila(f, 0, 0, {"erratas": 1.0})["texto"], f["texto"])
        m = A.aumentar_fila(f, 0, 0, {"mayusculas": 1.0})["texto"]
        self.assertEqual(m.lower(), f["texto"].lower())
        self.assertNotEqual(m, f["texto"])
        p = A.aumentar_fila(f, 0, 0, {"parafrasis": 1.0})["pregunta"]
        self.assertNotEqual(p, f["pregunta"])
        self.assertIn("banco", p)
        e = A.aumentar_fila({**f, "tarea": "toxicidad", "opciones": ["false", "true"], "etiqueta": "true",
                             "descripciones": {"false": "x", "true": "y"}, "blanda": None}, 0, 0, {"ingles": 1.0})
        self.assertEqual(e["descripciones"], A.DESCRIPCIONES_EN_ENT["toxicidad"])
        self.assertEqual(A.aumentar_fila(f, 0, 0, {"ingles": 1.0})["pregunta"], A.PREGUNTAS_EN_ENT[f["pregunta"]])
        con_en = A.aumentar_fila({**f, "pregunta_en": "Is it?"}, 0, 0, {"ingles": 1.0})
        self.assertEqual(con_en["pregunta"], "Is it?")

    def test_las_listas_de_entrenamiento_y_de_medida_no_se_solapan(self):
        self.assertEqual(A.listas_solapadas(), [])
        self.assertFalse(set(A.PLANTILLAS_PREGUNTA_ENT[1:]) & set(A.E2.PLANTILLAS_PREGUNTA[1:]))
        self.assertFalse(set(A.RELLENO_ENT) & set(A.E2.RELLENO))
        # las que usa M3 siguen intactas tras un aumento (el cambio de listas es temporal)
        antes = (A.E2.PLANTILLAS_PREGUNTA, A.E2.RELLENO)
        A.aumentar_fila(fila(1), 0, 0, TODAS)
        self.assertIs(A.E2.PLANTILLAS_PREGUNTA, antes[0])
        self.assertIs(A.E2.RELLENO, antes[1])
        # lo que sale en entrenamiento no puede ser lo que M3 genera con la misma fila
        f = fila(1)
        med = {v["pregunta"] for v in (R.variantes_de(f, "parafrasear", s, A.E2.generar) for s in range(30))}
        ent = {A.aumentar_fila(f, s, 0, {"parafrasis": 1.0})["pregunta"] for s in range(30)}
        self.assertFalse(med & ent)
        med_ids = {o for s in range(30) for o in R.variantes_de(f, "renombrar", s, A.E2.generar)["opciones"]}
        self.assertFalse(any(re.fullmatch(r"op_[0-9a-f]{4}", o) for o in med_ids))
        self.assertTrue(all(re.fullmatch(r"x\d{3}", o) for o in med_ids))

    def test_entrenar_con_aumento_y_desde(self):
        import json
        import tempfile
        from pathlib import Path
        import torch
        from model.l2 import entrenar
        from model.l2.tests.falso import CodificadorFalso
        from model.l2.tests.falso import fila as ff
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            (d / "d.jsonl").write_text("".join(json.dumps(r) + "\n" for r in [ff(i, "choice", 4, "a") for i in range(30)]
                                              + [ff(100 + i, "noul", tarea="b") for i in range(20)]), encoding="utf-8")
            enc = CodificadorFalso()
            base = ["--datos", str(d / "d.jsonl"), "--pasos", "6", "--lote", "8", "--device", "cpu", "--ckpt-cada", "0"]
            with mock.patch.object(entrenar, "Codificador", lambda **kw: enc):
                self.assertEqual(entrenar.main(["--salida", str(d / "a"), *base]), 0)
                vistos = []
                real = A.aumentar_lote
                with mock.patch.object(A, "aumentar_lote", lambda *x, **k: vistos.append(1) or real(*x, **k)):
                    self.assertEqual(entrenar.main(["--salida", str(d / "b"), *base, "--desde", str(d / "a" / "mejor.pt"),
                                                    "--aumento", "--aumento-fracs", "ids=1"]), 0)
                self.assertEqual(len(vistos), 6)
            ck = torch.load(d / "b" / "ultimo.pt", weights_only=False)
            self.assertEqual((ck["args"]["lr"], ck["args"]["lr_torre"]), (3e-5, 1e-5))
            self.assertTrue(ck["args"]["aumento"])


class EmpaquetadoM5(unittest.TestCase):
    def test_el_paquete_incluye_el_json_de_conversion_y_ningun_otro_resultado(self):
        import subprocess
        from pathlib import Path
        raiz = Path(__file__).resolve().parents[3]
        out = subprocess.run(["bash", str(raiz / "model/l2/aws/empaquetar_estabilidad.sh"), "HEAD"], cwd=raiz, capture_output=True, check=True).stdout
        nombres = [m.name for m in tarfile.open(fileobj=io.BytesIO(out), mode="r:gz").getmembers() if m.isfile()]
        self.assertIn("model/meta/resultados/conversion-20261027.json", nombres)
        otros = [n for n in nombres if "/resultados" in n and not n.endswith("/") and n != "model/meta/resultados/conversion-20261027.json"]
        self.assertEqual(otros, [])


if __name__ == "__main__":
    unittest.main()
