#!/usr/bin/env python3
"""Reparto de longitudes y dominios de textos-es-co.txt (solo stdlib).

Uso: python3 estadisticas_textos.py [fichero]   (por defecto, textos-es-co.txt junto al script)
El dominio se estima por palabras clave (el fichero no lo trae); es aproximado, y «otro» es lo que no encaja.
Aplica las mismas reglas que cmd/carga: se ignoran líneas vacías y las que empiezan por '#'.
"""
import os, re, statistics, sys, unicodedata
from collections import Counter

DOMINIOS = {
    "salud": "eps ips cita medic formula urgencias especialista cirugia resonancia ecografia historia clinica incapacidad oxigeno ambulancia afiliacion farmacia laboratorio paciente terapia",
    "banca": "tarjeta credito debito cuenta de ahorros banco transferencia clave extracto cdt cajero cupo centrales de riesgo otp cuota de manejo deuda reestructurar certificado bancario consignado",
    "telecom": "internet modem fibra senal linea postpago plan de datos datos decodificador operador sim celular recarga megas wifi television portar tecnico",
    "ecommerce": "pedido guia envio transportadora reembolso devolver devolucion cupon paquete talla despacharon pse comprobante vendedor producto garantia entrega",
    "ferreteria": "cemento varilla pintura taladro pulidora tuberia baldosa ceramica grifería griferia zinc tejas arena maestro de obra obra impermeabilizante cerradura ferreteria galon",
    "servicios": "recibo luz energia agua gas medidor alumbrado fuga alcantarillado basura estrato reconexion tension poste acueducto",
    "soporte": "aplicacion app contrasena sesion error actualizacion sincroniza impresora usuario pantalla programa exportar calendario instalar cuenta verificacion",
    "ventas": "cotizacion cotizar licencias distribuidor demostracion descuento por volumen al por mayor suscripcion financiacion plan empresarial pyme catalogo asesor propuesta precio",
}

def norm(s):
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")

LEX = {d: [norm(w) for w in re.findall(r"(?:de |del |por |al |en )?\w+(?: de \w+| por \w+)?", v)] for d, v in DOMINIOS.items()}
LEX = {d: sorted({w for w in ws if len(w) > 2}) for d, ws in LEX.items()}

def dominio(t):
    n = " " + norm(t) + " "
    pt = {d: sum(n.count(" " + w) for w in ws) for d, ws in LEX.items()}
    d, p = max(pt.items(), key=lambda kv: kv[1])
    return d if p > 0 else "otro"

TRAMOS = [(3, 7), (8, 22), (23, 45), (46, 80), (81, 120)]

def main():
    ruta = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "textos-es-co.txt")
    with open(ruta, encoding="utf-8") as f:
        crudas = f.read().split("\n")
    ls = [l.strip() for l in crudas]
    msgs = [l for l in ls if l and not l.startswith("#")]
    pal = [len(m.split()) for m in msgs]
    print(f"fichero: {ruta}")
    tabs = sum("\t" in l for l in crudas)
    print(f"mensajes: {len(msgs)}  únicos: {len(set(msgs))}  con tabulador: {tabs}")
    print(f"palabras: min {min(pal)}  p50 {int(statistics.median(pal))}  media {statistics.mean(pal):.1f}  p90 {sorted(pal)[int(.9*(len(pal)-1))]}  max {max(pal)}")
    print(f"bytes UTF-8 por mensaje: p50 {int(statistics.median(len(m.encode()) for m in msgs))}  max {max(len(m.encode()) for m in msgs)}")
    print("\nlongitud (palabras)")
    for a, b in TRAMOS:
        n = sum(a <= p <= b for p in pal)
        print(f"  {a:>3}-{b:<3} {n:>5} {100*n/len(msgs):5.1f}%  {'#'*round(50*n/len(msgs))}")
    fuera = sum(not (3 <= p <= 120) for p in pal)
    if fuera:
        print(f"  fuera de 3-120: {fuera}")
    dom = Counter(dominio(m) for m in msgs)
    print("\ndominio (estimado por palabras clave)")
    for d, n in dom.most_common():
        print(f"  {d:<11}{n:>5} {100*n/len(msgs):5.1f}%")
    print("\nrasgos")
    emo = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
    print(f"  con emoji: {sum(bool(emo.search(m)) for m in msgs)}")
    marc = re.compile(r"\[[A-Z_]+\]")
    print(f"  con marcador [..]: {sum(bool(marc.search(m)) for m in msgs)}")
    print(f"  sin tildes (largos, ortografía descuidada, aprox.): {sum(norm(m) == m.lower() and len(m.split()) > 8 for m in msgs)}")
    print(f"  TODO EN MAYÚSCULAS: {sum(m.isupper() for m in msgs)}")
    print("\nlongitud media (palabras) por dominio")
    por = {}
    for m, p in zip(msgs, pal):
        por.setdefault(dominio(m), []).append(p)
    for d, v in sorted(por.items()):
        print(f"  {d:<11}{statistics.mean(v):6.1f}")

main()
