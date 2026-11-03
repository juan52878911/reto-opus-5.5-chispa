"""Vídeo vertical para reels (1080 × 1920, 9:16, 30 fps, H.264 yuv420p) de una partida guardada por `jugar`.

Campo girado: la pala izquierda (Laya) arriba y la derecha (Chispa) abajo, cada una con su panel pegado (opción elegida,
barras de confianza, latencia). Marcador grande arriba. Deja libres ~220 px arriba y ~420 px abajo (interfaz de reels).
Abre con un título de 2 s y elige el tramo de `--segundos` con más golpes de pala.

    python -m pong vertical traza.json salida.mp4 [--segundos 40]"""
from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from .motor import ALTO, ALTO_PALA, ANCHO, GROSOR_PALA, MARGEN_PALA, RADIO, TICS_POR_S
from .renderizar import AMBAR, AZUL, BORDE, CORAL, FONDO, LILA, MENTA, PANEL, TENUE, TEXTO, _barra, _fuente, ruta_ffmpeg

W, H = 1080, 1920
SEGURO_ARRIBA, SEGURO_ABAJO = 220, 420
COLOR = {"izquierda": LILA, "derecha": AMBAR}
ESC = 0.95
FW, FH = int(ALTO * ESC), int(ANCHO * ESC)          # campo girado: ancho = ALTO lógico, alto = ANCHO lógico
FX0, FY0 = (W - FW) // 2, 640
PANEL_LAYA = (40, 390, W - 40, 625)
PANEL_CHISPA = (40, FY0 + FH + 15, W - 40, FY0 + FH + 250)
TITULO_S = 2.0


def a_pantalla(x: float, y: float):
    """Coordenadas del juego → pantalla: x del juego crece hacia abajo (Laya arriba), y del juego crece hacia la derecha."""
    return FX0 + y * ESC, FY0 + x * ESC


def golpes_por_tic(tics: List[list]) -> List[int]:
    """1 en los tics donde la pelota cambia de sentido horizontal sin que cambie el marcador (golpe de pala)."""
    out = [0] * len(tics)
    for i in range(2, len(tics)):
        a, b, c = tics[i - 2], tics[i - 1], tics[i]
        if (b[1] - a[1]) * (c[1] - b[1]) < 0 and c[5:7] == b[5:7]:
            out[i] = 1
    return out


def mejor_tramo(tics: List[list], segundos: float) -> int:
    """Índice del primer tic del tramo de `segundos` con más golpes."""
    n = int(segundos * TICS_POR_S)
    if len(tics) <= n:
        return 0
    g = golpes_por_tic(tics)
    s = sum(g[:n])
    mejor, ini = s, 0
    for i in range(1, len(tics) - n + 1):
        s += g[i + n - 1] - g[i - 1]
        if s > mejor:
            mejor, ini = s, i
    return ini


def _panel(d, caja, nombre: str, lado: str, dec: Optional[dict], hist: List[dict]):
    x0, y0, x1, y1 = caja
    d.rounded_rectangle(caja, radius=22, fill=PANEL, outline=COLOR[lado], width=4)
    d.text((x0 + 28, y0 + 18), nombre, font=_fuente(52, True), fill=COLOR[lado])
    if dec is None:
        return
    d.text((x1 - 28, y0 + 14), f"{dec['ms']:.0f} ms", font=_fuente(56, True), fill=TEXTO, anchor="ra")
    ok = [h for h in hist if not h.get("error")]
    if ok:
        coinc = 100 * sum(h["elegida"] == h["optima"] for h in ok) / len(ok)
        d.text((x0 + 300, y0 + 34), f"acierta {coinc:.0f} %", font=_fuente(30, True), fill=MENTA if coinc >= 60 else CORAL)
    cw = (x1 - x0 - 56) // 3
    for i, nombre_op in enumerate(("subir", "quieta", "bajar")):
        o = next(o for o in dec["opciones"] if o["nombre"] == nombre_op)
        p = float(dec["probs"].get(o["id"], 0.0))
        elegida = o["id"] == dec["elegida"]
        cx = x0 + 28 + i * cw
        etiqueta = {"subir": "← izq.", "quieta": "quieta", "bajar": "der. →"}[nombre_op]
        d.text((cx, y0 + 100), etiqueta, font=_fuente(34, True), fill=COLOR[lado] if elegida else TEXTO)
        if o["id"] == dec["optima"]:
            d.text((cx + cw - 24, y0 + 108), "mejor", font=_fuente(26, True), fill=MENTA, anchor="ra")
        _barra(d, cx, y0 + 150, cw - 24, 26, p, MENTA if elegida else AZUL)
        d.text((cx, y0 + 180), f"{p * 100:.0f} %", font=_fuente(48, True), fill=TEXTO)


PIE = "zero-shot · mismas opciones · tiempo real"


def dibujar(t: list, nombres: dict, ultima: dict, hist: dict, titulo: Optional[str] = None):
    from PIL import Image, ImageDraw
    tic, bx, by, pl, pr, ptl, ptr = t[:7]
    im = Image.new("RGB", (W, H), FONDO)
    d = ImageDraw.Draw(im)
    # marcador (justo bajo la zona segura de arriba)
    d.text((W // 2 - 150, 300), str(ptl), font=_fuente(130, True), fill=COLOR["izquierda"], anchor="mm")
    d.text((W // 2, 300), ":", font=_fuente(110, True), fill=TENUE, anchor="mm")
    d.text((W // 2 + 150, 300), str(ptr), font=_fuente(130, True), fill=COLOR["derecha"], anchor="mm")
    d.text((W // 2 - 150, 372), nombres["izquierda"], font=_fuente(30, True), fill=COLOR["izquierda"], anchor="mm")
    d.text((W // 2 + 150, 372), nombres["derecha"], font=_fuente(30, True), fill=COLOR["derecha"], anchor="mm")
    _panel(d, PANEL_LAYA, nombres["izquierda"], "izquierda", ultima.get("izquierda"), hist["izquierda"])
    # campo girado
    d.rounded_rectangle([FX0 - 8, FY0 - 8, FX0 + FW + 8, FY0 + FH + 8], radius=16, fill=(18, 24, 44), outline=BORDE, width=3)
    for xx in range(FX0, FX0 + FW, 34):
        d.rectangle([xx, FY0 + FH // 2 - 2, xx + 18, FY0 + FH // 2 + 2], fill=BORDE)
    for lado, yc in (("izquierda", pl), ("derecha", pr)):
        xf = MARGEN_PALA if lado == "izquierda" else ANCHO - MARGEN_PALA - GROSOR_PALA
        ax, ay = a_pantalla(xf, yc - ALTO_PALA / 2)
        bx2, by2 = a_pantalla(xf + GROSOR_PALA, yc + ALTO_PALA / 2)
        d.rounded_rectangle([ax, ay, bx2, by2], radius=6, fill=COLOR[lado])
    px, py = a_pantalla(bx, by)
    r = RADIO * ESC * 1.2
    d.ellipse([px - r, py - r, px + r, py + r], fill=TEXTO)
    _panel(d, PANEL_CHISPA, nombres["derecha"], "derecha", ultima.get("derecha"), hist["derecha"])
    d.text((W // 2, PANEL_CHISPA[3] + 30), PIE, font=_fuente(30), fill=TENUE, anchor="mm")
    if titulo:
        capa = Image.new("RGBA", (W, H), (14, 18, 32, 215))
        im = Image.alpha_composite(im.convert("RGBA"), capa).convert("RGB")
        d = ImageDraw.Draw(im)
        a, b = titulo.split(" · ", 1) if " · " in titulo else (titulo, "")
        d.text((W // 2, H // 2 - 70), a, font=_fuente(88, True), fill=TEXTO, anchor="mm")
        d.text((W // 2, H // 2 + 40), b, font=_fuente(52, True), fill=AMBAR, anchor="mm")
    return im


def fotogramas(traza: dict, desde: int, hasta: int, titulo: str):
    nombres = {l: traza["resumen"]["agentes"][l]["nombre"] for l in ("izquierda", "derecha")}
    decs = sorted(traza["decisiones"], key=lambda x: x["tic_aplicada"])
    k, ultima, hist, i = 0, {}, {"izquierda": [], "derecha": []}, 0
    n_titulo = int(TITULO_S * TICS_POR_S)
    for t in traza["tics"]:
        while k < len(decs) and decs[k]["tic_aplicada"] <= t[0]:
            ultima[decs[k]["lado"]] = decs[k]
            hist[decs[k]["lado"]].append(decs[k])
            k += 1
        if t[0] == desde:
            for _ in range(n_titulo):
                yield dibujar(t, nombres, ultima, hist, titulo)
        if desde <= t[0] < hasta:
            yield dibujar(t, nombres, ultima, hist)
            i += 1


def main(argv=None) -> int:
    from .renderizar import crear_mp4
    import pong.renderizar as R
    ap = argparse.ArgumentParser(prog="vertical", description=__doc__.splitlines()[0])
    ap.add_argument("traza")
    ap.add_argument("salida")
    ap.add_argument("--segundos", type=float, default=40.0)
    ap.add_argument("--titulo", default="Laya vs Chispa · Pong en tiempo real")
    ap.add_argument("--pie", default=PIE)
    a = ap.parse_args(argv)
    with open(a.traza, encoding="utf-8") as f:
        traza = json.load(f)
    ini = traza["tics"][mejor_tramo(traza["tics"], a.segundos)][0]
    fin = ini + int(a.segundos * TICS_POR_S)
    R.W, R.H = W, H   # crear_mp4 usa el tamaño del módulo
    globals()["PIE"] = a.pie
    n = crear_mp4(fotogramas(traza, ini, fin, a.titulo), a.salida)
    print(f"vertical: {n} fotogramas ({n / TICS_POR_S:.1f} s, desde {ini / TICS_POR_S:.1f} s de partida) en {a.salida}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
