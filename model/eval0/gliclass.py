"""GLiClass modern-base-v3.0 (knowledgator), zero-shot con las descripciones de las opciones como etiquetas.
El paquete `gliclass` no está instalado (sin red): se reimplementa su arquitectura uni-encoder desde config.json y los
nombres de los pesos, siguiendo su pipeline: «<<LABEL>>l1<<LABEL>>l2...<<SEP>>texto» (prompt_first), ModernBERT,
pooling 'first' para el texto, embeddings en las posiciones <<LABEL>>, proyectores MLP (linear_1 → gelu → linear_2),
scorer 'simple' (producto punto; sin exp(logit_scale), que saturaba el softmax a 1e-26: el escalado solo cambia ECE, no el argmax). Etiqueta única: softmax sobre las clases.
Es un modelo ModernBERT-base inglés (vocab 50 368): no es multilingüe por construcción."""
import glob, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import common

G = glob.glob(os.path.expanduser("~/hf/hub/models--knowledgator--gliclass-modern-base-v3.0/snapshots/*"))[0]


class GLiClass:
    def __init__(self, tarea):
        import torch
        from torch import nn
        from safetensors.torch import load_file
        from transformers import AutoTokenizer, ModernBertConfig, ModernBertModel
        cfg = json.load(open(G + "/config.json"))
        self.cfg = cfg
        self.tok = AutoTokenizer.from_pretrained(G)
        ec = ModernBertConfig(**{k: v for k, v in cfg["encoder_config"].items() if k not in ("architectures", "id2label", "label2id")})
        ec.vocab_size = cfg["vocab_size"]
        try:
            from transformers.initialization import no_init_weights
        except ImportError:
            from transformers.modeling_utils import no_init_weights
        with no_init_weights():  # la inicialización aleatoria tarda minutos en esta CPU y los pesos se sobrescriben
            self.enc = ModernBertModel(ec).eval()
        w = load_file(G + "/model.safetensors")
        sd = {k[len("model.encoder_model."):]: v for k, v in w.items() if k.startswith("model.encoder_model.")}
        print(self.enc.load_state_dict(sd, strict=False))
        mlp = lambda p: nn.Sequential(nn.Linear(768, 768), nn.GELU(), nn.Linear(768, 768))
        self.tp, self.cp = mlp(0), mlp(0)
        for m, name in ((self.tp, "text_projector"), (self.cp, "classes_projector")):
            m[0].load_state_dict({"weight": w[f"model.{name}.linear_1.weight"], "bias": w[f"model.{name}.linear_1.bias"]})
            m[2].load_state_dict({"weight": w[f"model.{name}.linear_2.weight"], "bias": w[f"model.{name}.linear_2.bias"]})
            m.eval()
        self.scale = float(w["model.logit_scale"].exp())
        self.tarea = tarea
        self.torch = torch
        self.label_id = cfg["class_token_index"]

    def _scores(self, texto, etiquetas):
        torch = self.torch
        prompt = "".join("<<LABEL>>" + e for e in etiquetas) + "<<SEP>>" + texto
        b = self.tok(prompt, return_tensors="pt", truncation=True, max_length=1024)
        with torch.inference_mode():
            h = self.enc(input_ids=b["input_ids"], attention_mask=b["attention_mask"]).last_hidden_state
            pos = (b["input_ids"][0] == self.label_id).nonzero().flatten()
            if len(pos) != len(etiquetas):
                raise ValueError(f"etiquetas encontradas {len(pos)} != {len(etiquetas)}")
            t = self.tp(h[:, 0])
            c = self.cp(h[0, pos])
            return (c @ t[0]).numpy()

    def predecir(self, f):
        d = f["descripciones"]
        etiquetas = [d[o] for o in f["opciones"]]
        z = self._scores(f["texto"], etiquetas)
        p = np.exp(z - z.max())
        return p / p.sum()


if __name__ == "__main__":
    common.main("gliclass", lambda t, tr, a: GLiClass(t), "no consta (el snapshot no trae README ni LICENSE)")
