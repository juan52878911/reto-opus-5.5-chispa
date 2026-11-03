"""Vídeo 1080p a 30 fps de una partida grabada con `ale --video`: el emulador a la izquierda (fotogramas reales, uno de cada 2)
y a la derecha la decisión de cada pieza con la probabilidad de cada opción. Pillow, numpy y ffmpeg solo se usan aquí.

    python -m tetris_ale renderizar PREFIJO salida.mp4 [--segundos 60] [--titulo …]

PREFIJO es la ruta sin extensión de `video-<agente>.npz` y `video-<agente>.jsonl`."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from typing import List, Optional

W, H, FPS = 1920, 1080, 30
# Identidad visual de Chispa (la de Caída): fondo noche, ámbar «chispa», menta para lo que elige Chispa.
FONDO, PANEL, BORDE = (14, 18, 32), (24, 30, 52), (52, 62, 98)
AMBAR, MENTA, CORAL, AZUL, TEXTO, TENUE = (255, 176, 32), (64, 214, 178), (255, 107, 107), (110, 142, 255), (234, 238, 250), (136, 146, 178)
# Solo el campo de juego del fotograma real (x 20–66, y 26–206), con escala entera para que se vea nítido y el píxel del Atari
# al doble de ancho que de alto (como en la tele): 46 × 180 → 552 × 900.
RECORTE = (20, 26, 66, 206)
EX_ESC, EY_ESC = 12, 5
EMU_W, EMU_H = (RECORTE[2] - RECORTE[0]) * EX_ESC, (RECORTE[3] - RECORTE[1]) * EY_ESC
EX0, EY0 = 150, (H - EMU_H) // 2
PX0 = EX0 + EMU_W + 150


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


def leer_traza(ruta: str):
    turnos, fin = [], {}
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            x = json.loads(linea)
            if "fin" in x:
                fin = x["fin"]
            else:
                turnos.append(x)
    return turnos, fin


def barras(t: dict) -> List[dict]:
    """Opciones en orden de id con su probabilidad (0 si el servidor no la dio) y si es la elegida."""
    probs = t.get("probs") or {}
    out = []
    for o in sorted(t.get("opciones") or [], key=lambda o: int(o["id"])):
        out.append({"id": o["id"], "prob": float(probs.get(o["id"], 0.0)), "descripcion": o["descripcion"],
                    "elegida": o["id"] == t.get("id_elegida"), "maestro": o.get("puesto") == 1})
    return out


def partir(texto: str, ancho: int) -> List[str]:
    """Corta por comas en líneas de como mucho `ancho` caracteres."""
    lineas, actual = [], ""
    for trozo in texto.split(", "):
        nuevo = trozo if not actual else actual + ", " + trozo
        if len(nuevo) > ancho and actual:
            lineas.append(actual + ",")
            actual = trozo
        else:
            actual = nuevo
    return lineas + [actual]


def _barra(d, x, y, w, h, p, color):
    d.rounded_rectangle([x, y, x + w, y + h], radius=5, fill=BORDE)
    if p > 0:
        d.rounded_rectangle([x, y, x + max(8, int(w * min(1.0, p))), y + h], radius=5, fill=color)


def dibujar(foto, t: Optional[dict], n_pieza: int, lineas: int, titulo: str, stats: dict):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (W, H), FONDO)
    emu = Image.fromarray(foto).crop(RECORTE).resize((EMU_W, EMU_H), Image.NEAREST)
    im.paste(emu, (EX0, EY0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([EX0 - 6, EY0 - 6, EX0 + emu.width + 6, EY0 + emu.height + 6], radius=8, outline=BORDE, width=4)
    x0, y = PX0, 64
    d.rounded_rectangle([x0 - 24, 36, W - 44, H - 36], radius=18, fill=PANEL, outline=BORDE, width=3)
    d.text((x0, y), titulo, font=_fuente(30, True), fill=AMBAR)
    y += 52
    d.text((x0, y), "ALE/Tetris-v5 · emulador Atari real · una pregunta «choice» por pieza", font=_fuente(20), fill=TENUE)
    y += 48
    d.text((x0, y), f"Pieza {n_pieza}", font=_fuente(28, True), fill=TEXTO)
    d.text((x0 + 300, y), f"Líneas {lineas}", font=_fuente(28, True), fill=AMBAR)
    y += 56
    if t is None or not t.get("opciones"):
        d.text((x0, y), "Apertura al azar (igual para todos los agentes)" if t is not None else "", font=_fuente(22), fill=TENUE)
    else:
        d.text((x0, y), f"Pieza {t['pieza']}: ¿dónde la coloco?  Confianza de Chispa por opción", font=_fuente(22, True), fill=TENUE)
        y += 42
        for b in barras(t):
            color = MENTA if b["elegida"] else AZUL
            d.text((x0, y), b["id"], font=_fuente(24, True), fill=AMBAR if b["elegida"] else TEXTO)
            _barra(d, x0 + 34, y + 5, 260, 22, b["prob"], color)
            d.text((x0 + 306, y + 2), f"{b['prob'] * 100:3.0f} %", font=_fuente(20, True), fill=TEXTO)
            color_t = TEXTO if b["elegida"] else TENUE
            for i, trozo in enumerate(partir(b["descripcion"], 46)[:2]):
                d.text((x0 + 380, y - 4 + i * 22), trozo, font=_fuente(17), fill=color_t)
            if b["maestro"]:
                d.text((x0 + 720, y + 2), "← maestro", font=_fuente(17, True), fill=AMBAR)
            y += 54
        y += 16
        lat = t.get("ms_cliente")
        d.text((x0, y), f"Latencia {lat:.0f} ms" if lat is not None else "Latencia —", font=_fuente(24), fill=TEXTO)
        coincide = "elige la del maestro" if t.get("coincide") else "elige otra que la del maestro"
        d.text((x0 + 300, y), coincide, font=_fuente(24, True), fill=MENTA if t.get("coincide") else CORAL)
        y += 44
        if t.get("decidio") == "chispa_bajo_tau":
            d.rounded_rectangle([x0, y, x0 + 560, y + 40], radius=8, fill=CORAL)
            d.text((x0 + 14, y + 6), "bajo τ: se juega su argmax (modo demo)", font=_fuente(22, True), fill=FONDO)
    pie = (f"Hasta aquí: coincide con el maestro {stats['coinc']}/{stats['dec']} · "
           f"p50 {stats['p50']:.0f} ms" if stats["dec"] else "")
    d.text((x0, H - 96), pie, font=_fuente(22), fill=TENUE)
    return im


def fotogramas(fotos, turnos: List[dict], titulo: str, max_fotos: int):
    import statistics
    k, lineas, coinc, lats = -1, 0, 0, []
    for i in range(min(len(fotos), max_fotos)):
        while k + 1 < len(turnos) and turnos[k + 1]["foto"] <= i:
            k += 1
            if k > 0:
                lineas += turnos[k - 1]["lineas"]
            t = turnos[k]
            if t.get("opciones"):
                coinc += bool(t.get("coincide"))
                if t.get("ms_cliente") is not None:
                    lats.append(t["ms_cliente"])
        t = turnos[k] if k >= 0 else None
        dec = sum(1 for x in turnos[:k + 1] if x.get("opciones"))
        stats = {"dec": dec, "coinc": coinc, "p50": statistics.median(lats) if lats else 0.0}
        yield dibujar(fotos[i], t, k + 1, lineas, titulo, stats)


def crear_mp4(ims, salida: str, fps: int = FPS) -> int:
    ff = ruta_ffmpeg()
    if not ff:
        raise RuntimeError("no hay ffmpeg: ni en el PATH ni imageio-ffmpeg")
    cmd = [ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "14", "-tune", "animation", "-movflags", "+faststart", salida]
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
    ap.add_argument("prefijo")
    ap.add_argument("salida")
    ap.add_argument("--segundos", type=float, default=60.0)
    ap.add_argument("--titulo", default="Chispa juega Tetris (zero-shot)")
    a = ap.parse_args(argv)
    import numpy as np
    fotos = np.load(a.prefijo + ".npz")["fotos"]
    turnos, fin = leer_traza(a.prefijo + ".jsonl")
    n = crear_mp4(fotogramas(fotos, turnos, a.titulo, int(a.segundos * FPS)), a.salida)
    print(f"renderizar: {n} fotogramas ({n / FPS:.1f} s) en {a.salida}; partida: {fin}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
