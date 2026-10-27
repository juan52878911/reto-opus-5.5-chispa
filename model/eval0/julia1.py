"""Julia-1 (SupersonicLabs): modelo de decisión tipada sobre mmBERT. Uso según scripts/reproduce_typed.py y
metrics/typed-cpu-*.json del checkpoint: load_model(cpu, max_length=1024, head_length=512, strict) y
engine.predict(state=texto, questions=...). Opciones = descripciones (choice); toxicidad = pregunta booleana `noul`."""
import glob, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

CK = glob.glob(os.path.expanduser("~/hf/hub/models--SupersonicLabs--Julia-1/snapshots/*"))[0]
MAXLEN, HEAD = int(os.environ.get("JULIA_MAXLEN", 512)), int(os.environ.get("JULIA_HEAD", 256))
PREG = {
    "intencion": "¿Qué quiere hacer la persona?",
    "whatsapp_comercio": "¿Qué quiere el cliente en este mensaje de WhatsApp?",
    "herramientas": "¿Qué herramienta debe usar el asistente para atender esta petición?",
}


class Julia:
    def __init__(self, tarea):
        sys.path.insert(0, CK)
        from julia.router.engine import FastEngine
        self.e = FastEngine(CK, "cpu", MAXLEN, HEAD, strict_encoding=True)
        enc = self.e.model.encoder
        # La ruta «especializada» del autor usa _update_attention_mask (transformers 5.0.x); aquí hay 5.21 y no existe.
        # Se vuelve al forward original de ModernBERT (misma función, sin la optimización).
        if hasattr(enc, "_julia_original_forward"):
            enc.forward = enc._julia_original_forward
        self.tarea = tarea

    def predecir(self, f):
        if self.tarea == "toxicidad":
            q = {"q": {"type": "noul", "instructions": "¿El mensaje es de odio o tóxico contra una persona o grupo?"}}
            p = self.e.predict(state=f["texto"], questions=q)["answers"]["q"]["probabilities"]
            return [p["true"] if o == "toxico" else p["false"] for o in f["opciones"]]
        q = {"q": {"type": "choice", "instructions": PREG[self.tarea], "criteria": f["descripciones"]}}
        p = self.e.predict(state=f["texto"], questions=q)["answers"]["q"]["probabilities"]
        return [p[o] for o in f["opciones"]]


if __name__ == "__main__":
    common.main("julia1", lambda t, tr, a: Julia(t), "ver provenance.json del checkpoint (sin README ni LICENSE en el snapshot)")
