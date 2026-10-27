"""Runtime común de THX-01 y Laya (mismo formato de checkpoint: rl_agent_config.json + model.safetensors sobre
mmBERT-base). THX-01 se usa con su librería `thx01` (Agent.system_one), como indica su código; Laya no trae README ni
código en el snapshot, así que se carga con el mismo runtime (si las claves de pesos no casan, falla y queda «no medido»)."""
import glob, os, shutil, sys, tempfile

PREG = {
    "intencion": "¿Qué quiere hacer la persona?",
    "whatsapp_comercio": "¿Qué quiere el cliente en este mensaje de WhatsApp?",
    "herramientas": "¿Qué herramienta debe usar el asistente para atender esta petición?",
}


class Decision:
    def __init__(self, patron, tarea):
        src = glob.glob(os.path.expanduser(patron))[0]
        # Agent escribe en tokenizer_config.json del directorio; el snapshot es de solo lectura: copia sin los pesos.
        d = tempfile.mkdtemp(prefix="dec_")
        for n in os.listdir(src):
            if n not in ("model.safetensors",) and os.path.isfile(os.path.join(src, n)) or n in ("tokenizer", "encoder"):
                p = os.path.join(src, n)
                (shutil.copytree if os.path.isdir(p) else shutil.copy)(p, os.path.join(d, n))
        os.symlink(os.path.join(src, "model.safetensors"), os.path.join(d, "model.safetensors"))
        self.dir = d
        thx = glob.glob(os.path.expanduser("~/hf/hub/models--doofz--THX-01/snapshots/*"))[0]
        sys.path.insert(0, thx)
        import thx01
        try:
            from transformers.initialization import no_init_weights
        except ImportError:
            from transformers.modeling_utils import no_init_weights
        with no_init_weights():  # la inicialización aleatoria tarda minutos en esta CPU; load_state_dict(strict) la sobrescribe
            self.agent = thx01.Agent(d, device="cpu", half=False)
        self.tarea = tarea

    def predecir(self, f):
        if self.tarea == "toxicidad":
            q = {"q": {"type": "noul", "instructions": "¿El mensaje es de odio o tóxico contra una persona o grupo?"}}
            p1 = self.agent.system_one(f["texto"], q)["answers"]["q"]["noul"]
            return [p1 if o == "toxico" else 1 - p1 for o in f["opciones"]]
        q = {"q": {"type": "choice", "instructions": PREG[self.tarea], "criteria": f["descripciones"]}}
        p = self.agent.system_one(f["texto"], q)["answers"]["q"]["probabilities"]
        return [p[o] for o in f["opciones"]]

    def __del__(self):
        shutil.rmtree(getattr(self, "dir", "/nonexistent"), ignore_errors=True)
