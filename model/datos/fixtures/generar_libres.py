"""Fixtures inventados de las fuentes de libre uso (T1.1c): `python -m model.datos.fixtures.generar_libres`.

Nada aquí viene de datos reales: los nombres, teléfonos, correos y direcciones de las PQRS son inventados.
"""
import csv
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

AQUI = Path(__file__).parent


def tarjeta(nombre, licencia, cuerpo="", sub=""):
    d = AQUI / nombre / sub if sub else AQUI / nombre
    d.mkdir(parents=True, exist_ok=True)
    (d / "README.md").write_text("---\nlicense: %s\n---\n# Tarjeta inventada del fixture %s\n%s\n" % (licencia, nombre, cuerpo), encoding="utf-8")
    return d


def csv_(path, cab, filas):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cab)
        w.writerows(filas)


def parquet(path, filas):
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(filas), path)


def odio_alia():
    d = tarjeta("odio_alia", "cc-by-4.0")
    filas = []
    for i in range(1, 41):
        odio = i % 4 == 0
        texto = ("Fuera de aquí esos %d, no valen nada." if odio else "Qué buen video número %d, gracias por compartir.") % i
        filas.append({"id": "record_%d" % i, "source": "youtube" if i % 2 else "tiktok", "text": texto,
                      "foe_class": 1 if odio else 0, "foe_score": 0.9 if odio else 0.05})
    filas.append(dict(filas[0], id="record_41"))  # texto repetido
    with open(d / "ALIA-es-discriminative-hate-speech.jsonl", "w", encoding="utf-8") as fh:
        for f in filas:
            fh.write(json.dumps(f, ensure_ascii=False) + "\n")
    # muestra humana: record_4 (LLM=1, humanos 0,0,1 → 0), record_8 (1; 1,1,0 → 1), record_1 (0; 0,0,0 → 0)
    hum = [("record_4", 1, 0, 0, 1), ("record_8", 1, 1, 1, 0), ("record_1", 0, 0, 0, 0)]
    with open(d / "ALIA-es-discriminative-hate-speech-human-sample.jsonl", "w", encoding="utf-8") as fh:
        for k, (rid, fc, a1, a2, a3) in enumerate(hum, 1):
            fh.write(json.dumps({"id_sample": "sample_%d" % k, "id": rid, "text": "x", "foe_class": fc, "annotator_1": a1,
                                 "annotator_2": a2, "annotator_3": a3}) + "\n")


def _tox(nombre, fichero, extra_cab, extra):
    d = tarjeta(nombre, "cc-by-4.0")
    cab = ["id_obs", "coder_1", "coder_2", "consensus", "text"] + extra_cab
    filas = []
    for i in range(1, 31):
        c1 = c2 = "1" if i % 3 == 0 else "0"
        cons = "NA" if (c1 == "1" and i % 6 == 0) else "1"
        filas.append([str(100 + i), c1, c2, cons, "Tuit inventado número %d" % i] + extra(i))
    filas.append(["200", "1", "0", "0", "Tuit inventado con desacuerdo"] + extra(1))
    filas.append(["201", "0", "1", "0", "Otro tuit con desacuerdo"] + extra(2))
    csv_(d / fichero, cab, filas)


def toxicidad():
    _tox("toxicidad_protestas", "goldstd_protests.csv", ["country"], lambda i: ["Argentina" if i % 2 else "Chile"])
    _tox("toxicidad_constitucion", "goldstd_Convention.csv", [], lambda i: [])


def goemociones():
    d = tarjeta("goemociones", "apache-2.0")
    def filas(pref, n, base):
        out = []
        for i in range(n):
            ls = [(base + i) % 27] if i % 5 else [(base + i) % 27, 27]
            out.append({"text": "english %s %d" % (pref, i), "labels": ls, "id": "%s%d" % (pref, i), "text_es": "Texto inventado %s número %d" % (pref, i)})
        return out
    for nom, n in (("train", 16), ("validation", 3), ("test", 3)):
        parquet(d / "data" / ("%s-00000-of-00001.parquet" % nom), filas(nom[:2], n, len(nom)))


def spam_tanaos():
    d = tarjeta("spam_tanaos", "mit")
    filas = []
    for i in range(30):
        spam = i % 2 == 0
        filas.append(["¡Gana dinero rápido con esta oferta %d! Haz clic ya." % i if spam else "Nos vemos mañana en la reunión %d." % i, "1" if spam else "0"])
    filas.append(list(filas[0]))
    csv_(d / "data" / "data.csv", ["text", "labels"], filas)


def soporte_ti():
    d = tarjeta("soporte_ti", "cc-by-4.0")
    textos = [("Cannot log in to Active Directory account, please reset password", 0), ("Impressora nao funciona, preciso de ajuda", 1),
              ("Laptop end of life replacement request", 2), ("Zugriff auf Netzlaufwerk bitte freigeben", 3),
              ("Outlook y Teams no abren en el portátil", 4), ("Install the new software package please", 5), ("General question about the VPN", 6)]
    train, test = [], []
    for i in range(24):
        t, l = textos[i % 7]
        (train if i < 17 else test).append({"text": "%s [TICKET ID] %d" % (t, i), "label": l})
    parquet(d / "data" / "train-00000-of-00001.parquet", train)
    parquet(d / "data" / "test-00000-of-00001.parquet", test)


def ciberacoso():
    for sub, cab, n0 in (("d1", ["author", "categoria", "ciberacoso", "texto", ""], 0), ("d2", ["author", "categoria", "ciberacoso", "texto", "Unnamed: 4"], 100)):
        d = tarjeta("ciberacoso", "mit", sub=sub)
        filas = []
        for i in range(20):
            acoso = i % 2 == 0
            filas.append(["usuario_%d" % i, "2" if acoso else "0", "1" if acoso else "0",
                          ("@vecino%d eres un inútil, ojalá te vaya mal %d" if acoso else "Parce, se me olvidó ver el partido %d @amigo%d") % ((i + n0, i) if not acoso else (i, i + n0)), ""])
        filas.append(["x", "", "", "", ""])  # fila vacía
        if sub == "d2":
            filas.append(["x", "1.0", "1.0", "@otro eres un inútil, ojalá te vaya mal 0", ""])  # repetido de d1 salvo la mención
        csv_(d / "DATASET.csv", cab, filas)


def clima():
    d = tarjeta("clima", "cc-by-4.0", cuerpo="## License\ncc-by-nc-sa-4.0 Due to inheritance of the data used in the dataset.")
    for nom, n in (("train", 12), ("test", 6)):
        csv_(d / "csv" / ("final_esp_%s.csv" % nom), ["question", "answer", "dominio"],
             [["El cambio climático afecta a los glaciares %d" % i if i % 2 else "El equipo ganó el partido %d" % i, str(i % 2), "x"] for i in range(n)])


def _meta(lic_id, enlace):
    return {"id": "fix", "name": "fixture inventado", "licenseId": lic_id,
            "license": {"name": "inventada", "termsLink": "http://creativecommons.org/licenses/%s/legalcode" % enlace}}


def _pqrs(nombre, id_fuente, lic_id, enlace, cab, filas):
    d = AQUI / nombre
    d.mkdir(parents=True, exist_ok=True)
    csv_(d / (id_fuente + ".csv"), cab, filas)
    (d / (id_fuente + ".meta.json")).write_text(json.dumps(_meta(lic_id, enlace)), encoding="utf-8")


NOMBRES_FIX = ["Pedro Gómez", "María Rodríguez", "Luis Herrera", "Ana Torres"]


def texto_pqrs(i, tipo):
    n = NOMBRES_FIX[i % 4]
    base = {"peticion": "Solicito copia del contrato número %d",
            "queja": "Presento queja por el mal trato recibido en la ventanilla %d",
            "reclamo": "Reclamo por el cobro duplicado en la factura %d",
            "sugerencia": "Sugiero abrir más puntos de atención en la sede %d",
            "denuncia": "Denuncio una posible irregularidad en el proceso %d",
            "felicitacion": "Felicito al equipo por la atención recibida en el caso %d"}[tipo] % i
    return "%s. Soy %s, cédula 1032456789, cel 3001234567, correo pedro%d@ejemplo.com, vivo en la calle 45 # 12-34." % (base, n, i)


def pqrs():
    tipos = ["peticion"] * 8 + ["queja"] * 4 + ["reclamo"] * 4 + ["sugerencia"] * 4 + ["denuncia"] * 4 + ["felicitacion"] * 4
    # gb9w: «Tipo de solicitud»
    esp = {"peticion": "Petición", "queja": "Queja", "reclamo": "Reclamo", "sugerencia": "Sugerencia", "denuncia": "Denuncia", "felicitacion": "Felicitación"}
    filas = [[str(i), "2020-01-01", "Solicitud de información" if (t == "peticion" and i % 2) else esp[t], "SI", texto_pqrs(i, t), "Cerrada", "NO", "Chat"]
             for i, t in enumerate(tipos) if t != "felicitacion"]
    filas.append(["900", "2020-01-01", "Agenda tu cita", "NO", "Quiero una cita el martes", "Abierta", "NO", "Chat"])
    _pqrs("pqrs_gb9w", "gb9w-jt96", "CC_40_BY_SA", "by-sa/4.0",
          ["No de solicitud", "Fecha de creación", "Tipo de solicitud", "Es anonima", "Descripción de la solicitud", "Estado", "Fue delegada", "Origen"], filas)
    # e86p: «CLASIFICACIÓN»
    cl = {"peticion": "DERECHO DE PETICION", "queja": "QUEJA", "sugerencia": "SUGERENCIA", "reclamo": "QUEJA - RECLAMO", "denuncia": "ENTES DE CONTROL (10)", "felicitacion": ""}
    filas = [["2020-01-01", cl[t], texto_pqrs(i, t).upper() if i % 3 == 0 else texto_pqrs(i, t), "2020-02-01", "CERRADO", "x"] for i, t in enumerate(tipos)]
    _pqrs("pqrs_e86p", "e86p-frfd", "CC_40_BY_SA", "by-sa/4.0", ["FECHA DE INGRESO", "CLASIFICACIÓN", "ASUNTO", "FECHA DE RESPUESTA", "ESTADO ACTUAL", "Radica Respuesta"], filas)
    # xtj2: una columna SI/NO por tipo
    cols = ["Peticion", "Queja", "Reclamo", "Solicitud", "Sugerencia", "Denuncia", "Felicitación"]
    col_de = {"peticion": "Peticion", "queja": "Queja", "reclamo": "Reclamo", "sugerencia": "Sugerencia", "denuncia": "Denuncia", "felicitacion": "Felicitación"}
    filas = []
    for i, t in enumerate(tipos):
        marcas = ["SI" if col_de[t] == c else "NO" for c in cols]
        nombre = NOMBRES_FIX[i % 4]
        filas.append([str(i), "2020-01-01", str(i)] + marcas + [nombre, "Pide copia del documento %d. Atiende %s." % (i, nombre)])
    filas.append(["98", "2020-01-01", "98"] + ["NO"] * 7 + ["Sin Marca", "Fila sin ningún tipo marcado"])
    filas.append(["99", "2020-01-01", "99", "SI", "SI"] + ["NO"] * 5 + ["Doble Marca", "Fila con dos tipos marcados"])
    _pqrs("pqrs_xtj2", "xtj2-ipwy", "CC_40_BY_SA", "by-sa/4.0",
          ["CONSEC", "FECHA RADICACIÓN", "NUMERO RADICADO"] + cols + ["NOMBRE DEL PETICIONARIO", "RESUMEN INFORMACIÓN SOLICITADA"], filas)
    # m3mt: «Asunto» → «Dependencia»
    deps = ["Dirección de Sanidad", "Atención al Usuario", "Gestión Documental", "Oficina de Tecnología"]
    asuntos = ["Cita médica especializada", "Entrega de medicamentos", "Certificado de afiliación", "Falla del sistema de citas", "Autorización de cirugía"]
    filas = []
    for i in range(60):
        filas.append([asuntos[i % 5], "2020-01-%02d" % (i % 28 + 1), deps[i % 4] if i < 56 else "Dependencia Rara %d" % i, "Página web"])
    filas.append(["Asunto sin dependencia", "2020-02-01", "", "Página web"])
    _pqrs("pqrs_enrutamiento", "m3mt-c275", "CC_40_BY", "by/4.0", ["Asunto", "Fecha", "Dependencia", "Recepcion"], filas)


if __name__ == "__main__":
    for f in (odio_alia, toxicidad, goemociones, spam_tanaos, soporte_ti, ciberacoso, clima, pqrs):
        f()
