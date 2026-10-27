"""Construye model/sondeo/*.jsonl. Uso: python construir.py <dir_salida> <dir_arena_data>
dir_arena_data = salida de dataset.Generate(seed 1) (spam/, intencion/, ...). Determinista (semilla 7)."""
import csv, glob, gzip, json, os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import herramientas_datos as H

OUT, ARENA = sys.argv[1], sys.argv[2]
HF = os.path.expanduser("~/hf/hub")
rng = random.Random(7)
K = 32

def write(name, rows):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    print(name, len(rows))

def rows_for(tarea, items, desc, fuente, lic, split):
    opts = list(desc)
    return [dict(texto=t, opciones=opts, etiqueta=y, tarea=tarea, fuente=fuente, licencia=lic,
                 descripciones=desc, split=split) for t, y in items]

def pick_train(items, tarea, desc, fuente, lic, test_texts):
    """K por clase, sin solaparse con el test; idx_clase<8 forma el subconjunto k=8."""
    by = {}
    for t, y in items:
        if t not in test_texts:
            by.setdefault(y, []).append((t, y))
    out = []
    for y in desc:
        pool = by.get(y, [])
        rng.shuffle(pool)
        sel = pool[:K]
        for i, r in enumerate(rows_for(tarea, sel, desc, fuente, lic, "train")):
            r["idx_clase"] = i
            out.append(r)
    return out

def dedup(items):
    seen, out = set(), []
    for t, y in items:
        if t not in seen:
            seen.add(t); out.append((t, y))
    return out

# --- intención (MASSIVE es) ---
INT = {
 "calendar_set": "agendar un evento en el calendario", "play_music": "poner música",
 "weather_query": "preguntar por el clima", "news_query": "preguntar por las noticias",
 "email_query": "consultar los correos", "email_sendemail": "enviar un correo",
 "datetime_query": "preguntar la fecha o la hora", "cooking_recipe": "pedir una receta de cocina",
 "alarm_set": "poner una alarma", "lists_createoradd": "añadir algo a una lista",
 "qa_currency": "preguntar por el cambio de moneda", "iot_hue_lightoff": "apagar las luces",
 "transport_query": "preguntar por transporte o rutas",
}
b = glob.glob(HF + "/datasets--mteb--amazon_massive_intent/snapshots/*/")[0]
def massive(split):
    return [(r["text"], r["label_text"]) for r in map(json.loads, gzip.open(b + split + "/es.json.gz", "rt", encoding="utf-8")) if r["label_text"] in INT]
te = dedup(massive("test")); by = {}
for t, y in te: by.setdefault(y, []).append((t, y))
test = []
for y in INT:
    l = by[y]; rng.shuffle(l); test += l[:30]
LIC_M = "apache-2.0 (mteb/amazon_massive_intent; origen Amazon MASSIVE, CC-BY-4.0)"
tt = {t for t, _ in test}
write("intencion.jsonl", rows_for("intencion", test, INT, "mteb/amazon_massive_intent es test", LIC_M, "test"))
write("train_intencion.jsonl", pick_train(dedup(massive("train")), "intencion", INT, "mteb/amazon_massive_intent es train", LIC_M, tt))

# --- toxicidad (hatecheck es), partido por plantilla ---
TOX = {"toxico": "mensaje de odio o tóxico contra una persona o grupo", "respetuoso": "mensaje respetuoso o no ofensivo"}
rows = list(csv.DictReader(open(glob.glob(HF + "/datasets--Paul--hatecheck-spanish/snapshots/*/test.csv", )[0], encoding="utf-8")))
rows = [r for r in rows if r["disagreement_in_case"] != "True"]
templ = sorted({r["templ_id"] for r in rows}); rng.shuffle(templ)
tset = set(templ[: len(templ) // 4])
m = {"hateful": "toxico", "non-hateful": "respetuoso"}
tst = dedup([(r["test_case"], m[r["label_gold"]]) for r in rows if r["templ_id"] in tset])
trn = dedup([(r["test_case"], m[r["label_gold"]]) for r in rows if r["templ_id"] not in tset])
bc = {"toxico": [], "respetuoso": []}
for t, y in tst: bc[y].append((t, y))
for l in bc.values(): rng.shuffle(l)
n = min(150, len(bc["toxico"]), len(bc["respetuoso"]))
test = bc["toxico"][:n] + bc["respetuoso"][:n]
tt = {t for t, _ in test}
LIC_T = "cc-by-4.0 (Paul/hatecheck-spanish)"
write("toxicidad.jsonl", rows_for("toxicidad", test, TOX, "Paul/hatecheck-spanish test.csv", LIC_T, "test"))
write("train_toxicidad.jsonl", pick_train(trn, "toxicidad", TOX, "Paul/hatecheck-spanish test.csv (plantillas distintas al test)", LIC_T, tt))

# --- WhatsApp de comercio (Arena, dimensión intencion) ---
WA = {"compra": "quiere comprar o preguntar por un producto", "soporte": "pide ayuda o soporte con algo que ya tiene",
      "queja": "presenta una queja o reclamo", "saludo": "solo saluda o conversa"}
def arena(sp): return [(r["text"], r["label"]) for r in map(json.loads, open(f"{ARENA}/intencion/{sp}.jsonl", encoding="utf-8"))]
test = dedup(arena("test")); tt = {t for t, _ in test}
LIC_W = "propia (Chispa Arena, plantillas sintéticas internal/dataset)"
write("whatsapp_comercio.jsonl", rows_for("whatsapp_comercio", test, WA, "arena intencion test (semilla 1; plantillas separadas del train)", LIC_W, "test"))
write("train_whatsapp_comercio.jsonl", pick_train(dedup(arena("train")), "whatsapp_comercio", WA, "arena intencion train", LIC_W, tt))

# --- orquestar herramientas ---
D = H.DESCRIPCIONES
test = [(t, y) for y, l in H.TEST.items() for t in l]; rng.shuffle(test)
PRE = ["oiga, ", "buenas, ", "parce, ", "hola, ", "porfa ", "disculpe, ", "mijo, ", "una pregunta: ", "ayúdeme: ", "necesito que "]
SUF = [", porfa", ", gracias", " por favor", " ahorita", ", si es posible", " rápido", " 🙏", " jaja"]
def wrap(t):
    s = t[0].lower() + t[1:] if rng.random() < .6 else t
    s = rng.choice(PRE) + s
    s = s.rstrip("?.!") + rng.choice(SUF)
    return s
trn = []
for y, seeds in H.TRAIN.items():
    items = list(seeds); i = 0
    while len(items) < K:
        w = wrap(seeds[i % len(seeds)]); i += 1
        if w not in items: items.append(w)
    for k, t in enumerate(items):
        r = rows_for("herramientas", [(t, y)], D, "sintetico-worker" + ("" if k < len(seeds) else " (semilla + envoltura de registro)"), "propia (sintetico-worker)", "train")[0]
        r["idx_clase"] = k
        trn.append(r)
# k=8 con solo semillas a mano: idx_clase<len(seeds) y el orden ya lo garantiza
write("herramientas.jsonl", rows_for("herramientas", test, D, "sintetico-worker", "propia (sintetico-worker)", "test"))
write("train_herramientas.jsonl", trn)
