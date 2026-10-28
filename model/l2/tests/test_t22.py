import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import torch

from model.l2 import datos as D
from model.l2 import entrenar
from model.l2 import evaluar
from model.l2.modelo import ModeloL2, texto_opcion
from model.l2.tests.falso import CodificadorFalso, fila


class Renombrar(unittest.TestCase):
    def test_letras(self):
        self.assertEqual([D.letra(i) for i in (0, 1, 25, 26, 27, 51, 52, 150)], ["A", "B", "Z", "AA", "AB", "AZ", "BA", "EU"])
        self.assertEqual(len({D.letra(i) for i in range(1000)}), 1000)

    def test_remapea_todo(self):
        r = fila(2, "choice", 3, blanda={"op0": 0.2, "op2": 0.8})
        n = D.renombrar_fila(r)
        self.assertEqual(n["opciones"], ["A", "B", "C"])
        self.assertEqual(n["etiqueta"], "C")
        self.assertEqual(n["descripciones"], {"A": "desc op0", "B": "desc op1", "C": "desc op2"})
        self.assertEqual(n["blanda"], {"A": 0.2, "C": 0.8})
        self.assertEqual(r["opciones"], ["op0", "op1", "op2"])  # no toca la original
        self.assertEqual(r["etiqueta"], "op2")
        self.assertIn(" · C · desc op2", texto_opcion(n, "C"))
        self.assertNotIn(" · op2 · ", texto_opcion(n, "C"))

    def test_idempotente(self):
        r = fila(1, "choice", 30, blanda={"op1": 1.0})
        n = D.renombrar_fila(r)
        self.assertIs(D.renombrar_fila(n), n)
        self.assertEqual(D.renombrar_fila(D.renombrar_fila(r)), n)
        self.assertEqual(n["opciones"][26:], ["AA", "AB", "AC", "AD"])

    def test_no_choice_intactas(self):
        for t in ("noul", "score"):
            r = fila(1, t)
            self.assertIs(D.renombrar_fila(r), r)

    def test_lote_probabilidad_y_determinismo(self):
        filas = [fila(i, "choice", 3) for i in range(2000)]
        a = D.renombrar_lote(filas, 0.5, 0, 3)
        self.assertEqual(a, D.renombrar_lote(filas, 0.5, 0, 3))
        self.assertAlmostEqual(sum(x["opciones"][0] == "A" for x in a) / len(a), 0.5, delta=0.05)
        self.assertNotEqual([x["opciones"][0] for x in a], [x["opciones"][0] for x in D.renombrar_lote(filas, 0.5, 0, 4)])
        self.assertIs(D.renombrar_lote(filas, 0.0, 0, 3), filas)
        self.assertTrue(all(x["opciones"][0] == "A" for x in D.renombrar_lote(filas, 1.0, 0, 3)))
        # renombrar un lote ya renombrado no cambia nada
        self.assertEqual(D.renombrar_lote(a, 1.0, 5, 9), D.renombrar_lote(filas, 1.0, 5, 9))


class MezclaMaestros(unittest.TestCase):
    def test_promedio_ponderado(self):
        m = D.mezclar_blanda({"a": 0.8, "b": 0.2}, {"a": 0.2, "b": 0.8}, 0.25)
        self.assertAlmostEqual(m["a"], 0.65)
        self.assertAlmostEqual(m["b"], 0.35)
        self.assertAlmostEqual(sum(m.values()), 1.0)

    def test_normaliza_y_une_claves(self):
        m = D.mezclar_blanda({"a": 3.0, "b": 1.0}, {"c": 1.0}, 0.5)  # a,b suman 4 → 0,75/0,25
        self.assertEqual(m, {"a": 0.375, "b": 0.125, "c": 0.5})

    def test_falta_una(self):
        self.assertEqual(D.mezclar_blanda(None, {"a": 2.0}, 0.3), {"a": 1.0})
        self.assertEqual(D.mezclar_blanda({"a": 2.0}, None, 0.3), {"a": 1.0})
        self.assertIsNone(D.mezclar_blanda(None, None, 0.3))
        self.assertEqual(D.mezclar_blanda({"a": 0.0}, {"b": 1.0}, 0.3), {"b": 1.0})

    def test_filas_y_fichero(self):
        filas = [fila(0, blanda={"op0": 1.0}), fila(1), fila(2)]
        with tempfile.TemporaryDirectory() as t:
            with open(Path(t) / "e.jsonl", "w") as f:  # solo {id, blanda}: sin el resto del esquema
                for i in (0, 1):
                    f.write(json.dumps({"id": filas[i]["id"], "blanda": {"op0": 0.0, "op1": 1.0}}) + "\n")
            ex = D.cargar_simples(t)
        self.assertEqual(len(ex), 2)
        self.assertEqual(D.mezclar_extra(filas, ex, 0.5), 2)
        self.assertEqual(filas[0]["blanda"], {"op0": 0.5, "op1": 0.5})
        self.assertEqual(filas[1]["blanda"], {"op0": 0.0, "op1": 1.0})
        self.assertNotIn("blanda", filas[2])


class Cache(unittest.TestCase):
    def test_congelado_cachea_y_descongelado_no_durante_entrenamiento(self):
        textos = ["passage: a", "passage: b"]
        c = CodificadorFalso()
        c.pasaje(textos)
        c.pasaje(textos)
        self.assertEqual((c.fallos, c.aciertos), (2, 2))
        self.assertFalse(c.pasaje(textos).requires_grad)
        d = CodificadorFalso(descongelar=1)
        v = d.pasaje(textos)
        self.assertTrue(v.requires_grad)  # con gradiente: no sale de la caché
        d.pasaje(textos)
        self.assertEqual((d.fallos, d.aciertos, len(d.cache)), (4, 0, 0))

    def test_invalidar_tras_cada_paso(self):
        textos = ["passage: a", "passage: b"]
        d = CodificadorFalso(descongelar=1)
        with torch.no_grad():
            v0 = d.pasaje(textos)
            d.pasaje(textos)
            self.assertEqual((d.fallos, d.aciertos), (2, 2))
            d.w.add_(1.0)  # un paso de optimización
            self.assertTrue(torch.equal(d.pasaje(textos), v0))  # caché vieja si nadie invalida
            d.invalidar()
            self.assertEqual(len(d.cache), 0)
            v1 = d.pasaje(textos)
        self.assertFalse(torch.allclose(v1, v0))

    def test_entrenar_invalida_en_cada_paso(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            with open(t / "d.jsonl", "w") as f:
                for i in range(40):
                    f.write(json.dumps(fila(i, "choice", 3, "a", blanda={"op0": 0.5, "op1": 0.5})) + "\n")
                for i in range(20):
                    f.write(json.dumps(fila(100 + i, "noul", tarea="b")) + "\n")
            enc = CodificadorFalso(descongelar=2)
            n = []
            orig = enc.invalidar
            enc.invalidar = lambda: (n.append(1), orig())
            with mock.patch.object(entrenar, "Codificador", lambda **kw: enc):
                rc = entrenar.main(["--salida", str(t / "s"), "--datos", str(t / "d.jsonl"), "--pasos", "6", "--lote", "8", "--device", "cpu",
                                    "--descongelar", "2", "--renombrar", "0.5", "--eval-cada", "3"])
            self.assertEqual(rc, 0)
            self.assertEqual(len(n), 6)
            ck = torch.load(t / "s" / "ultimo.pt", weights_only=False)
            self.assertFalse(torch.equal(ck["enc"]["w"], torch.zeros_like(ck["enc"]["w"])))  # el codificador se movió
            self.assertEqual(len(ck["opt"]["param_groups"]), 3)
            # arrancar de ese checkpoint con --inicial recupera los pesos del codificador
            enc2 = CodificadorFalso(descongelar=2)
            with mock.patch.object(entrenar, "Codificador", lambda **kw: enc2):
                entrenar.main(["--salida", str(t / "s2"), "--datos", str(t / "d.jsonl"), "--epocas", "0", "--lote", "8", "--device", "cpu",
                               "--descongelar", "2", "--inicial", str(t / "s" / "mejor.pt")])
            self.assertTrue(torch.equal(enc2.w.detach(), torch.load(t / "s" / "mejor.pt", weights_only=False)["enc"]["w"]))


class CaidaTabla(unittest.TestCase):
    def test_caida(self):
        m = lambda f: {"n": 10, "macro_f1": f}
        res = {"x": {"por_tarea": {"t": m(0.9)}, "global": m(0.9)}}
        res_r = {"x": {"por_tarea": {"t": m(0.82)}, "global": m(0.82)}}
        md, peor, peor_g = evaluar.tabla_caida(res, res_r)
        self.assertAlmostEqual(peor, 0.08)
        self.assertIn("+0.080", md)


class ModeloConRenombrado(unittest.TestCase):
    def test_forward_con_filas_renombradas(self):
        filas = D.renombrar_lote([fila(i, "choice", 4, blanda={"op0": 1.0}) for i in range(4)], 1.0, 0, 0)
        probs, ps = ModeloL2()(filas, CodificadorFalso(), True)
        self.assertEqual(len(probs), 4)
        self.assertTrue(torch.isfinite(ps["total"]))


if __name__ == "__main__":
    unittest.main()
