"""Vídeo 1080p a 30 fps (un fotograma por tic) de una partida guardada por `jugar`: el campo en el centro, el marcador arriba y,
a cada lado, el panel del modelo que lleva esa pala (opción elegida, barras de confianza y latencia). Pillow y ffmpeg solo aquí.

    python -m pong renderizar traza.json salida.mp4 [--desde-s 0] [--segundos 60]"""
from __future__ import annotations

import argparse
import json
import shutil
import statistics
import subprocess
import sys
from typing import List, Optional

from .motor import ALTO, ALTO_PALA, ANCHO, GROSOR_PALA, MARGEN_PALA, RADIO, TICS_POR_S

W, H = 1920, 1080
FONDO, PANEL, BORDE = (14, 18, 32), (24, 30, 52), (52, 62, 98)
AMBAR, MENTA, CORAL, AZUL, TEXTO, TENUE, LILA = (255, 176, 32), (64, 214, 178), (255, 107, 107), (110, 142, 255), (234, 238, 250), (136, 146, 178), (190, 140, 255)
COLOR = {"izquierda": LILA, "derecha": AMBAR}  # Laya lila, Chispa ámbar
ESC = 1.4
CX0, CY0 = (W - int(ANCHO * ESC)) // 2, 250
PW = CX0 - 70  # ancho de cada panel


def _fuente(tam: int, negrita: bool = False):
    from PIL import ImageFont
    for n in (("DejaVuSans-Bold.ttf" if negrita else "DejaVuSans.ttf"), ("Arial Bold.ttf" if negrita else "Arial.ttf")):
        try:
            return ImageFont.truetype(n, tam)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size=tam)
    except TypeError:
        return ImageFont.load_default()


def ruta_ffmpeg() -> Optional[str]:
    f = shutil.which("ffmpeg")
    if f:
        return f
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _barra(d, x, y, w, h, p, color):
    d.rounded_rectangle([x, y, x + w, y + h], radius=5, fill=BORDE)
    if p > 0:
        d.rounded_rectangle([x, y, x + max(8, int(w * min(1.0, p))), y + h], radius=5, fill=color)


def _panel(d, x0: int, nombre: str, lado: str, dec: Optional[dict], hist: List[dict]):
    d.rounded_rectangle([x0, 230, x0 + PW, H - 40], radius=18, fill=PANEL, outline=COLOR[lado], width=3)
    x, y = x0 + 24, 254
    d.text((x, y), nombre, font=_fuente(34, True), fill=COLOR[lado])
    d.text((x, y + 46), "pala " + lado, font=_fuente(18), fill=TENUE)
    y += 96
    if dec is None:
        d.text((x, y), "esperando la primera decisión…", font=_fuente(20), fill=TENUE)
        return
    d.text((x, y), "¿Qué hago con la pala?", font=_fuente(20, True), fill=TENUE)
    y += 38
    for o in sorted(dec["opciones"], key=lambda o: int(o["id"])):
        p = float(dec["probs"].get(o["id"], 0.0))
        elegida = o["id"] == dec["elegida"]
        d.text((x, y), o["nombre"], font=_fuente(24, True), fill=COLOR[lado] if elegida else TEXTO)
        if o["id"] == dec["optima"]:
            d.text((x + 120, y + 4), "óptima", font=_fuente(16, True), fill=MENTA)
        _barra(d, x, y + 34, PW - 140, 22, p, MENTA if elegida else AZUL)
        d.text((x + PW - 128, y + 32), f"{p * 100:3.0f} %", font=_fuente(22, True), fill=TEXTO)
        d.text((x, y + 62), f"queda a {o['distancia']} px", font=_fuente(17), fill=TENUE)
        y += 104
    y += 6
    d.text((x, y), f"{dec['ms']:.0f} ms", font=_fuente(44, True), fill=TEXTO)
    d.text((x + 150, y + 18), "latencia de esta decisión", font=_fuente(17), fill=TENUE)
    y += 70
    ok = [h for h in hist if not h.get("error")]
    if ok:
        coinc = 100 * sum(h["elegida"] == h["optima"] for h in ok) / len(ok)
        p50 = statistics.median(h["ms"] for h in ok)
        d.text((x, y), f"elige la óptima {coinc:.0f} %", font=_fuente(22, True), fill=MENTA if coinc >= 60 else CORAL)
        d.text((x, y + 34), f"p50 {p50:.0f} ms · {len(ok)} decisiones", font=_fuente(20), fill=TEXTO)


def dibujar(t: list, nombres: dict, ultima: dict, hist: dict, titulo: str):
    from PIL import Image, ImageDraw
    tic, bx, by, pl, pr, ptl, ptr = t[:7]
    im = Image.new("RGB", (W, H), FONDO)
    d = ImageDraw.Draw(im)
    d.text((W // 2, 46), titulo, font=_fuente(28, True), fill=TENUE, anchor="mm")
    d.text((W // 2 - 90, 130), str(ptl), font=_fuente(96, True), fill=COLOR["izquierda"], anchor="mm")
    d.text((W // 2, 130), ":", font=_fuente(80, True), fill=TENUE, anchor="mm")
    d.text((W // 2 + 90, 130), str(ptr), font=_fuente(96, True), fill=COLOR["derecha"], anchor="mm")
    d.text((W // 2, 200), f"{tic / TICS_POR_S:5.1f} s · a 7 puntos", font=_fuente(20), fill=TENUE, anchor="mm")
    fx1, fy1 = CX0 + int(ANCHO * ESC), CY0 + int(ALTO * ESC)
    d.rounded_rectangle([CX0 - 8, CY0 - 8, fx1 + 8, fy1 + 8], radius=14, fill=(18, 24, 44), outline=BORDE, width=3)
    for yy in range(CY0, fy1, 34):
        d.rectangle([W // 2 - 2, yy, W // 2 + 2, yy + 18], fill=BORDE)
    for lado, yc in (("izquierda", pl), ("derecha", pr)):
        xf = MARGEN_PALA if lado == "izquierda" else ANCHO - MARGEN_PALA - GROSOR_PALA
        d.rounded_rectangle([CX0 + xf * ESC, CY0 + (yc - ALTO_PALA / 2) * ESC, CX0 + (xf + GROSOR_PALA) * ESC,
                             CY0 + (yc + ALTO_PALA / 2) * ESC], radius=6, fill=COLOR[lado])
    r = RADIO * ESC
    d.ellipse([CX0 + bx * ESC - r, CY0 + by * ESC - r, CX0 + bx * ESC + r, CY0 + by * ESC + r], fill=TEXTO)
    _panel(d, 40, nombres["izquierda"], "izquierda", ultima.get("izquierda"), hist["izquierda"])
    _panel(d, W - 40 - PW, nombres["derecha"], "derecha", ultima.get("derecha"), hist["derecha"])
    return im


def fotogramas(traza: dict, desde: int, hasta: int, titulo: str):
    nombres = {l: traza["resumen"]["agentes"][l]["nombre"] for l in ("izquierda", "derecha")}
    decs = sorted(traza["decisiones"], key=lambda x: x["tic_aplicada"])
    k, ultima, hist = 0, {}, {"izquierda": [], "derecha": []}
    for t in traza["tics"]:
        while k < len(decs) and decs[k]["tic_aplicada"] <= t[0]:
            ultima[decs[k]["lado"]] = decs[k]
            hist[decs[k]["lado"]].append(decs[k])
            k += 1
        if desde <= t[0] < hasta:
            yield dibujar(t, nombres, ultima, hist, titulo)


def crear_mp4(ims, salida: str) -> int:
    ff = ruta_ffmpeg()
    if not ff:
        raise RuntimeError("no hay ffmpeg")
    cmd = [ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(TICS_POR_S), "-i", "-",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", "-tune", "animation", "-movflags", "+faststart", salida]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n = 0
    try:
        for im in ims:
            p.stdin.write(im.tobytes())
            n += 1
    finally:
        p.stdin.close()
        rc = p.wait()
    if rc:
        raise RuntimeError(f"ffmpeg terminó con código {rc}")
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="renderizar", description=__doc__.splitlines()[0])
    ap.add_argument("traza")
    ap.add_argument("salida")
    ap.add_argument("--desde-s", type=float, default=0.0)
    ap.add_argument("--segundos", type=float, default=60.0)
    ap.add_argument("--titulo", default="Chispa: Pong · Laya contra Chispa en tiempo real (zero-shot, mismas opciones)")
    a = ap.parse_args(argv)
    with open(a.traza, encoding="utf-8") as f:
        traza = json.load(f)
    desde = int(a.desde_s * TICS_POR_S)
    n = crear_mp4(fotogramas(traza, desde, desde + int(a.segundos * TICS_POR_S), a.titulo), a.salida)
    print(f"renderizar: {n} fotogramas ({n / TICS_POR_S:.1f} s) en {a.salida}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
