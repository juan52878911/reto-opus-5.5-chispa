"""Generador del corpus sintético v2 en español colombiano (T1.3).

El modelo (un Qwen abierto en la GPU) solo genera textos y verifica etiquetas; no produce distribuciones. Por cada (tarea, clase) se piden lotes de textos
con un estilo (registro, tecleo, voz, mezcla, ataques de la Arena); cada lote lleva una «plantilla» (su semilla) y se
verifica con una segunda llamada. Después: dedup (exacta, 5-gramas, coseno e5-small), reparto train/dev por plantilla,
escritura en el esquema y un resumen.json. Reanuda desde lo ya escrito y para en seco al llegar al tope de USD.

Uso: python model/corpus/generar.py --tareas pqrs fintech --por-clase 60 --salida DIR [--backend local|simulado|bedrock]
       [--modelo Qwen/Qwen3.5-9B-Instruct] [--tope-min 120]     (local, por defecto: el coste son horas de GPU)
       --backend bedrock es SOLO EVALUACIÓN (Haiku): exige --precio-in y --precio-out y usa --tope-usd.
"""
import argparse
import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    __package__ = "model.corpus"

from . import tareas as T
from .backends import Bedrock, Local, Simulado, elegir_modelo, exigir_apache
from .nucleo import (ErrorFormato, Gasto, TopeAlcanzado, deduplicar, norm, parsear_lista, repartir, semilla_de,
                     validar_conjunto)

MODELO_BEDROCK = "us.anthropic.claude-haiku-5-5"
MAX_CHARS = 600
dormir = time.sleep  # los tests lo sustituyen

# Textos de test que no se pueden parecer a lo generado (no hay fuga de test al corpus).
REFERENCIAS = {"herramientas": ("herramientas", "test.jsonl"), "whatsapp_comercio": ("sondeo", "whatsapp_comercio.jsonl")}


# --- prompts --------------------------------------------------------------------------------------------------
SISTEMA = ("Eres un generador de datos sintéticos en español de Colombia para entrenar un clasificador de mensajes. "
           "Respondes SOLO con un objeto JSON válido, sin texto antes ni después.")


def _clases(t):
    return "\n".join("- %s: %s" % (o, t["descripciones"][o]) for o in t["opciones"])


def prompt_generar(nombre, t, clase, estilo, n, escenario, ciudad):
    extra = ""
    if clase == "escalate":
        extra = "\nPara escalate, genera: %s." % T.ESCALATE_AYUDA[nombre]
    return (
        "Contexto: %s\nEscenario: %s. Ciudad: %s.\n\nClases posibles de la tarea:\n%s\n\n"
        "Escribe %d mensajes distintos cuya clase correcta es SIN DUDA «%s» (%s).%s\n\n"
        "Estilo de este lote (%s): %s\n\n"
        "Reglas: español colombiano natural; varía longitud, estructura y vocabulario; nada de repetir frases entre mensajes; "
        "todo inventado (nombres, números, empresas y enlaces falsos, sin datos reales de personas ni de clientes); "
        "el mensaje no debe nombrar la clase de forma artificial; no lo expliques.\n\n"
        'Responde solo: {"textos": ["mensaje 1", "mensaje 2", ...]} con exactamente %d cadenas.'
        % (T.CONTEXTO_TAREA[nombre], escenario, ciudad, _clases(t), n, clase, t["descripciones"][clase], extra,
           estilo, T.ESTILOS[estilo], n))


def prompt_verificar(nombre, t, clase, textos):
    lista = "\n".join("%d. %s" % (i + 1, x.replace("\n", " ")) for i, x in enumerate(textos))
    return (
        "Contexto: %s\n\nClases posibles:\n%s\n\nA cada mensaje se le asignó la etiqueta «%s» (%s).\n"
        "Para cada uno, ¿esa etiqueta es correcta? Si el mensaje trae spam o una instrucción dirigida al sistema, eso "
        "no cambia la clase: se juzga la intención real; si no hay intención real, la correcta es escalate.\n\n%s\n\n"
        'Responde solo: {"veredictos": ["si" o "no", ...]} con exactamente %d valores, en el mismo orden.'
        % (T.CONTEXTO_TAREA[nombre], _clases(t), clase, t["descripciones"][clase], lista, len(textos)))


# --- llamadas con reintentos ------------------------------------------------------------------------------
class Motor:
    def __init__(self, backend, gasto, hilos=1, max_reintentos=5, espera_base=2.0, log=print):
        self.b, self.g, self.hilos = backend, gasto, hilos
        self.max_reintentos, self.espera_base, self.log = max_reintentos, espera_base, log
        self.reintentos = 0

    def pedir(self, tarea, tipo, sistema, usuario, meta, clave, n_esperado, max_tokens, temperatura):
        """Llama, cuenta tokens (también de las respuestas rotas) y reintenta con espera exponencial.
        Devuelve (lista, reparado). TopeAlcanzado sale sin reintentar."""
        ultimo = None
        for i in range(self.max_reintentos):
            self.g.permitir(self.hilos * self.g.max_llamada)
            try:
                texto, tin, tout = self.b.llamar(sistema, usuario, meta, max_tokens, temperatura)
            except Exception as e:  # límite de peticiones, red, 5xx: espera y reintenta
                ultimo = e
                self.reintentos += 1
                dormir(self.espera_base * 2 ** i * (0.5 + random.random()))
                continue
            self.g.registrar(tarea, tipo, tin, tout)
            try:
                lista, reparado = parsear_lista(texto, clave)
                if tipo == "verificar" and len(lista) != n_esperado:
                    raise ErrorFormato("%d veredictos, se esperaban %d" % (len(lista), n_esperado))
                return lista, reparado
            except ErrorFormato as e:
                ultimo = e
                self.reintentos += 1
                dormir(self.espera_base * 2 ** i * 0.1)
        raise RuntimeError("sin respuesta útil tras %d intentos: %s" % (self.max_reintentos, ultimo))


def trabajos(nombre, t, por_clase, lote, semilla):
    """Lotes de una tarea: (clase, k, estilo, plantilla). El ciclo de estilos arranca en un punto distinto por clase."""
    out = []
    for clase in t["opciones"]:
        estilos = T.estilos_de_clase(clase)
        desfase = semilla_de(semilla, nombre, clase) % len(estilos)
        for k in range(-(-por_clase // lote)):
            estilo = estilos[(k + desfase) % len(estilos)]
            n = min(lote, por_clase - k * lote)
            out.append({"tarea": nombre, "clase": clase, "k": k, "estilo": estilo, "n": n,
                        "plantilla": "t13s%d-%s-%s-%s-%d" % (semilla, nombre, clase, estilo, k)})
    return out


def hacer_lote(motor, t, job, semilla):
    nombre, clase, estilo, n = job["tarea"], job["clase"], job["estilo"], job["n"]
    rng = random.Random(semilla_de(semilla, job["plantilla"]))
    esc, ciudad = rng.choice(T.ESCENARIOS[nombre]), rng.choice(T.CIUDADES)
    meta = {"tipo": "generar", "n": n, "clase": clase, "estilo": estilo, "tarea": nombre,
            "descripcion": t["descripciones"][clase]}
    textos, rep1 = motor.pedir(nombre, "generar", SISTEMA, prompt_generar(nombre, t, clase, estilo, n, esc, ciudad), meta,
                               "textos", n, 4096, 1.0)
    textos = textos[:n + 5]
    ok = [x for x in textos if isinstance(x, str)]
    mv = {"tipo": "verificar", "textos": ok, "etiqueta": clase, "tarea": nombre}
    ver, rep2 = motor.pedir(nombre, "verificar", SISTEMA, prompt_verificar(nombre, t, clase, ok), mv, "veredictos",
                            len(ok), 1024, 0.0)
    return {"plantilla": job["plantilla"], "tarea": nombre, "clase": clase, "estilo": estilo, "pedidos": n,
            "textos": ok, "veredictos": [norm(v) == "si" for v in ver], "reparado": rep1 or rep2}


# --- almacenamiento ---------------------------------------------------------------------------------------------
def leer_jsonl(ruta):
    if not os.path.exists(ruta):
        return []
    out = []
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            try:
                out.append(json.loads(linea))
            except ValueError:  # línea cortada por una caída: se vuelve a generar ese lote
                continue
    return out


def e5():
    """Embeddings multilingual-e5-small (prefijo «query: », media normalizada). None si no hay torch o el modelo."""
    try:
        import numpy as np
        import torch
        from transformers import AutoModel, AutoTokenizer
        tok = AutoTokenizer.from_pretrained("intfloat/multilingual-e5-small", local_files_only=True)
        mod = AutoModel.from_pretrained("intfloat/multilingual-e5-small", local_files_only=True).eval()
    except Exception as e:
        print("e5-small no disponible (%s): se omite el coseno" % type(e).__name__)
        return None

    def embeber(textos):
        sal = []
        with torch.no_grad():
            for i in range(0, len(textos), 64):
                b = tok(["query: " + x for x in textos[i:i + 64]], padding=True, truncation=True, max_length=128,
                        return_tensors="pt")
                h = mod(**b).last_hidden_state
                m = b["attention_mask"].unsqueeze(-1).to(h.dtype)
                v = (h * m).sum(1) / m.sum(1)
                sal.append(torch.nn.functional.normalize(v, dim=-1).numpy())
        return np.concatenate(sal) if sal else np.zeros((0, 384), dtype="float32")
    return embeber


def referencias(nombre):
    if nombre not in REFERENCIAS:
        return []
    ruta = os.path.join(T.MODEL, *REFERENCIAS[nombre])
    return [{"texto": r["texto"], "etiqueta": r["etiqueta"]} for r in leer_jsonl(ruta)]


def construir(nombre, t, lotes, args, embeber):
    """De los lotes verificados al archivo de la tarea. Devuelve (filas, descartes, por_estilo)."""
    d = {"lotes_sin_respuesta": 0, "vacio_o_largo": 0, "verificador_no": 0, "generados": 0, "verificados": 0}
    cand = []
    por_estilo = {}
    for lote in lotes:
        for texto, bueno in zip(lote["textos"], lote["veredictos"]):
            d["generados"] += 1
            texto = texto.strip()
            if not texto or len(texto) > MAX_CHARS:
                d["vacio_o_largo"] += 1
                continue
            d["verificados"] += 1
            e = por_estilo.setdefault(lote["estilo"], {"verificados": 0, "rechazados": 0})
            e["verificados"] += 1
            if not bueno:
                d["verificador_no"] += 1
                e["rechazados"] += 1
                continue
            cand.append({"texto": texto, "etiqueta": lote["clase"], "plantilla": lote["plantilla"]})
    cand.sort(key=lambda f: (f["plantilla"], f["texto"]))
    pre = len(cand)
    filas, dd = deduplicar(cand, referencias(nombre), embeber)
    d.update(dd)
    d["tras_dedup"] = len(filas)
    d["dedup_total"] = pre - len(filas)
    n_pl = {}
    for f in filas:
        n_pl[f["plantilla"]] = n_pl.get(f["plantilla"], 0) + 1
    split = repartir(n_pl, 0.10, args.semilla)
    cont = {"train": 0, "dev": 0}
    salida = []
    for f in sorted(filas, key=lambda f: (f["plantilla"], f["texto"])):
        sp = split[f["plantilla"]]
        salida.append({"id": "t13-%s:%s:%d" % (nombre, sp, cont[sp]), "tarea": nombre, "tipo": "choice",
                       "pregunta": t["pregunta"], "texto": f["texto"], "opciones": t["opciones"],
                       "descripciones": t["descripciones"], "etiqueta": f["etiqueta"], "idioma": "es-CO", "split": sp,
                       "fuente": args.fuente, "licencia": args.licencia, "uso_comercial": True, "plantilla": f["plantilla"]})
        cont[sp] += 1
    validar_conjunto(salida)
    return salida, d, por_estilo


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tareas", nargs="+", default=["whatsapp_comercio", "pqrs", "fintech", "herramientas"])
    ap.add_argument("--por-clase", type=int, required=True, help="textos pedidos por clase (antes de verificar y dedup)")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--backend", choices=["local", "bedrock", "simulado"], default="local",
                    help="local: Qwen abierto en la GPU (por defecto); bedrock: Haiku, solo evaluación; simulado: pruebas")
    ap.add_argument("--tope-usd", type=float, default=8.0, help="solo --backend bedrock")
    ap.add_argument("--tope-min", type=float, default=0, help="minutos de reloj máximos de esta ejecución (0 = sin tope)")
    ap.add_argument("--motor", choices=["auto", "vllm", "transformers"], default="auto", help="motor del backend local")
    ap.add_argument("--precio-in", type=float, help="USD por millón de tokens de entrada")
    ap.add_argument("--precio-out", type=float, help="USD por millón de tokens de salida")
    ap.add_argument("--lote", type=int, default=20, help="textos por llamada de generación")
    ap.add_argument("--semilla", type=int, default=1)
    ap.add_argument("--hilos", type=int, default=None, help="peticiones en paralelo (local 32, resto 4)")
    ap.add_argument("--modelo", default=None, help="local: id del Hub o ruta (por defecto el mayor Qwen que exista); bedrock: id")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--max-reintentos", type=int, default=5)
    ap.add_argument("--espera-base", type=float, default=2.0, help="segundos del primer reintento (se duplica)")
    ap.add_argument("--sin-llamadas", action="store_true", help="no llama al modelo: ensambla salidas con lo ya escrito")
    ap.add_argument("--embeddings", choices=["auto", "no"], default="auto")
    args = ap.parse_args(argv)

    if args.backend == "bedrock" and (args.precio_in is None or args.precio_out is None):
        ap.error("--backend bedrock exige --precio-in y --precio-out (USD por millón de tokens)")
    args.hilos = args.hilos or (32 if args.backend == "local" else 4)
    pin = 1.0 if args.precio_in is None else args.precio_in
    pout = 5.0 if args.precio_out is None else args.precio_out
    if args.backend == "local":
        pin = pout = 0.0
    todas = T.tareas()
    for n in args.tareas:
        if n not in todas:
            ap.error("tarea desconocida %r; hay %s" % (n, sorted(todas)))
    os.makedirs(os.path.join(args.salida, "crudo"), exist_ok=True)
    gasto = Gasto(os.path.join(args.salida, "gasto.jsonl"), args.tope_usd, pin, pout)
    gasto0 = gasto.usd
    inicio = time.time()
    if args.tope_min > 0:
        gasto.vence = inicio + 60 * args.tope_min
    args.fuente, args.licencia, lic_modelo = T.FUENTE, T.LICENCIA, None
    if args.backend == "local":
        args.modelo = args.modelo or elegir_modelo()
        lic_modelo = exigir_apache(args.modelo)
        args.fuente = "chispa T1.3 (%s, local)" % args.modelo
        args.licencia = "%s + %s" % (lic_modelo, T.LICENCIA)
        print("modelo %s, licencia de la tarjeta: %s" % (args.modelo, lic_modelo), flush=True)
        backend = Local(args.modelo, args.motor)
        print("motor: %s" % backend.motor, flush=True)
    elif args.backend == "bedrock":
        args.modelo = args.modelo or MODELO_BEDROCK
        backend = Bedrock(args.modelo, args.region)
    else:
        backend = Simulado(args.semilla)
    motor = Motor(backend, gasto, args.hilos, args.max_reintentos, args.espera_base)
    print("generar: tareas=%s por_clase=%d backend=%s tope=%s (ya gastado: %.4f USD)"
          % (",".join(args.tareas), args.por_clase, args.backend,
             "%g min" % args.tope_min if args.backend == "local" else "%.2f USD" % args.tope_usd, gasto0), flush=True)

    fallos = {}
    for nombre in args.tareas:
        t = todas[nombre]
        crudo = os.path.join(args.salida, "crudo", nombre + ".jsonl")
        hechos = {r["plantilla"] for r in leer_jsonl(crudo)}
        pend = [j for j in trabajos(nombre, t, args.por_clase, args.lote, args.semilla) if j["plantilla"] not in hechos]
        print("[%s] %d lotes, %d ya hechos" % (nombre, len(pend) + len(hechos & {j["plantilla"] for j in trabajos(
            nombre, t, args.por_clase, args.lote, args.semilla)}), len(hechos)), flush=True)

        def una(job, t=t, crudo=crudo):
            if gasto.parado or args.sin_llamadas:
                return None
            try:
                r = hacer_lote(motor, t, job, args.semilla)
            except TopeAlcanzado:
                return None
            except Exception as e:
                fallos[job["plantilla"]] = str(e)
                print("  lote fallido %s: %s" % (job["plantilla"], e), flush=True)
                return None
            with gasto.lock:
                with open(crudo, "a", encoding="utf-8") as f:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            return r

        with ThreadPoolExecutor(max_workers=max(1, args.hilos)) as ex:
            for i, r in enumerate(ex.map(una, pend), 1):
                if i % 10 == 0 or i == len(pend):
                    print("  [%s] %d/%d lotes, %.4f USD, %d llamadas" % (nombre, i, len(pend), gasto.usd, gasto.llamadas),
                          flush=True)
        if gasto.parado:
            print("PARADO POR TOPE: %.4f USD de %.2f, %.1f min de %g (se escribe lo que hay)"
                  % (gasto.usd, args.tope_usd, (time.time() - inicio) / 60, args.tope_min), flush=True)
            break

    embeber = e5() if args.embeddings == "auto" else None
    resumen = {"fuente": args.fuente, "backend": args.backend, "modelo": args.modelo or "simulado",
               "licencia_modelo": lic_modelo, "motor": getattr(backend, "motor", None), "licencia": args.licencia,
               "minutos_esta_ejecucion": round((time.time() - inicio) / 60, 2), "tope_min": args.tope_min,
               "por_clase_pedido": args.por_clase, "lote": args.lote, "semilla": args.semilla,
               "parado_por_tope": gasto.parado, "tope_usd": args.tope_usd,
               "usd_total": round(gasto.usd, 6), "usd_esta_ejecucion": round(gasto.usd - gasto0, 6),
               "llamadas": gasto.llamadas, "tokens_in": gasto.tin, "tokens_out": gasto.tout,
               "reintentos_esta_ejecucion": motor.reintentos, "coseno": "e5-small" if embeber else "omitido",
               "lotes_fallidos": len(fallos), "tareas": {}}
    for nombre in args.tareas:
        t = todas[nombre]
        pls = {j["plantilla"] for j in trabajos(nombre, t, args.por_clase, args.lote, args.semilla)}
        lotes = [r for r in leer_jsonl(os.path.join(args.salida, "crudo", nombre + ".jsonl")) if r["plantilla"] in pls]
        filas, d, por_estilo = construir(nombre, t, lotes, args, embeber)
        d["lotes_sin_respuesta"] = len(pls) - len(lotes)
        with open(os.path.join(args.salida, nombre + ".jsonl"), "w", encoding="utf-8") as f:
            for r in filas:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        clases = {o: {"train": 0, "dev": 0} for o in t["opciones"]}
        for r in filas:
            clases[r["etiqueta"]][r["split"]] += 1
        ver = max(1, d["verificados"])
        resumen["tareas"][nombre] = {
            "filas": len(filas), "train": sum(c["train"] for c in clases.values()), "dev": sum(c["dev"] for c in clases.values()),
            "filas_por_clase": clases, "descartes": d, "por_estilo": por_estilo,
            "pct_verificador_no": round(100 * d["verificador_no"] / ver, 1),
            "pct_dedup": round(100 * d["dedup_total"] / max(1, d["verificados"] - d["verificador_no"]), 1),
            "gasto": {k: (round(v, 6) if k == "usd" else v) for k, v in gasto.por_tarea.get(nombre, {}).items()},
        }
        tr = resumen["tareas"][nombre]
        print("[%s] %d filas (train %d, dev %d); verificador no %.1f%%, dedup %.1f%%"
              % (nombre, tr["filas"], tr["train"], tr["dev"], tr["pct_verificador_no"], tr["pct_dedup"]), flush=True)
    resumen["hipotesis_refutada"] = any(r["pct_dedup"] > 40 or r["pct_verificador_no"] > 30
                                        for r in resumen["tareas"].values())
    with open(os.path.join(args.salida, "resumen.json"), "w", encoding="utf-8") as f:
        json.dump(resumen, f, ensure_ascii=False, indent=1)
    print("resumen: %.4f USD, %d llamadas, %d tokens in, %d out; parado_por_tope=%s"
          % (gasto.usd, gasto.llamadas, gasto.tin, gasto.tout, gasto.parado), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
