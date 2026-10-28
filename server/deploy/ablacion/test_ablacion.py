"""Pruebas en seco de ablacion.py (T4.5b): `python -m pytest server/deploy/ablacion` con ~/venv y PYTHONPATH=repo:sdk/python.

Las de fixtures sintéticos no necesitan red ni modelos. La integración (`test_integracion_*`) usa lo que deja
`CHISPA_LOCAL=1 bash server/deploy/aws/e2e.sh` en /tmp/chispa-e2e (un .chispa pequeño con el e5 de ~/hf) y se salta si no está."""
import json
import os
import struct
import sys
from pathlib import Path

import numpy as np
import pytest

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import ablacion as A  # noqa: E402

REPO = A.REPO
LOCAL = Path(os.environ.get("CHISPA_E2E_BASE", "/tmp/chispa-e2e"))
rng = np.random.default_rng(0)


def unit(x):
    return x / np.linalg.norm(x, axis=-1, keepdims=True)


def fuentes_sinteticas(n=60, C=7, K=4, d=16, iguales=True, semilla=1):
    """Fuentes con srv == ref por construcción (iguales=True) o con srv perturbado."""
    r = np.random.default_rng(semilla)
    ops = [f"c{i}" for i in range(C)]
    filas = [{"id": f"t{i}", "tarea": "x", "opciones": ops, "etiqueta": ops[int(r.integers(C))]} for i in range(n)]
    S = [unit(r.normal(size=(K, d))).astype(np.float32) for _ in range(n)]
    H = {o: unit(r.normal(size=d)) for o in ops}
    P = unit(r.normal(size=(C, K, d)))
    esc = (np.abs(P).max(-1) / 127).astype(np.float32)
    proto = np.clip(np.rint(P / esc[..., None]), -127, 127).astype(np.int8)
    P8 = proto.astype(np.float64) * esc.astype(np.float64)[..., None]
    l0 = [r.dirichlet(np.ones(C) * 0.3) for _ in range(n)]
    cab = {"T": 0.05, "beta": 1.0, "esc": np.array([1.2, 0.05, 1.0]), "w": np.array([1.0, 1.0, 1.0, 0.3, 0.2, 0.1])}
    if iguales:
        # todas las fuentes coinciden: el int8 «servidor» es lo que ya usan las dos
        return A.Fuentes(filas, {"srv": S, "ref": S}, {"srv": H, "ref": H}, {"srv": P8, "ref": P8}, (proto, esc), ops,
                         {"srv": l0, "ref": l0}, cab)
    S2 = [unit(s + 0.2 * r.normal(size=s.shape)).astype(np.float32) for s in S]
    return A.Fuentes(filas, {"srv": S2, "ref": S}, {"srv": H, "ref": H}, {"srv": P8, "ref": P}, (proto, esc), ops,
                     {"srv": l0, "ref": l0}, cab)


def test_corridas_1_y_2_coinciden_por_construccion():
    ar = A.Arnes(fuentes_sinteticas())
    p1, p2 = ar.probs(A.cfg_de("srv")), ar.probs(A.cfg_de("ref"))
    # las fuentes coinciden; D es aritmética (int8 de S frente a float), así que solo difiere en la cuantización de S
    assert len(p1) == len(p2) == 60
    assert max(np.abs(a - b).max() for a, b in zip(p1, p2)) < 0.05
    assert all((a == b).all() for a, b in zip(p1, ar.probs(A.cfg_de("srv"))))   # determinista


def test_sustituir_componentes_iguales_no_cambia_nada():
    f = fuentes_sinteticas()
    ar = A.Arnes(f)
    base = ar.probs(A.cfg_de("srv"))
    for x in "ABCEF":   # D cambia la aritmética: se prueba aparte
        otra = ar.probs(A.cfg_de("srv", **{x: "ref"}))
        assert all(np.allclose(a, b, atol=0, rtol=0) for a, b in zip(base, otra)), x


def test_una_sustitucion_cambia_solo_lo_suyo():
    ar = A.Arnes(fuentes_sinteticas(iguales=False))
    base = ar.probs(A.cfg_de("srv"))
    d = {x: max(np.abs(a - b).max() for a, b in zip(base, ar.probs(A.cfg_de("srv", **{x: "ref"})))) for x in "ABCDEF"}
    assert d["A"] > 1e-3 and d["C"] > 1e-6 and d["D"] > 1e-6     # las ranuras, los prototipos y la cuantización de S
    assert d["B"] == 0 and d["E"] == 0 and d["F"] == 0           # B, E y F son iguales en estas fuentes


def test_corridas_y_tabla():
    f = fuentes_sinteticas()
    res = A.corridas(A.Arnes(f))
    nombres = [r["tipo"] for r in res]
    assert nombres.count("todo-srv") == 1 and nombres.count("todo-ref") == 1 and nombres.count("sustituye") == 6
    r1 = next(r for r in res if r["tipo"] == "todo-srv")["macro_f1"]
    r2 = next(r for r in res if r["tipo"] == "todo-ref")["macro_f1"]
    md, v = A.tabla(res, (r1, r2), "sintetica")
    assert v["valido"] and "ARNÉS ESTÁ MAL" not in md
    md, v = A.tabla(res, (r1 + 0.05, r2), "sintetica")
    assert not v["valido"] and "ARNÉS ESTÁ MAL" in md and not v["culpables"]


def test_tabla_marca_culpable():
    base = {"cfg": {}, "tipo": "sustituye"}
    res = [{"nombre": "1 todo servidor", "tipo": "todo-srv", "macro_f1": 0.771, "cfg": {}},
           {"nombre": "2 todo referencia", "tipo": "todo-ref", "macro_f1": 0.817, "cfg": {}},
           {"nombre": "3E servidor con E de referencia", "macro_f1": 0.812, **base},
           {"nombre": "3C servidor con C de referencia", "macro_f1": 0.775, **base}]
    md, v = A.tabla(res, (0.771, 0.817), "massive")
    assert v["valido"] and v["culpables"] == ["E"] and "Culpable" in md
    res[2]["macro_f1"] = 0.78
    _, v = A.tabla(res, (0.771, 0.817), "massive")
    assert v["culpables"] == []


def test_cabeza_igual_a_la_de_conjunta_py():
    torch = pytest.importorskip("torch")
    pytest.importorskip("sklearn")
    sys.path.insert(0, str(REPO))
    from model.l2 import conjunta as C
    r = np.random.default_rng(3)
    n, k = 40, 9
    l0, l2 = r.dirichlet(np.ones(k) * 0.4, n), r.dirichlet(np.ones(k) * 0.4, n)
    sp, y = r.normal(size=(n, k)) * 0.1, r.integers(0, k, n)
    cab = C.Cabeza("lr", 1e-2).ajustar(l0, sp, l2, y)
    ref = cab.probs(l0, sp, l2)
    got = np.stack([A.cabeza_lr(l0[i], sp[i], l2[i], np.array(cab.esc), cab.w.numpy()) for i in range(n)])
    assert np.abs(ref - got).max() < 1e-9


def test_simproto_int8_contra_un_bucle_ingenuo():
    r = np.random.default_rng(5)
    C, Kp, d, K = 5, 3, 24, 4
    S = unit(r.normal(size=(K, d))).astype(np.float32)
    P = unit(r.normal(size=(C, Kp, d)))
    esc = (np.abs(P).max(-1) / 127).astype(np.float32)
    proto = np.clip(np.rint(P / esc[..., None]), -127, 127).astype(np.int8)
    got = A.simproto_int8(S, proto, esc)
    want = np.zeros(C)
    for c in range(C):
        tot = 0.0
        for s in S:
            e = np.float32(np.abs(s).max() / np.float32(127))
            q = np.rint(s / e).astype(np.int64)
            tot += max(float((q * proto[c, j].astype(np.int64)).sum()) * float(e) * float(esc[c, j]) for j in range(Kp))
        want[c] = tot / K
    assert np.allclose(got, want, rtol=1e-12, atol=1e-12)
    # el producto entero del servidor es el producto float de las S y los prototipos cuantizados
    deq = A.simproto_float(A.deq_ranuras(S), proto.astype(np.float64) * esc.astype(np.float64)[..., None])
    assert np.allclose(got, deq, rtol=1e-12, atol=1e-12)
    # y es una aproximación del cálculo en float (|Δ| de unas milésimas, como en T4.5)
    assert np.abs(got - A.simproto_float(S, proto.astype(np.float64) * esc.astype(np.float64)[..., None])).max() < 5e-3


def test_parsers_de_esquemas_y_conj():
    from chispa import formato
    r = np.random.default_rng(7)
    C, K, d = 3, 2, 8
    proto = r.integers(-127, 128, (C, K, d)).astype(np.int8)
    escala = r.random((C, K)).astype(np.float32)
    h = formato.hash_esquema("pregunta", ["a", "b", "c"])
    e = {"hash": h, "T": 0.03, "beta": 0.7, "esc": [1.0, 2.0, 3.0], "w": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6], "clases": ["a", "b", "ñ"],
         "escala": escala, "proto": proto}
    got = A.leer_conj(formato.conj([e]))[0]
    assert got["clases"] == ["a", "b", "ñ"] and got["K"] == K and got["d"] == d
    assert np.allclose(got["w"], e["w"]) and np.allclose(got["esc"], e["esc"]) and abs(got["T"] - 0.03) < 1e-7
    assert (got["proto"] == proto).all() and (got["escala"] == escala).all()
    # ESQUEMAS: dos entradas ordenadas por hash
    hs = sorted([formato.hash_esquema("p", ["x"]), formato.hash_esquema("p", ["y"])])
    vec = r.integers(-127, 128, (2, 5)).astype(np.int8)
    esc = np.array([0.5, 0.25], "<f4")
    b = struct.pack("<II", 5, 2) + b"".join(hs) + esc.tobytes() + vec.tobytes()
    t = A.leer_esquemas(b)
    assert (t[hs[1]][0] == vec[1]).all() and t[hs[0]][1] == 0.5


def test_comparar_servidor():
    f = fuentes_sinteticas(n=10)
    probs = A.Arnes(f).probs(A.cfg_de("srv"))
    pred = A.a_preds(f.filas, probs)
    for p in pred:
        p["layer"] = "L2"
    c = A.comparar_servidor(f.filas, probs, pred)
    assert c["acuerdo_top1"] == 1.0 and c["dif_max"] < 1e-12 and c["capas_servidor"] == {"L2": 10}
    pred[0]["probs"] = {o: 1.0 / len(f.filas[0]["opciones"]) + (0.2 if i == 0 else 0) for i, o in enumerate(f.filas[0]["opciones"])}
    assert A.comparar_servidor(f.filas, probs, pred)["dif_max"] > 0.1


def test_atajo_de_la_cascada_forzada():
    f = fuentes_sinteticas(n=5)
    uno = np.zeros(len(f.filas[0]["opciones"]))
    uno[2] = 1.0
    f.L0["srv"][0] = uno
    ar = A.Arnes(f)
    assert np.allclose(ar.probs(A.cfg_de("srv"))[0], uno)                       # L0 con confianza 1 responde
    assert not np.allclose(ar.probs(A.cfg_de("srv", F="ref"))[0], uno)          # sin el atajo, decide la cabeza


# ---------------------------------------------------------------- integración con un .chispa pequeño de e2e.sh en seco
def _servidor():
    p = Path(os.environ.get("CHISPA_SERVIDOR", LOCAL / "chispa-server"))
    return p if p.is_file() else None


@pytest.mark.skipif(not (LOCAL / "modelos/clinc150.chispa").is_file() or _servidor() is None, reason="sin lo que deja e2e.sh en seco")
def test_integracion_servir_l0():
    from chispa import formato
    prep = LOCAL / "prep/clinc150"
    test = A.leer_jsonl(prep / "test.jsonl")[:20]
    pred = A.servir_l0(_servidor(), LOCAL / "modelos/clinc150.chispa", test, puerto=8093)
    assert len(pred) == len(test) and all(p["layer"] == "L0" for p in pred)
    assert all(abs(sum(p["probs"].values()) - 1) < 1e-6 for p in pred)


@pytest.mark.skipif(not (LOCAL / "modelos/clinc150.chispa").is_file() or _servidor() is None, reason="sin lo que deja e2e.sh en seco")
def test_integracion_correr_en_seco(tmp_path):
    """El arnés entero sobre el .chispa pequeño: autocomprobación de «todo referencia» frente a conjunta.py y las 14 corridas.
    Los objetivos se toman de las propias corridas 1 y 2 (en el fixture no hay cifras de AWS): coinciden por construcción."""
    prep = LOCAL / "prep/clinc150"

    def args(salida, *extra):
        return ["correr", "--tarea", "clinc150", "--chispa", str(LOCAL / "modelos/clinc150.chispa"), "--prep", str(prep),
                "--ckpt", str(LOCAL / "mejor.pt"), "--salida", str(salida), "--servidor", str(_servidor()), "--max", "40", *extra]
    rc = A.main(args(tmp_path, "--objetivo-srv", "0", "--objetivo-ref", "0", "--extras"))
    inf = json.loads((tmp_path / "ablacion.json").read_text())
    assert rc in (0, 3)
    ac = inf["autocomprobacion"]
    assert ac["dif_max_simproto"] < 1e-4 and ac["dif_max_probs_L2"] < 1e-4, ac   # el arnés ref reproduce a conjunta.py
    r1, r2 = (next(r for r in inf["corridas"] if r["tipo"] == t)["macro_f1"] for t in ("todo-srv", "todo-ref"))
    out2 = tmp_path / "b"
    rc = A.main(args(out2, "--objetivo-srv", str(r1), "--objetivo-ref", str(r2)))
    assert rc == 0, "con los objetivos de las propias corridas 1 y 2 el arnés debe darse por válido"
    inf2 = json.loads((out2 / "ablacion.json").read_text())
    assert [r["macro_f1"] for r in inf2["corridas"]] == [r["macro_f1"] for r in inf["corridas"] if r["tipo"] != "extra"]
    assert len(inf2["corridas"]) == 14


# ---------------------------------------------------------------- integración lenta: E+ y «conjunta.py pura» con una tarea inventada
def _tarea_inventada(d, clases=5, por_clase=14, n_test=30):
    """Datos inventados (plantillas de frases) con el formato de e2e_util preparar y de model.datos.convertir."""
    r = np.random.default_rng(11)
    ops = [f"clase{c}" for c in range(clases)]
    desc = {o: f"mensajes del tipo {o}" for o in ops}
    verbos = ["quiero", "necesito", "busco", "pido", "deseo"]
    objetos = [["una cita", "un turno"], ["un saldo", "una cuenta"], ["una alarma", "un aviso"], ["un taxi", "un coche"], ["una pizza", "un menú"]]

    def fila(i, c, split):
        t = f"{verbos[int(r.integers(5))]} {objetos[c][int(r.integers(2))]} para {['hoy', 'mañana', 'el lunes'][int(r.integers(3))]} {i}"
        return {"id": f"inv:{split}:{i}", "tarea": "inventada", "tipo": "choice", "pregunta": "¿qué quiere la persona?", "texto": t,
                "opciones": ops, "descripciones": desc, "etiqueta": ops[c], "idioma": "es", "split": split, "fuente": "inventada",
                "licencia": "propia", "uso_comercial": True}
    train = [fila(i * clases + c, c, "train") for i in range(por_clase) for c in range(clases)]
    test = [fila(i, int(r.integers(clases)), "test") for i in range(n_test)]
    d.mkdir(parents=True, exist_ok=True)
    A.escribir_jsonl(d / "ejemplos.jsonl", [{"texto": x["texto"], "etiqueta": x["etiqueta"]} for x in train])
    (d / "esquema.json").write_text(json.dumps({"id": "inventada", "pregunta": train[0]["pregunta"], "tipo": "choice", "opciones": desc},
                                               ensure_ascii=False))
    A.escribir_jsonl(d / "test.jsonl", test)
    A.escribir_jsonl(d / "datos.jsonl", train + test)
    return train + test


@pytest.mark.skipif(not os.environ.get("CHISPA_ABL_LENTO") or not (LOCAL / "mejor.pt").is_file() or _servidor() is None,
                    reason="lenta (≈ 5 min): CHISPA_ABL_LENTO=1 y lo que deja e2e.sh en seco")
def test_integracion_lenta_extras(tmp_path):
    import subprocess
    filas = _tarea_inventada(tmp_path / "prep")
    py, env = sys.executable, {**os.environ, "PYTHONPATH": f"{REPO}:{REPO}/sdk/python", "HF_HUB_OFFLINE": "1"}
    dev = [dict(x, split="dev") for x in filas[:10]]
    A.escribir_jsonl(tmp_path / "dev.jsonl", dev)
    for cmd in ([py, "-m", "model.l2.exportar", "--ckpt", str(LOCAL / "mejor.pt"), "--calib", str(LOCAL / "modelos/calib.json"),
                 "--esquemas", str(tmp_path / "dev.jsonl"), "--salida", str(tmp_path / "l2.chispa"), "--trabajo", str(tmp_path / "onnx"),
                 "--min-top1", "0"],
                [py, "-m", "chispa", "train", "--ejemplos", str(tmp_path / "prep/ejemplos.jsonl"), "--esquema", str(tmp_path / "prep/esquema.json"),
                 "--salida", str(tmp_path / "m.chispa"), "--ckpt", str(LOCAL / "mejor.pt"), "--l2", str(tmp_path / "l2.chispa"),
                 "--conjunta", "--repo", str(REPO)]):
        r = subprocess.run(cmd, cwd=REPO, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-1500:]
    rc = A.main(["correr", "--tarea", "inventada", "--chispa", str(tmp_path / "m.chispa"), "--prep", str(tmp_path / "prep"),
                 "--ckpt", str(LOCAL / "mejor.pt"), "--salida", str(tmp_path / "s"), "--servidor", str(_servidor()),
                 "--datos-orig", str(tmp_path / "prep/datos.jsonl"), "--extras", "--objetivo-srv", "0", "--objetivo-ref", "0"])
    inf = json.loads((tmp_path / "s/ablacion.json").read_text())
    assert "extras_error" not in inf, inf.get("extras_error")
    assert any(c["tipo"] == "extra" for c in inf["corridas"])
    assert 0 <= inf["extras"]["conjunta_pura_macro_f1"] <= 1
    assert inf["autocomprobacion"]["dif_max_probs_L2"] < 1e-4
