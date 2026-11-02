"""Renderizador: traza JSONL → fotogramas (Pillow) → MP4 1080p a 30 fps (ffmpeg). Pillow y ffmpeg solo se usan aquí.

`python3 -m caida.renderizar --traza traza.jsonl --salida partida.mp4`
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from typing import Iterator, List, Optional, Tuple

from .motor import ALTO, ANCHO, CHISPA, NORMAL, aplicar, Colocacion
from .panel import paneles
from .traza import leer

W, H, FPS = 1920, 1080, 30

# Identidad visual de Chispa: fondo noche, acento ámbar «chispa», verde azulado para lo que decide Chispa.
FONDO, PANEL, BORDE = (14, 18, 32), (24, 30, 52), (52, 62, 98)
AMBAR, MENTA, CORAL, TEXTO, TENUE = (255, 176, 32), (64, 214, 178), (255, 107, 107), (234, 238, 250), (136, 146, 178)
COLORES_PIEZA = {"domino": (110, 142, 255), "diagonal": (178, 120, 255), "recta3": (64, 214, 178), "ele3": (255, 140, 96),
                 "pinza": (96, 200, 255), "punta": (240, 120, 190), "gancho": (150, 220, 110)}
LADO = 56  # px por celda del tablero
TX0, TY0 = 90, (H - ALTO * LADO) // 2
PX0 = TX0 + ANCHO * LADO + 90


def hay_pillow() -> bool:
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        return False


def ruta_ffmpeg() -> Optional[str]:
    """ffmpeg del PATH o, si no hay, el que trae imageio-ffmpeg."""
    f = shutil.which("ffmpeg")
    if f:
        return f
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _fuente(tam: int, negrita: bool = False):
    from PIL import ImageFont
    for n in (("DejaVuSans-Bold.ttf" if negrita else "DejaVuSans.ttf"), "Arial.ttf"):
        try:
            return ImageFont.truetype(n, tam)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size=tam)
    except TypeError:
        return ImageFont.load_default()


def _celda(d, f, c, color, chispa=False, alfa=False):
    x, y = TX0 + c * LADO, TY0 + f * LADO
    d.rounded_rectangle([x + 2, y + 2, x + LADO - 3, y + LADO - 3], radius=9, fill=color)
    if chispa:
        cx, cy = x + LADO // 2, y + LADO // 2
        d.polygon([(cx, cy - 18), (cx + 6, cy - 6), (cx + 18, cy), (cx + 6, cy + 6), (cx, cy + 18),
                   (cx - 6, cy + 6), (cx - 18, cy), (cx - 6, cy - 6)], fill=AMBAR)


def dibujar_fotograma(panel: dict, tablero: List[str], pieza_celdas: List[Tuple[int, int, int]], nombre_pieza: str,
                      resaltar_columnas: Tuple[int, ...] = (), destello: float = 0.0):
    """Devuelve una imagen PIL 1920×1080. `tablero`: filas de texto (. # *). `pieza_celdas`: celdas absolutas que se
    dibujan encima (la pieza cayendo o ya apoyada)."""
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (W, H), FONDO)
    d = ImageDraw.Draw(im)
    d.text((TX0, 28), "CHISPA: CAÍDA", font=_fuente(40, True), fill=AMBAR)
    d.rounded_rectangle([TX0 - 10, TY0 - 10, TX0 + ANCHO * LADO + 10, TY0 + ALTO * LADO + 10], radius=14, fill=PANEL, outline=BORDE, width=3)
    for c in resaltar_columnas:
        d.rectangle([TX0 + c * LADO, TY0, TX0 + (c + 1) * LADO, TY0 + ALTO * LADO],
                    fill=tuple(int(a + (b - a) * destello) for a, b in zip(PANEL, AMBAR)))
    for f, fila in enumerate(tablero):
        for c, ch in enumerate(fila):
            if ch != ".":
                _celda(d, f, c, (88, 100, 150), chispa=(ch == "*"))
    col = COLORES_PIEZA.get(nombre_pieza, MENTA)
    for f, c, s in pieza_celdas:
        if f >= 0:
            _celda(d, f, c, col, chispa=(s == CHISPA))
    _panel(d, panel)
    return im


def _barra(d, x, y, w, h, p, color, fondo=BORDE):
    d.rounded_rectangle([x, y, x + w, y + h], radius=5, fill=fondo)
    if p > 0:
        d.rounded_rectangle([x, y, x + max(8, int(w * min(1.0, p))), y + h], radius=5, fill=color)


def _panel(d, p: dict) -> None:
    x0, y, ancho = PX0, 70, W - PX0 - 70
    d.rounded_rectangle([x0 - 20, 40, W - 50, H - 40], radius=18, fill=PANEL, outline=BORDE, width=3)
    d.text((x0, y), f"Turno {p['turno']}", font=_fuente(26, True), fill=TENUE)
    d.text((x0 + ancho - 330, y), f"Puntos {p['puntos']}   Filas {p['filas']}", font=_fuente(26, True), fill=AMBAR)
    y += 50
    d.text((x0, y), p["jugada"][:78], font=_fuente(22), fill=TEXTO)
    y += 44
    d.text((x0, y), "Probabilidad por opción", font=_fuente(20, True), fill=TENUE)
    y += 34
    for b in p["barras"]:
        d.text((x0, y), b["id"], font=_fuente(22, True), fill=AMBAR if b["elegida"] else TEXTO)
        _barra(d, x0 + 36, y + 4, 340, 20, b["prob"], MENTA if b["elegida"] else (110, 142, 255))
        d.text((x0 + 392, y), f"{b['prob'] * 100:4.0f} %  {b['descripcion'][:42]}", font=_fuente(18), fill=TEXTO)
        y += 36
    y += 14
    r = p["riesgo"]
    d.text((x0, y), f"Riesgo (1–5): {r['nivel'] if r['nivel'] is not None else '—'}", font=_fuente(22, True), fill=CORAL if (r["nivel"] or 0) >= 4 else TEXTO)
    for i, n in enumerate(r["niveles"]):
        _barra(d, x0 + 250 + i * 92, y + 6, 80, 16, n["prob"], CORAL)
    y += 50
    c = p["completa"]
    pt = "—" if c["p_si"] is None else f"{c['p_si'] * 100:.0f} %"
    d.text((x0, y), f"¿Completa fila?  {c['texto'].upper()}  (p sí = {pt})", font=_fuente(22, True), fill=TEXTO)
    y += 56
    for i, cp in enumerate(p["capas"]):
        bx = x0 + i * 140
        d.rounded_rectangle([bx, y, bx + 124, y + 44], radius=10, fill=(AMBAR if cp["activa"] else FONDO), outline=BORDE, width=2)
        d.text((bx + 20, y + 8), cp["id"], font=_fuente(24, True), fill=(FONDO if cp["activa"] else TENUE))
    y += 76
    lat = "—" if p["latencia_ms"] is None else f"{p['latencia_ms']:.1f} ms"
    dps = "—" if p["decisiones_por_s"] is None else f"{p['decisiones_por_s']:.1f}"
    d.text((x0, y), f"Latencia {lat}     Decisiones/s {dps}", font=_fuente(24), fill=TEXTO)
    y += 46
    d.text((x0, y), f"Escudo: {p['escudo']} intervenciones de {p['decisiones']} decisiones", font=_fuente(24, True), fill=CORAL if p["escudo"] else MENTA)


def fotogramas(turnos: List[dict], seg_por_turno: float = 0.6, fps: int = FPS) -> Iterator["object"]:
    """Genera imágenes PIL: la pieza cae hasta su sitio y, si hay limpieza, el tablero se actualiza con un destello."""
    ps = paneles(turnos)
    n = max(4, int(seg_por_turno * fps))
    caida = n // 2
    for t, p in zip(turnos, ps):
        celdas = [tuple(c) for c in t["celdas_elegidas"]]
        fmin = min(c[0] for c in celdas)
        for k in range(caida):
            baja = (fmin * (k + 1)) // caida  # filas que ha bajado desde la fila 0
            yield dibujar_fotograma(p, t["tablero"], [(f - fmin + baja, c, s) for f, c, s in celdas], t["pieza"]["nombre"])
        # tras apoyar: tablero con la pieza y, si limpia, destello de las columnas borradas
        con = [list(f) for f in t["tablero"]]
        for f, c, s in celdas:
            con[f][c] = "*" if s == CHISPA else "#"
        for k in range(n - caida):
            if t["filas"] or t["columnas_borradas"]:
                yield dibujar_fotograma(p, ["".join(f) for f in con], [], t["pieza"]["nombre"],
                                        tuple(t["columnas_borradas"]), 1.0 - k / max(1, n - caida))
            else:
                yield dibujar_fotograma(p, ["".join(f) for f in con], [], t["pieza"]["nombre"])


def crear_mp4(ims: Iterator["object"], salida: str, fps: int = FPS) -> int:
    """Manda los fotogramas (RGB crudo) a ffmpeg. Devuelve cuántos escribió."""
    ff = ruta_ffmpeg()
    if not ff:
        raise RuntimeError("no hay ffmpeg: ni en el PATH ni imageio-ffmpeg")
    cmd = [ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-movflags", "+faststart", salida]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n = 0
    try:
        for im in ims:
            p.stdin.write(im.tobytes())
            n += 1
    finally:
        p.stdin.close()
        rc = p.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg terminó con código {rc}")
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="renderizar", description=__doc__.splitlines()[0])
    ap.add_argument("--traza", required=True)
    ap.add_argument("--salida", required=True, help="fichero .mp4")
    ap.add_argument("--seg-por-turno", type=float, default=0.6)
    ap.add_argument("--max-turnos", type=int, default=0, help="0 = todos")
    a = ap.parse_args(argv)
    if not hay_pillow():
        print("renderizar: falta Pillow (pip install -r requirements-render.txt); se salta el vídeo", file=sys.stderr)
        return 3
    if not ruta_ffmpeg():
        print("renderizar: falta ffmpeg (ni en el PATH ni imageio-ffmpeg); se salta el vídeo", file=sys.stderr)
        return 3
    _, turnos = leer(a.traza)
    if a.max_turnos:
        turnos = turnos[:a.max_turnos]
    if not turnos:
        print("renderizar: la traza no tiene turnos", file=sys.stderr)
        return 1
    n = crear_mp4(fotogramas(turnos, a.seg_por_turno), a.salida)
    print(f"renderizar: {n} fotogramas ({n / FPS:.1f} s a {FPS} fps, {W}x{H}) en {a.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
