"""Codificador BERT diminuto y aleatorio con tokenizer de letras, construido en memoria (nada se baja)."""
import string

from transformers import BertConfig, BertModel, BertTokenizerFast

from model.alt.modelo import CrossEncoder


def tokenizer(dir_tmp):
    piezas = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]"] + list(string.ascii_lowercase + string.digits + string.punctuation)
    piezas += ["##" + c for c in string.ascii_lowercase + string.digits]
    return BertTokenizerFast(vocab={x: i for i, x in enumerate(dict.fromkeys(piezas))}, do_lower_case=True)


def modelo(dir_tmp, **kw):
    tok = tokenizer(dir_tmp)
    cfg = BertConfig(vocab_size=len(tok), hidden_size=16, num_hidden_layers=1, num_attention_heads=2, intermediate_size=32,
                     max_position_embeddings=128)
    return CrossEncoder(BertModel(cfg), tok, "diminuto-aleatorio", **kw)


def filas(n=20):
    """n filas con choice, noul y score (con y sin blanda), todas comerciales y de train/dev."""
    out = []
    for i in range(n):
        t = ("choice", "noul", "score")[i % 3]
        if t == "choice":
            ops, desc, etq = ["a", "b", "c"], {"a": "primera", "b": "segunda", "c": "tercera"}, "abc"[i % 3]
        elif t == "noul":
            ops, desc, etq = ["false", "true"], {"false": "", "true": ""}, "true" if i % 2 else "false"
        else:
            ops, desc, etq = ["1", "2", "3"], {"1": "malo", "2": "regular", "3": "bueno"}, str(1 + i % 3)
        f = {"id": "dem:%s:%d" % ("dev" if i % 5 == 4 else "train", i), "tarea": "demo", "tipo": t, "pregunta": "que es esto %d" % i,
             "texto": "mensaje numero %d con algo de texto" % i, "opciones": ops, "descripciones": desc, "etiqueta": etq, "idioma": "es",
             "split": "dev" if i % 5 == 4 else "train", "fuente": "demo", "licencia": "cc-by-4.0", "uso_comercial": True}
        if i % 4 == 0:
            f["blanda"] = {o: (0.7 if o == etq else 0.3 / (len(ops) - 1)) for o in ops}
        out.append(f)
    return out
