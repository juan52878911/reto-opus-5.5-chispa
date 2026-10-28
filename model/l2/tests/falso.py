"""Codificador falso (sin e5): estados deterministas por hash del texto, con la caché y el hash reales de `Codificador`."""
import hashlib

import torch

from model.l2.modelo import Codificador, DIM_E5


def _vec(texto, n, dim=DIM_E5):
    g = torch.Generator().manual_seed(int.from_bytes(hashlib.sha1(texto.encode()).digest()[:7], "big"))
    return torch.randn(n, dim, generator=g)


class CodificadorFalso(Codificador):
    def __init__(self, caer_en=None, descongelar=0):
        self.n_desc = descongelar
        self.w = torch.nn.Parameter(torch.zeros(DIM_E5), requires_grad=bool(descongelar))  # «capa» entrenable
        self.device, self.max_tok = "cpu", 128
        from collections import OrderedDict
        self.cache, self.cache_max, self.aciertos, self.fallos = OrderedDict(), 10000, 0, 0
        self.pases, self.msgs = 0, None
        self.caer_en = caer_en

    def _pase(self, textos):
        self.pases += 1
        if self.caer_en is not None and self.pases > self.caer_en:
            raise RuntimeError("caída simulada")
        T = 6
        H = torch.stack([_vec(t, T) for t in textos]) + self.w
        return H, torch.ones(len(textos), T, dtype=torch.bool)


    def parametros_entrenables(self):
        return [self.w] if self.n_desc else []

    def estado_enc(self):
        return {"w": self.w.detach().clone()} if self.n_desc else {}

    def cargar_enc(self, estado):
        if estado:
            self.w.data.copy_(estado["w"])


def fila(i, tipo="choice", n=4, tarea="t", blanda=None, k=None):
    ops = {"choice": ["op%d" % j for j in range(n)], "noul": ["false", "true"], "score": [str(j + 1) for j in range(k or 5)]}[tipo]
    r = {"id": "f:train:%d" % i, "tarea": tarea, "tipo": tipo, "pregunta": "¿Qué %s?" % tarea, "texto": "mensaje %d de %s" % (i, tarea),
         "opciones": ops, "descripciones": {o: "desc " + o for o in ops}, "etiqueta": ops[i % len(ops)], "idioma": "es",
         "split": "train", "fuente": "x", "licencia": "MIT", "uso_comercial": True}
    if blanda:
        r["blanda"] = blanda
    return r

