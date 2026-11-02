"""Modelo L2: ranuras de lectura, torre de opción y cabezas (choice, noul, score/CORAL) sobre e5 congelado.

Un solo pase del mensaje da S ∈ R^{K×d}; cada opción da un vector h ∈ R^d; la puntuación es
sim(h) = max_k softplus(h · s_k) (MaxSim). Diseño del orquestador: plan/fase-2/encargo.md y el encargo de T2.1.

T2.1b (few-shot): con `protos` (prototipos por clase a partir de ejemplos de soporte) la puntuación pasa a ser
sim_opción(c) + β · simproto(c); sin `protos` (o con β = 0) es exactamente la de la ronda 1. Ver `prototipos`.
"""
import hashlib
import math
import os
from collections import OrderedDict

import torch
import torch.nn as nn
import torch.nn.functional as F

from model.datos.comun import niveles_score  # noqa: F401  (helper canónico; se reexporta para el resto de model.l2)

E5 = "intfloat/multilingual-e5-small"
DIM_E5 = 384
MAX_TOK = 128
K_RANURAS = 16
D = 256
LAMBDA_KL, LAMBDA_NCE, LAMBDA_B = 1.0, 0.5, 0.5
SEP = " · "
TIPOS_BETA = ("choice", "noul", "score")


def normalizar_mayusculas(texto):
    """Texto del mensaje: con ≥ 8 letras y más del 70 % en mayúsculas, minúsculas carácter a carácter (primer punto de código de `c.lower()`, como `strings.ToLower`); si no, igual. Ver contrato-normalizacion.md."""
    letras = [c for c in texto if c.isalpha()]
    if len(letras) >= 8 and sum(c.isupper() for c in letras) * 10 > 7 * len(letras):
        return "".join(c.lower()[0] if c.lower() else c for c in texto)  # como strings.ToLower de Go: «İ» → «i», sigma final → «σ»
    return texto


TEXTOS_TORRE = ("v1", "v2_sin_id")


def descripcion_repetida(fila, opcion):
    """¿Otra opción de la misma pregunta tiene la misma descripción (igualdad exacta tras `strip()`)? Las vacías no cuentan."""
    desc = fila["descripciones"].get(opcion, "").strip()
    return bool(desc) and sum(fila["descripciones"].get(o, "").strip() == desc for o in fila.get("opciones", fila["descripciones"])) > 1


def texto_opcion(fila, opcion, version="v1"):
    """Texto de torre de una opción. v1: pregunta · opción · descripción. v2_sin_id: sin la opción si su descripción (`strip()`) no
    está vacía y no la comparte con otra opción de la pregunta (entonces v1, con id, para que no empaten); el `strip()` solo decide,
    el texto lleva la descripción tal cual. Ver contrato-torre.md."""
    if version not in TEXTOS_TORRE:
        raise ValueError("texto_torre desconocido: %r" % (version,))
    desc = fila["descripciones"].get(opcion, "")
    if version == "v2_sin_id" and desc.strip() and not descripcion_repetida(fila, opcion):
        return "passage: %s%s%s" % (fila["pregunta"], SEP, desc)
    return "passage: %s%s%s%s%s" % (fila["pregunta"], SEP, opcion, SEP, desc)


def indice_etiqueta(fila):
    """Índice de la etiqueta de la fila en el orden de su cabeza: el nivel (orden por int) en score, la posición declarada en el resto."""
    if fila["tipo"] == "score":
        return niveles_score(fila["opciones"]).index(fila["etiqueta"])
    return fila["opciones"].index(fila["etiqueta"])


def texto_consulta(fila, version="v1"):
    """Torre de las cabezas noul y score: la pregunta con la opción «true» (noul) o el nivel máximo (score), sea cual sea el orden.

    Mismo criterio que `exportar.opcion_consulta`. Otros tipos: la última opción."""
    ops = fila["opciones"]
    if fila["tipo"] == "noul":
        if "true" not in ops:
            raise ValueError("pregunta noul sin opción «true»: %r" % (fila["pregunta"],))
        return texto_opcion(fila, "true", version)
    if fila["tipo"] == "score":
        return texto_opcion(fila, niveles_score(ops)[-1], version)
    return texto_opcion(fila, ops[-1], version)


def clave_cabeza(fila):
    """Una cabeza por tipo de pregunta; score se separa por número de niveles (θ tiene K-1 umbrales)."""
    return "score%d" % len(fila["opciones"]) if fila["tipo"] == "score" else fila["tipo"]


class Codificador:
    """e5: estados de token del mensaje y vector de pasaje (media normalizada) con caché por hash del texto.

    Congelado por defecto. Con `descongelar=N` se entrenan las últimas N capas (el resto sigue sin gradiente, así que
    autograd no guarda nada de ellas). Coste: las dos torres comparten el codificador, de modo que (1) los vectores de opción
    ya no se pueden reutilizar entre pasos y en entrenamiento se recalculan, con gradiente, para todos los textos únicos del
    lote (antes: solo los que no estaban en la caché, y tras el calentamiento casi ninguno); (2) la caché de opciones (y la
    de mensajes) se invalida con `invalidar()` después de cada paso de optimización, y solo sirve para evaluar entre pasos.
    """

    n_desc = 0  # valor por defecto para subclases que no llaman a __init__

    def __init__(self, ruta=None, device="cpu", max_tok=MAX_TOK, cache_max=400_000, cache_mensajes=False, descongelar=0):
        from transformers import AutoModel, AutoTokenizer
        ruta = ruta or os.environ.get("CHISPA_E5") or E5
        kw = {"local_files_only": os.environ.get("HF_HUB_OFFLINE") == "1" or os.path.exists(os.path.expanduser("~/hf/hub"))}
        self.tok = AutoTokenizer.from_pretrained(ruta, **kw)
        self.enc = AutoModel.from_pretrained(ruta, **kw).to(device).eval()  # eval también al descongelar: sin dropout
        for p in self.enc.parameters():
            p.requires_grad_(False)
        self.n_desc = descongelar
        if descongelar:
            capas = self.enc.encoder.layer
            for capa in capas[len(capas) - descongelar:]:
                for p in capa.parameters():
                    p.requires_grad_(True)
        self.device, self.max_tok = device, max_tok
        self.cache = OrderedDict()
        self.cache_max = cache_max
        self.msgs = {} if (cache_mensajes and not descongelar) else None  # estados de token por mensaje: solo pruebas en seco
        self.aciertos = self.fallos = 0

    def parametros_entrenables(self):
        return [p for p in self.enc.parameters() if p.requires_grad]

    def estado_enc(self):
        """Pesos de las capas descongeladas (vacío si está congelado), para el checkpoint."""
        return {k: v.detach().cpu() for k, v in self.enc.named_parameters() if v.requires_grad}

    def cargar_enc(self, estado):
        if estado:
            r = self.enc.load_state_dict(estado, strict=False)
            if r.unexpected_keys:
                raise ValueError("claves de e5 inesperadas en el checkpoint: %s" % r.unexpected_keys[:3])

    def invalidar(self):
        """Tira las cachés de vectores: los pesos del codificador acaban de cambiar."""
        self.cache.clear()
        if self.msgs:
            self.msgs.clear()

    def _con_grad(self):
        return self.n_desc > 0 and torch.is_grad_enabled()

    def _pase(self, textos):
        b = self.tok(textos, padding=True, truncation=True, max_length=self.max_tok, return_tensors="pt").to(self.device)
        with torch.autocast(self.device.split(":")[0], dtype=torch.bfloat16, enabled=self.device != "cpu"):
            h = self.enc(**b).last_hidden_state
        return h.float(), b["attention_mask"].bool()

    def tokens(self, textos):
        """Estados de la última capa H (B,T,384) y máscara (B,T) de «query: » + texto."""
        textos = [normalizar_mayusculas(t) for t in textos]
        with torch.set_grad_enabled(self._con_grad()):
            if self.msgs is None:
                return self._pase(["query: " + t for t in textos])
            falta = [t for t in dict.fromkeys(textos) if t not in self.msgs]
            if falta:
                H, m = self._pase(["query: " + t for t in falta])
                for t, h, k in zip(falta, H, m):
                    self.msgs[t] = h[k].cpu()
            T = max(self.msgs[t].shape[0] for t in textos)
            H = torch.zeros(len(textos), T, DIM_E5)
            m = torch.zeros(len(textos), T, dtype=torch.bool)
            for i, t in enumerate(textos):
                n = self.msgs[t].shape[0]
                H[i, :n], m[i, :n] = self.msgs[t], True
            return H.to(self.device), m.to(self.device)

    @staticmethod
    def hash(texto):
        return hashlib.sha1(texto.encode("utf-8")).hexdigest()

    def _vectores(self, textos):
        """(n,384) normalizados de e5 sobre cada texto, en lotes de 256 y con el gradiente del modo actual."""
        out = []
        for i in range(0, len(textos), 256):
            h, m = self._pase(textos[i:i + 256])
            mf = m.unsqueeze(-1).float()
            out.append(F.normalize((h * mf).sum(1) / mf.sum(1).clamp(min=1), dim=-1))
        return torch.cat(out)

    def pasaje(self, textos):
        """(n,384): media normalizada de e5 sobre cada texto (ya con su prefijo «passage: »). Congelado, o sin gradiente,
        con caché por hash; descongelado y entrenando, recalculado cada vez y con gradiente."""
        if self._con_grad():
            self.fallos += len(textos)
            return self._vectores(textos)
        with torch.no_grad():
            claves = [self.hash(t) for t in textos]
            nuevos = {}
            for c, t in zip(claves, textos):
                if c in self.cache:
                    self.aciertos += 1
                    self.cache.move_to_end(c)
                elif c not in nuevos:
                    nuevos[c] = t
            if nuevos:
                self.fallos += len(nuevos)
                v = self._vectores(list(nuevos.values())).cpu()
                for k, x in zip(nuevos, v):
                    self.cache[k] = x
                while len(self.cache) > self.cache_max:
                    self.cache.popitem(last=False)
            return torch.stack([self.cache[c] for c in claves]).to(self.device)


class Ranuras(nn.Module):
    """K consultas aprendidas, atención cruzada (4 cabezas) sobre H, residual + LayerNorm, proyección a d y normalización."""

    def __init__(self, k=K_RANURAS, dim=DIM_E5, d=D, cabezas=4):
        super().__init__()
        self.q = nn.Parameter(torch.randn(k, dim) * 0.02)
        self.atencion = nn.MultiheadAttention(dim, cabezas, batch_first=True)
        self.norma = nn.LayerNorm(dim)
        self.proy = nn.Linear(dim, d)

    def forward(self, H, mascara):
        q = self.q.unsqueeze(0).expand(H.shape[0], -1, -1)
        a, _ = self.atencion(q, H, H, key_padding_mask=~mascara, need_weights=False)
        return F.normalize(self.proy(self.norma(q + a)), dim=-1)  # (B,K,d)


class Torre(nn.Module):
    """MLP de 2 capas sobre el vector de pasaje de e5 → d, normalizado."""

    def __init__(self, dim=DIM_E5, d=D, oculta=512):
        super().__init__()
        self.mlp = nn.Sequential(nn.Linear(dim, oculta), nn.GELU(), nn.Linear(oculta, d))

    def forward(self, v):
        return F.normalize(self.mlp(v), dim=-1)


def maxsim(S, h):
    """S (B,K,d), h (U,d) → (B,U): max_k softplus(h · s_k)."""
    return F.softplus(torch.einsum("bkd,ud->bku", S, h)).max(dim=1).values


def prototipos(modelo, enc, filas_soporte, lote=256, kappa=0.0):
    """Prototipos de clase: (idx {etiqueta: i}, P (C,K,d)). Sin `kappa`, P_c es, ranura a ranura, la media normalizada de las
    ranuras de los ejemplos de soporte de la clase. e5 va sin gradiente (aunque haya capas descongeladas); las ranuras, con el del
    modo actual.

    Con `kappa` > 0 (G.8, shrinkage hacia la descripción; ver formula-shrinkage.md): P_c,k = normaliza(λ_c · torre(desc_c) +
    (1 − λ_c) · media_k(soporte_c)), con λ_c = κ / (κ + n_c), n_c = ejemplos de soporte de la clase y desc_c = `texto_opcion` de la
    clase (pregunta, id y descripción de la tarea). La media es la de las ranuras sin normalizar (norma ≤ 1), y el mismo
    vector de la torre se suma a las K ranuras. Con κ = 0 es exactamente lo de siempre."""
    dev = modelo.ranuras.q.device
    etqs = sorted({r["etiqueta"] for r in filas_soporte})
    idx = {e: i for i, e in enumerate(etqs)}
    suma, n = None, torch.zeros(len(etqs), device=dev)
    for i in range(0, len(filas_soporte), lote):
        fs = filas_soporte[i:i + lote]
        with torch.no_grad():
            H, m = enc.tokens([r["texto"] for r in fs])
        S = modelo.ranuras(H.to(dev), m.to(dev))  # (b,K,d)
        ci = torch.tensor([idx[r["etiqueta"]] for r in fs], device=dev)
        parte = torch.zeros(len(etqs), *S.shape[1:], device=dev).index_add(0, ci, S)
        suma = parte if suma is None else suma + parte
        n = n.index_add(0, ci, torch.ones(len(fs), device=dev))
    if kappa <= 0:
        return idx, F.normalize(suma, dim=-1)
    ref = filas_soporte[0]
    with torch.no_grad():
        h = modelo.torre(enc.pasaje([texto_opcion(ref, e, modelo.texto_torre) for e in etqs]).to(dev))  # (C,d), norma 1
    return idx, mezcla_prototipos(suma, n, h, kappa)


def mezcla_prototipos(suma, n, h, kappa):
    """suma (C,K,d) de ranuras por clase, n (C,) ejemplos, h (C,d) torre de la descripción → P (C,K,d) con shrinkage."""
    lam = (torch.ones_like(n) if math.isinf(kappa) else kappa / (kappa + n)).view(-1, 1, 1)   # λ = ∞: P = torre de la descripción
    media = suma / n.clamp(min=1).view(-1, 1, 1)
    return F.normalize(lam * h.unsqueeze(1) + (1 - lam) * media, dim=-1)


def simproto(S, P):
    """S (B,K,d), P (C,K,d) → (B,C): mean_k max_k' (s_k · P_c,k')."""
    return torch.einsum("bkd,cjd->bckj", S, P).max(dim=-1).values.mean(dim=-1)


def hash_soporte(filas_soporte):
    return hashlib.sha1("\n".join(sorted(r["id"] for r in filas_soporte)).encode("utf-8")).hexdigest()


class CachePrototipos:
    """Prototipos por (tarea, hash del soporte): se calculan una vez. Vale mientras no cambien los pesos: `limpiar()` tras entrenar."""

    def __init__(self):
        self.d, self.calculos = {}, 0

    def obtener(self, modelo, enc, tarea, filas_soporte, kappa=0.0):
        clave = (tarea, hash_soporte(filas_soporte), float(kappa))
        if clave not in self.d:
            self.calculos += 1
            with torch.no_grad():
                self.d[clave] = prototipos(modelo, enc, filas_soporte, kappa=kappa)
        return self.d[clave]

    def limpiar(self):
        self.d.clear()


class SoporteEval:
    """Soporte de evaluación: k por clase de cada tarea, elegido como en T1.7a (`datos.soporte_t17a`, semilla 0)."""

    def __init__(self, train_por_tarea, k=32, semilla=0, kappa=0.0):
        from . import datos
        self.k, self.kappa = k, kappa
        self.filas = {t: [r for _, r in datos.soporte_t17a(rs, k, semilla)] for t, rs in train_por_tarea.items() if rs}
        self.cache = CachePrototipos()

    def protos(self, modelo, enc, tareas):
        return {t: self.cache.obtener(modelo, enc, t, self.filas[t], self.kappa) for t in tareas if t in self.filas}


class Coral(nn.Module):
    """P(y > j) = σ(w·sim − θ_j), j=1..K-1, con θ_j = θ_1 + Σ_{m<j} softplus(δ_m): umbrales ordenados, P decreciente."""

    def __init__(self, niveles):
        super().__init__()
        self.niveles = niveles
        self.w = nn.Parameter(torch.tensor(4.0))
        self.theta1 = nn.Parameter(torch.tensor(2.0))
        self.delta = nn.Parameter(torch.zeros(niveles - 2))

    def umbrales(self):
        return torch.cat([self.theta1.view(1), self.theta1 + torch.cumsum(F.softplus(self.delta), 0)])

    def forward(self, sim):
        """sim (B,) → distribución (B,K)."""
        sup = torch.sigmoid(self.w * sim.unsqueeze(-1) - self.umbrales())  # (B,K-1) = P(y>j)
        uno = torch.ones_like(sup[:, :1])
        return (torch.cat([uno, sup], 1) - torch.cat([sup, 0 * uno], 1)).clamp(min=0)

    def acumuladas(self, sim):
        """sim (B,) → P(y>j) (B,K-1), sin pasar por la distribución."""
        return torch.sigmoid(self.w * sim.unsqueeze(-1) - self.umbrales())

    @staticmethod
    def etiqueta(sup):
        """Mediana CORAL, como el runtime: sup (B,K-1) = P(y>j) → nivel predicho (B,) en 0..K-1 = número de umbrales con
        P(y>j) > 0,5 (se cuentan todos, no el primer cruce: vale con acumuladas no monótonas). No es el argmax de P(y=k)."""
        return (sup > 0.5).sum(-1)

    @staticmethod
    def esperado(p):
        return (p * torch.arange(1, p.shape[1] + 1, device=p.device, dtype=p.dtype)).sum(-1)


class ModeloL2(nn.Module):
    """Parte entrenable de L2 (el codificador e5 va aparte, congelado)."""

    def __init__(self, k=K_RANURAS, d=D, texto_torre="v1"):
        super().__init__()
        self.texto_torre = texto_torre  # versión del texto de torre (configuración del modelo; va en el checkpoint)
        self.ranuras = Ranuras(k, DIM_E5, d)
        self.torre = Torre(DIM_E5, d)
        self.log_t = nn.ParameterDict({"choice": nn.Parameter(torch.tensor(math.log(0.02)))})
        self.ab = nn.ParameterDict({"noul": nn.Parameter(torch.tensor([4.0, -4.0]))})  # a, b
        self.coral = nn.ModuleDict()
        self.beta = nn.ParameterDict({t: nn.Parameter(torch.tensor(1.0)) for t in TIPOS_BETA})  # peso de simproto, por tipo

    def load_state_dict(self, estado, strict=True):
        """Admite checkpoints anteriores a T2.1b (sin β): conservan el β actual."""
        estado = dict(estado)
        for k, v in self.state_dict().items():
            if k.startswith("beta.") and k not in estado:
                estado[k] = v
        return super().load_state_dict(estado, strict)

    def asegurar_cabeza(self, clave, device=None):
        if clave.startswith("score") and clave not in self.coral:
            self.coral[clave] = Coral(int(clave[5:])).to(device or self.ranuras.q.device)

    def parametros_cabezas(self):
        return [*self.log_t.parameters(), *self.ab.parameters(), *self.coral.parameters(), *self.beta.parameters()]

    def grupos_optimizador(self, lr=3e-4, lr_torre=1e-4, wd=0.01):
        return [{"params": list(self.ranuras.parameters()) + self.parametros_cabezas(), "lr": lr, "weight_decay": wd},
                {"params": list(self.torre.parameters()), "lr": lr_torre, "weight_decay": wd}]

    def _simproto(self, S, filas, protos):
        """Lista (una por fila) de tensores (len(opciones),) con simproto por opción, o None si la fila no tiene prototipos.
        La clase de una opción es su nombre original (`origen`, si la fila está renombrada); una opción sin prototipo vale 0."""
        out = [None] * len(filas)
        for t in {r["tarea"] for r in filas} if protos else ():
            if t not in protos:
                continue
            idx, P = protos[t]
            ii = [i for i, r in enumerate(filas) if r["tarea"] == t]
            sp = simproto(S[ii], P)  # (b,C)
            for j, i in enumerate(ii):
                col = [idx.get(o, -1) for o in filas[i].get("origen", filas[i]["opciones"])]
                v = sp[j, [max(c, 0) for c in col]]
                out[i] = v * torch.tensor([c >= 0 for c in col], device=v.device, dtype=v.dtype)
        return out

    def forward(self, filas, enc, entrenar=True, protos=None):
        """Devuelve (probs: lista de tensores por fila en el orden de `opciones`, perdidas: dict o None).
        `protos`: {tarea: (idx, P)} de `prototipos`; sin él (o sin la tarea de la fila) es el modo sin soporte de la ronda 1."""
        dev = self.ranuras.q.device
        for k in {clave_cabeza(r) for r in filas}:
            self.asegurar_cabeza(k, dev)
        H, m = enc.tokens([r["texto"] for r in filas])
        S = self.ranuras(H.to(dev), m.to(dev))
        textos, pos, fila_txt = [], {}, []
        for r in filas:
            ts = [texto_opcion(r, o, self.texto_torre) for o in r["opciones"]] if r["tipo"] == "choice" else [texto_consulta(r, self.texto_torre)]
            ix = []
            for t in ts:
                if t not in pos:
                    pos[t] = len(textos)
                    textos.append(t)
                ix.append(pos[t])
            fila_txt.append(ix)
        h = self.torre(enc.pasaje(textos).to(dev))
        sim = maxsim(S, h)  # (B,U)
        sp_filas = self._simproto(S, filas, protos)
        probs, p_ce, p_kl, p_nce, p_b = [], [], [], [], []
        T = self.log_t["choice"].exp().clamp(min=5e-3)
        for i, r in enumerate(filas):
            ix = torch.tensor(fila_txt[i], device=dev)
            s = sim[i, ix]
            tipo, ops = r["tipo"], r["opciones"]
            y = ops.index(r["etiqueta"])
            sp = sp_filas[i]
            if tipo == "score":
                niv = niveles_score(ops)
            if tipo == "choice":
                lg = (s if sp is None else s + self.beta["choice"] * sp) / T
                p = F.softmax(lg, -1)
                ce = F.cross_entropy(lg.unsqueeze(0), torch.tensor([y], device=dev))
                # InfoNCE: las opciones de las demás filas del lote (todo el conjunto único) son negativos.
                nce = F.cross_entropy((sim[i] / T).unsqueeze(0), torch.tensor([fila_txt[i][y]], device=dev))
                p_nce.append(nce)
            elif tipo == "noul":
                a, b = self.ab["noul"]
                pt = torch.sigmoid(a * (s[0] + self._ajuste(sp, "noul")) + b)
                p = torch.stack([1 - pt, pt])
                ce = -torch.log(p[y].clamp(min=1e-7))
            else:
                # CORAL se indexa por el nivel (orden por int), no por la posición declarada; se devuelve en el orden de `opciones`
                if sp is not None:  # el soporte llega en el orden declarado; el linspace de `_ajuste` va por nivel
                    sp = sp[torch.tensor([ops.index(n) for n in niv], device=sp.device)]
                pn = self.coral["score%d" % len(ops)](s[:1] + self._ajuste(sp, "score"))[0]
                ce = -torch.log(pn[niv.index(r["etiqueta"])].clamp(min=1e-7))
                p = pn[torch.tensor([niv.index(o) for o in ops], device=pn.device)]
            probs.append(p)
            if not entrenar:
                continue
            p_ce.append(ce)
            t1 = F.one_hot(torch.tensor(y), len(ops)).float().to(dev)
            p_b.append(((p - t1) ** 2).sum())
            bl = blanda_vector(r)
            if bl is not None:
                bl = bl.to(dev)
                p_kl.append((bl * (torch.log(bl.clamp(min=1e-8)) - torch.log(p.clamp(min=1e-8)))).sum())
        if not entrenar:
            return probs, None
        cero = sim.sum() * 0
        media = lambda xs: torch.stack(xs).mean() if xs else cero
        ps = {"ce": media(p_ce), "kl": media(p_kl), "nce": media(p_nce), "brier": media(p_b)}
        ps["total"] = ps["ce"] + LAMBDA_KL * ps["kl"] + LAMBDA_NCE * ps["nce"] + LAMBDA_B * ps["brier"]
        return probs, ps


    def _ajuste(self, sp, tipo):
        """β · (simproto ponderado de −1 a +1 por la posición de la clase, sobre la suma de pesos positivos): con 2 clases es
        sp(true) − sp(false). 0 sin prototipos."""
        if sp is None:
            return 0.0
        w = torch.linspace(-1, 1, len(sp), device=sp.device)
        return self.beta[tipo] * (w * sp).sum() / w.clamp(min=0).sum()


def blanda_vector(fila):
    """Distribución blanda de la fila sobre `opciones`, renormalizada; None si no hay o no cae en las opciones."""
    bl = fila.get("blanda")
    if not bl:
        return None
    v = torch.tensor([max(float(bl.get(o, 0.0)), 0.0) for o in fila["opciones"]])
    s = v.sum()
    return None if s <= 0 else v / s
