"""Renderizador: traza JSONL → fotogramas (Pillow) → MP4 1080p a 30 fps (ffmpeg), de 20 a 40 s.
Pillow y ffmpeg solo se usan aquí; el plan de fotogramas (`plan`) es Python puro.

`python3 -m serpiente.renderizar --traza traza.jsonl --salida partida.mp4`
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from typing import Iterator, List, Optional, Tuple

from .estado import posicion_comida
from .motor import GIROS, LADO, MAX_PASOS, mover, nueva_dir
from .traza import leer

W, H, FPS = 1920, 1080, 30
MIN_S, MAX_S = 20.0, 40.0          # duración permitida del vídeo
SEG_IDEAL, FOTOS_MIN = 0.5, 3      # segundos por paso si cabe; mínimo de fotogramas por paso (0,1 s)
REMATE_S = 1.5                     # fotograma final retenido

# Identidad visual propia: fondo noche, serpiente menta, chispa ámbar.
FONDO, PANEL, BORDE, REJILLA = (12, 16, 28), (22, 28, 48), (50, 60, 94), (30, 38, 64)
AMBAR, MENTA, CORAL, TEXTO, TENUE = (255, 176, 32), (64, 214, 178), (255, 107, 107), (234, 238, 250), (136, 146, 178)
CELDA = 56
TX0, TY0 = 90, (H - LADO * CELDA) // 2
PX0 = TX0 + LADO * CELDA + 90
TAG = {"chispa_tau": ("CHISPA ≥ τ", MENTA), "chispa_bajo_tau": ("CHISPA bajo τ", AMBAR),
       "escudo": ("ESCUDO · juega el profesor", CORAL)}


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


def plan(n_pasos: int, fps: int = FPS) -> Tuple[int, int, int]:
    """(pasos a mostrar, fotogramas por paso, fotogramas del remate final). Duración total entre 20 y 40 s: si la partida
    es larga se acelera hasta 3 fotogramas por paso y, si aun así no cabe, se muestran solo los últimos pasos."""
    remate_min = round(REMATE_S * fps)
    m = max(1, min(n_pasos, (round(MAX_S * fps) - remate_min) // FOTOS_MIN))
    f = max(FOTOS_MIN, round(SEG_IDEAL * fps))
    f = max(FOTOS_MIN, min(f, (round(MAX_S * fps) - remate_min) // m))
    remate = max(remate_min, round(MIN_S * fps) - m * f)
    return m, f, remate


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


def _rect(d, f, c, color, margen=2, radio=9):
    x, y = TX0 + c * CELDA, TY0 + f * CELDA
    d.rounded_rectangle([x + margen, y + margen, x + CELDA - margen - 1, y + CELDA - margen - 1], radius=radio, fill=color)


def _chispa(d, f, c):
    cx, cy = TX0 + c * CELDA + CELDA // 2, TY0 + f * CELDA + CELDA // 2
    d.polygon([(cx, cy - 22), (cx + 7, cy - 7), (cx + 22, cy), (cx + 7, cy + 7), (cx, cy + 22),
               (cx - 7, cy + 7), (cx - 22, cy), (cx - 7, cy - 7)], fill=AMBAR)


def _mezcla(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def dibujar_fotograma(paso: dict, cuerpo, comida, direccion: int, despues: bool, resultado: str = ""):
    """Imagen PIL 1920×1080 de un paso. `cuerpo`/`comida`/`direccion`: lo que se dibuja (antes o después de mover);
    `resultado`: texto del desenlace del paso («¡come!», «choque: muro»…), solo después de mover."""
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (W, H), FONDO)
    d = ImageDraw.Draw(im)
    d.text((TX0, 24), "CHISPA: SERPIENTE", font=_fuente(40, True), fill=AMBAR)
    d.rounded_rectangle([TX0 - 10, TY0 - 10, TX0 + LADO * CELDA + 10, TY0 + LADO * CELDA + 10], radius=14,
                        fill=PANEL, outline=BORDE, width=3)
    for i in range(LADO + 1):
        d.line([(TX0 + i * CELDA, TY0), (TX0 + i * CELDA, TY0 + LADO * CELDA)], fill=REJILLA, width=1)
        d.line([(TX0, TY0 + i * CELDA), (TX0 + LADO * CELDA, TY0 + i * CELDA)], fill=REJILLA, width=1)
    n = len(cuerpo)
    for i in range(n - 1, -1, -1):
        f, c = cuerpo[i]
        _rect(d, f, c, CORAL if (i == 0 and resultado.startswith("choque")) else
              (TEXTO if i == 0 else _mezcla(MENTA, (20, 90, 90), i / max(1, n))))
    if comida:
        _chispa(d, comida[0], comida[1])
    # panel de datos
    x, y = PX0, TY0
    d.text((x, y), f"Paso {paso['paso']}", font=_fuente(56, True), fill=TEXTO)
    d.text((x + 380, y + 12), f"de {MAX_PASOS}", font=_fuente(34), fill=TENUE)
    d.text((x, y + 80), f"Longitud {len(cuerpo)}   ·   Comidas {paso['comidas'] - (0 if despues else int(paso['comio']))}",
           font=_fuente(34), fill=TEXTO)
    d.text((x, y + 130), posicion_comida(cuerpo, direccion, comida) if comida else "No queda comida.", font=_fuente(28), fill=TENUE)
    # decisión de Chispa
    tag = TAG.get(paso.get("decidio"))
    etiqueta, color = tag if tag else (("ÚNICA SALIDA", TENUE) if paso.get("forzada") else ("PROFESOR / AZAR", TENUE))
    d.rounded_rectangle([x, y + 200, x + 740, y + 280], radius=14, fill=PANEL, outline=color, width=4)
    d.text((x + 24, y + 214), etiqueta, font=_fuente(40, True), fill=color)
    probs = paso.get("probs") or {}
    for k, g in enumerate(GIROS):
        by = y + 320 + k * 90
        elegido = g == paso["giro"]
        d.text((x, by), g, font=_fuente(34, elegido), fill=TEXTO if elegido else TENUE)
        d.rounded_rectangle([x + 220, by + 4, x + 220 + 400, by + 40], radius=8, fill=PANEL, outline=BORDE, width=2)
        p = probs.get(g)
        if isinstance(p, (int, float)) and p > 0:
            d.rounded_rectangle([x + 220, by + 4, x + 220 + max(8, int(400 * min(1.0, p))), by + 40], radius=8,
                                fill=color if elegido else BORDE)
            d.text((x + 640, by), f"{100 * p:.0f} %", font=_fuente(30), fill=TEXTO if elegido else TENUE)
        if elegido:
            d.text((x - 36, by), "▶", font=_fuente(34), fill=color)
    conf = paso.get("confianza")
    d.text((x, y + 610), f"Jugada: {paso['giro']}" + (f"   ·   confianza {100 * conf:.0f} %" if conf is not None else ""),
           font=_fuente(36, True), fill=color)
    if paso.get("escudo"):
        d.text((x, y + 660), f"escudo: {paso.get('motivo_escudo') or 'sin opinión'}", font=_fuente(28), fill=TENUE)
    if resultado:
        d.text((x, y + 730), resultado, font=_fuente(48, True), fill=CORAL if resultado.startswith("choque") else AMBAR)
    return im


def _resultado(paso: dict) -> str:
    if paso["choque"]:
        return "choque: " + ("muro" if paso["choque"] == "muro" else "su cuerpo")
    if paso["comio"]:
        return "¡come!"
    return "tope de 500 pasos" if paso["terminada"] else ""


def fotogramas(pasos: List[dict], fps: int = FPS) -> Iterator:
    """Fotogramas de la partida: de cada paso, la mitad antes de mover (con la decisión) y la mitad después."""
    m, f, remate = plan(len(pasos), fps)
    pasos = pasos[len(pasos) - m:]
    ultimo = None
    for i, t in enumerate(pasos):
        cuerpo = [tuple(c) for c in t["cuerpo"]]
        comida = tuple(t["comida"]) if t["comida"] else None
        nd = nueva_dir(t["dir"], t["giro"])
        nuevo, come, choque = mover(cuerpo, nd, comida)
        sig = pasos[i + 1] if i + 1 < len(pasos) else None
        comida2 = (tuple(sig["comida"]) if sig and sig["comida"] else None) if come else comida
        antes = dibujar_fotograma(t, cuerpo, comida, t["dir"], False)
        despues = dibujar_fotograma(t, nuevo, comida2, nd if not choque else t["dir"], True, _resultado(t))
        k = max(1, f // 2)
        for j in range(f):
            yield antes if j < k else despues
        ultimo = despues
    for _ in range(remate):
        yield ultimo


def crear_mp4(ims, salida: str, fps: int = FPS) -> int:
    """Manda los fotogramas (rgb24) a ffmpeg. Devuelve cuántos escribió."""
    ff = ruta_ffmpeg()
    if not ff:
        raise RuntimeError("no hay ffmpeg: ni en el PATH ni imageio-ffmpeg")
    cmd = [ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-movflags", "+faststart", salida]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n = 0
    try:
        prev, crudo = None, b""
        for im in ims:
            if im is not prev:  # los fotogramas repetidos son el mismo objeto: se convierte una vez
                prev, crudo = im, im.tobytes()
            p.stdin.write(crudo)
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
    a = ap.parse_args(argv)
    if not hay_pillow():
        print("renderizar: falta Pillow (pip install -r requirements-render.txt); se salta el vídeo", file=sys.stderr)
        return 3
    if not ruta_ffmpeg():
        print("renderizar: falta ffmpeg (ni en el PATH ni imageio-ffmpeg); se salta el vídeo", file=sys.stderr)
        return 3
    _, pasos = leer(a.traza)
    if not pasos:
        print("renderizar: la traza no tiene pasos", file=sys.stderr)
        return 1
    n = crear_mp4(fotogramas(pasos), a.salida)
    print(f"renderizar: {n} fotogramas ({n / FPS:.1f} s a {FPS} fps, {W}x{H}) en {a.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
