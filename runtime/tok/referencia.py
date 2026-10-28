#!/usr/bin/env python3
"""Ids de referencia del tokenizador de e5 con transformers (AutoTokenizer), como model/l2/modelo.py:
«query: » + texto, truncation=True, max_length=128, con <s> y </s>.

  referencia.py <dir-e5> <salida.jsonl> [--fuzz N]   casos de borde + frases del sondeo (+ N de fuzz)
  referencia.py <dir-e5> <salida.jsonl> --tokenizers  lo mismo pero con tokenizers sobre tokenizer.json (sin los pasos de transformers)
"""
import importlib.util
import json
import random
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("l1_ref", Path(__file__).resolve().parent.parent / "l1" / "referencia.py")
l1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(l1)

MAX_TOK = 128


def duros():
    base = ["query:", "▁", "a▁b", "▁▁a", "a▁", "▁a ▁b", "a  b", " \t\n a   b　c ", "é ã ñ",
            "é" * 3, "https://ejemplo.com/a/b?c=d&e=f#g", "HTTP://EJEMPLO.COM", "MAYÚSCULAS Y minúsculas",
            "😀 🇨🇴 👨‍👩‍👧 ❤️ 👍🏽", "<s>", "</s>", "<pad>", "<unk>", "<mask>", "a<mask>b", "a <mask> b", "<s></s>",
            "x<s>y", "[CLS]", "\x00", "\x07a", "a​b", "a­b", "ﬁ ﬂ ① ㎏ ｱ ｶﾞ", "ｈｏｌａ　ＭＵＮＤＯ",
            "한국어 日本語 中文 العربية עברית", "�", "a�b", "퟿", "\U0010ffff", "é" * 700,
            "palabra " * 900, "x" * 3000, "a," * 400, "hola mundo " * 30, "ñ " * 126, "ñ " * 127, "ñ " * 128,
            "ñ" * 126, "1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 " * 6]
    return base


def textos(nfuzz):
    vistos, out = set(), []
    for t in duros() + l1.casos_borde() + l1.frases_sondeo() + (l1.fuzz(nfuzz) if nfuzz else []):
        if t not in vistos:
            vistos.add(t)
            out.append(t)
    if nfuzz:  # mezclas de palabras con espacios raros
        rnd = random.Random(11)
        sp = [" ", "  ", "\t", "\n", " ", "　", " ", "​", ""]
        pal = ["hola", "Mundo", "é", "ñandú", "😀", "▁", "<s>", "a", "123", "x.y", "ÁÉÍ", "ｆｕｌｌ", "é"]
        for _ in range(nfuzz):
            out.append("".join(rnd.choice(pal) + rnd.choice(sp) for _ in range(rnd.randint(1, 8))))
    return out


def main(dir_e5, salida, nfuzz=0, solo_tokenizers=False):
    if solo_tokenizers:
        from tokenizers import Tokenizer
        t = Tokenizer.from_file(str(Path(dir_e5) / "tokenizer.json"))
        t.enable_truncation(MAX_TOK)
        ids = lambda s: t.encode("query: " + s).ids
    else:
        from transformers import AutoTokenizer
        tk = AutoTokenizer.from_pretrained(dir_e5)
        ids = lambda s: tk("query: " + s, truncation=True, max_length=MAX_TOK)["input_ids"]
    ts = textos(nfuzz)
    with open(salida, "w", encoding="utf-8") as f:
        for s in ts:
            f.write(json.dumps({"texto": s, "ids": ids(s)}, ensure_ascii=False) + "\n")
    print(len(ts), "frases")


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) < 2:
        sys.exit(__doc__)
    main(a[0], a[1], int(a[3]) if len(a) == 4 and a[2] == "--fuzz" else 0, "--tokenizers" in a)
