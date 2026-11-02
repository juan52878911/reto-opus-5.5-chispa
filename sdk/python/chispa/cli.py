"""`chispa train …` y `chispa decide …`."""
from __future__ import annotations

import argparse
import json
import os
import sys

from .cliente import Chispa, ChispaError
from .tipos import Choice, Multi, Noul, Score


DESCRIPCION = """Chispa: clasificador tipado (choice, score, noul, multi) de bajo coste. Decide sobre esquemas y opciones que no ha visto.

  chispa train    arma un fichero .chispa en CPU (zero-shot, few-shot o con datos del cliente)
  chispa decide   hace una pregunta a un servidor chispa-server (/v1/decide)
  chispa evaluar  mide un servidor con una muestra etiquetada del cliente (exactitud, F1, escalado, cobertura, latencia);
                  con --bateria, la batería de regresión (varios conjuntos, línea base y umbrales: sale ≠ 0 si algo empeora)

Ayuda de cada orden: chispa train --help, chispa decide --help, chispa evaluar --help."""

EPILOGO_TRAIN = """\
Los tres modos (los elige chispa según lo que le pases):

  1. zero-shot      sin --ejemplos. Solo cuenta el esquema: L1 se arma con las descripciones de las opciones.
                      chispa train --esquema ferreteria.yaml --salida f.chispa --l1 potion.chispa-l1
  2. few-shot       --ejemplos con pocos casos por opción (menos de 10 en alguna): sin L0, y L1 se calibra con ellos.
                      chispa train --esquema ferreteria.yaml --ejemplos ej.csv --salida f.chispa --l1 potion.chispa-l1
                    Con 10 o más por opción entrena también L0 (necesita Go).
  3. --conjunta     con datos del cliente: al menos 20 ejemplos por opción (con menos avisa y cae a few-shot).
                    Añade la cabeza conjunta L0 + L2. Necesita --ckpt, torch y el repositorio (--repo o CHISPA_REPO).
                      chispa train --esquema e.yaml --ejemplos ej.csv --salida f.chispa --ckpt mejor.pt --l2 l2.chispa --conjunta --repo .

--torre torre.onnx se combina con cualquiera de los tres: añade la sección TORR, con la que el servidor (compilado con -tags ort)
y el móvil calculan al vuelo la torre de un esquema nuevo en L2. Necesita `pip install chispa[torre]`.
La versión del texto de torre (META.texto_torre, v1 o v2_sin_id) se copia de la META del l2.chispa (--l2/--ckpt; ausente = v1) y, con --torre, debe
coincidir con la metadata chispa.torre.texto_torre del ONNX (ausente = v1); --texto-torre la fija y debe coincidir con ambas. Si no coinciden, train falla.

Qué hace falta instalado:
  - solo Python: zero-shot, y few-shot sin L0 (META + L1 + CALIB), más --torre con chispa[torre].
  - Go ≥ 1.27 en el PATH: entrena L0. El wheel trae el entrenador y las fuentes de Go; kindling (v0.17.0) debe estar en la
    caché de módulos de Go o accesible por red (GOPROXY). Sin Go, el fichero sale sin L0 y lo avisa.
  - --ckpt y --conjunta (chispa[l2]): además el repositorio de Chispa (model/l2), que el wheel no incluye.
Esquemas .yaml: pip install chispa[yaml]; los .json no lo piden."""


def _validar_destino(ruta: str) -> None:
    """Falla antes de medir si `--guardar-linea-base` no podrá escribir en `ruta`."""
    from .bateria import ErrorBateria
    if os.path.isdir(ruta):
        raise ErrorBateria(f"--guardar-linea-base {ruta}: es un directorio")
    carpeta = os.path.dirname(os.path.abspath(ruta))
    if not os.path.isdir(carpeta) or not os.access(carpeta, os.W_OK) or (os.path.exists(ruta) and not os.access(ruta, os.W_OK)):
        raise ErrorBateria(f"--guardar-linea-base {ruta}: no se puede escribir ahí")


def _bateria(a) -> int:
    """0 bien · 1 una métrica empeora más que su umbral · 2 manifiesto, datos o servidor mal puestos."""
    from .bateria import ErrorBateria, _heredar_estabilidad_min, bateria, cargar_json, json_reporte, linea_base
    aviso = lambda m: print(f"chispa: aviso: {m}", file=sys.stderr)
    try:
        if a.guardar_linea_base and a.solo:
            raise ErrorBateria("--guardar-linea-base con --solo guardaría una línea base parcial: quita --solo")
        previa_dict = None
        if a.guardar_linea_base:
            _validar_destino(a.guardar_linea_base)
            if not a.linea_base and os.path.exists(a.guardar_linea_base):
                try:
                    previa_dict = cargar_json(a.guardar_linea_base, "línea base")
                except ErrorBateria as e:
                    aviso(f"{e}: se ignora y se sobrescribe")
        r = bateria(a.bateria, url=a.url, modelo=a.modelo, servidor=a.servidor, tok=a.tok, config=a.config, extra=a.servidor_arg, linea_base=a.linea_base,
                    umbrales=a.umbrales, robustez=a.robustez, robustez_max=a.robustez_max, solo=a.solo or None, objetivo=a.precision_objetivo,
                    concurrencia=a.concurrencia, timeout=a.timeout, reintentos=a.reintentos, filas=a.filas, agrupar=a.agrupar, aviso=aviso)
        if a.salida:
            with open(a.salida + ".md", "w", encoding="utf-8") as f:
                f.write(r["informe"])
            with open(a.salida + ".json", "w", encoding="utf-8") as f:
                json.dump(json_reporte(r), f, ensure_ascii=False, indent=2)
            print(f"chispa: {a.salida}.md y {a.salida}.json", file=sys.stderr)
        else:
            print(r["informe"], end="")
        if a.guardar_linea_base:
            if r["ok"]:
                if previa_dict is not None:  # regenerar sobre la misma ruta: conserva su estabilidad_min
                    _heredar_estabilidad_min(r, previa_dict)
                lb = linea_base(r)  # falla (2) si la corrida es parcial
                with open(a.guardar_linea_base, "w", encoding="utf-8") as f:
                    json.dump(lb, f, ensure_ascii=False, indent=2)
                print(f"chispa: línea base guardada en {a.guardar_linea_base}", file=sys.stderr)
            else:
                print("chispa: no guardo la línea base: la comparación falla", file=sys.stderr)
    except (ErrorBateria, ChispaError, ValueError, OSError) as e:
        print(f"chispa: {e}", file=sys.stderr)
        return 2
    if not r["ok"]:
        for x in r["comparacion"]["fallos"]:
            print(f"chispa: REGRESIÓN {x['seccion']}/{x['nombre']}: {x['detalle']}", file=sys.stderr)
        return 1
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="chispa", description=DESCRIPCION, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("train", help="arma un .chispa v3 en CPU: zero-shot (sin --ejemplos), few-shot (pocos) o --conjunta (con datos del cliente)",
                       description="Arma un .chispa v3 en CPU a partir de un esquema y, opcionalmente, ejemplos.", epilog=EPILOGO_TRAIN,
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    t.add_argument("--ejemplos", help="CSV/JSONL con columnas texto|text y etiqueta|label. Sin él, zero-shot: L1 con las descripciones "
                   "de las opciones (y L2/ESQUEMAS con --l2/--ckpt). Con pocos por opción (< 10), few-shot: sin L0 y L1 calibrada con ellos")
    t.add_argument("--esquema", required=True, help="YAML/JSON: id, pregunta, tipo, opciones (con descripciones)")
    t.add_argument("--salida", required=True, help="el .chispa que se escribe")
    t.add_argument("--l1", help=".chispa-l1 (potion exportado con runtime/l1/exportar.py)")
    t.add_argument("--ckpt", help="checkpoint de L2: calibra y exporta L2 y ESQUEMAS con model/l2")
    t.add_argument("--perfil", choices=("servidor", "movil", "movil-int8"), default="servidor",
                   help="con --ckpt, perfil del exportador de L2: servidor (defecto: fp32, sin poda de vocabulario) movil (fp16, vocabulario podado y "
                        "ampliado con el esquema, ≈ 89 MB) o movil-int8 (int8, más pequeño, algo menos fiel). La CALIB de L2 de --ckpt pasa a tipos_l2/tau_escalate_l2; la de L1 no se toca. Con --l2 no hace nada: ese .chispa ya se exportó con su perfil")
    t.add_argument("--l2", help=".chispa ya exportado por model/l2/exportar.py: de aquí salen L2 y ESQUEMAS")
    t.add_argument("--conjunta", action="store_true",
                   help="modo «con datos del cliente»: añade la cabeza conjunta L0 + L2 (sección CONJ) y L0TF; necesita train etiquetado "
                        "(--ejemplos, ≥ 20 por opción: con menos avisa por stderr y cae a few-shot), --ckpt y --l2 (o --ckpt solo)")
    t.add_argument("--repo", help="raíz del repositorio de Chispa: solo para --ckpt/--conjunta (por defecto CHISPA_REPO o el que contiene este paquete). Para L0 no hace falta: el wheel trae las fuentes de Go")
    t.add_argument("--shrinkage-lambda", type=float, default=None, metavar="LAMBDA",
                   help="valor sugerido de λ en el informe (≥ 0; por defecto 4, el default del runtime en L1; 0 = solo ejemplos, inf = solo descripción). "
                        "Con --l1 y ejemplos, la sección SOPL1 (k y media de los embeddings de L1 de los ejemplos por opción) se escribe siempre, para que el "
                        "runtime encoja el prototipo hacia ellos, w = k/(k+λ). λ no va en el fichero: se pone en l1_shrinkage_lambda / l2_shrinkage_lambda del "
                        "servidor o en AbrirConSoporte. Con --conjunta la sección lleva la norma de cada ranura de L2c (SOPL1 v2)")
    t.add_argument("--sin-soporte", action="store_true",
                   help="no escribe SOPL1 (el fichero es el de antes del default λ = 4); no se combina con --shrinkage-lambda")
    t.add_argument("--tau-l2-esquema-nuevo", type=float, default=None, metavar="TAU",
                   help="escribe tau_l2_esquema_nuevo (en [0,1]) en CALIB: el τ de L2 cuando la pregunta no estaba en ESQUEMAS y la torre sale al vuelo. "
                        "Sin esta opción no se escribe y L2 usa siempre tau_escalate")
    t.add_argument("--pregunta", help="id de la pregunta si el esquema trae varias")
    t.add_argument("--semilla", type=int, default=1)
    t.add_argument("--frac-valid", type=float, default=0.2)
    t.add_argument("--l0-max-mb", type=float, default=48.0,
                   help="tope de la tabla de pesos de L0 en MB; reduce los buckets de hashing hasta que cabe (kindling rechaza > 64 MiB)")
    t.add_argument("--l0tf-max-mb", type=float, default=48.0,
                   help="con --conjunta: tope de los coeficientes de L0TF en MB; poda el vocabulario por frecuencia hasta que cabe")
    t.add_argument("--precision-objetivo", type=float, default=0.95,
                   help="con --conjunta: precisión mínima de lo aceptado para fijar el τ de L2c fuera de pliegue (0,95)")
    t.add_argument("--validacion", help="con --conjunta: CSV/JSONL de texto y etiqueta, fuera de --ejemplos; el τ de L2c se elige sobre estas filas")
    t.add_argument("--margen", type=float, default=0.02,
                   help="con --conjunta y sin --validacion: el τ fuera de pliegue se fija para precisión objetivo + margen (0,02)")
    t.add_argument("--suelo", type=float, default=0.05,
                   help="con --conjunta y sin --validacion: suelo de τ = el que deja fuera esta fracción fuera de pliegue (0,05)")
    t.add_argument("--tope-tau", type=float, default=0.9,
                   help="con --conjunta: tope del τ de L2c, solo si se fija fuera de pliegue (con < 500 filas de validación o sin ellas) (0,9)")
    t.add_argument("--l0tf-f16", action="store_true", help="con --conjunta: coeficientes de L0TF en f16 en vez de f32")
    t.add_argument("--torre", help="ONNX de la torre de esquemas de L2 (contrato: input_ids/attention_mask int64, h float32 (B, dim), opset ≥ 17): "
                   "añade la sección TORR, con la que el servidor y el móvil calculan la torre al vuelo. Combina con zero-shot, few-shot y --conjunta")
    t.add_argument("--sin-torre", action="store_true", help="no incluir TORR (ni la que esté junto al checkpoint): el .chispa no decide esquemas nuevos en L2 y train no avisa de ello. "
                   "Sin --torre ni --sin-torre, con --ckpt se incluye por defecto el torre.onnx que esté junto al checkpoint; si no hay, train avisa")
    t.add_argument("--texto-torre", choices=("v1", "v2_sin_id"),
                   help="versión del texto con el que se calculan las torres al vuelo (META.texto_torre del .chispa; ausente = v1). Con --l2/--ckpt se copia de la META del l2.chispa y, con --torre, "
                        "debe coincidir con chispa.torre.texto_torre del ONNX (ausente = v1): si hay dos fuentes que difieren, o difieren de este flag, train falla. Sin L2 ni --torre escribe lo que diga (por defecto v1)")
    t.add_argument("--torre-dim", type=int, help="con --torre: dim de h (por defecto de los metadatos del ONNX o de la forma de h)")
    t.add_argument("--torre-max-len", type=int, help="con --torre: tokens máximos del pasaje: los trunca el runtime a este valor (metadatos del ONNX o 128; hasta 512, p. ej. 256 para G.8)")
    t.add_argument("--torre-prefijo", help="con --torre: prefijo del pasaje (metadatos del ONNX o «passage: »)")
    d = sub.add_parser("decide", help="una pregunta contra un servidor chispa-server",
                       description="Hace una pregunta a /v1/decide e imprime el resultado en JSON.",
                       epilog="Ejemplo:\n  chispa decide --url http://127.0.0.1:8090 --estado \"¿cuánto vale el cemento?\" "
                              "--pregunta \"¿Qué necesita?\" --opciones cotizacion pedido factura\n"
                              "Con --tipo score, --opciones lleva el número de niveles.",
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    d.add_argument("--url", required=True, help="base del servidor, p. ej. http://127.0.0.1:8090")
    d.add_argument("--estado", required=True, help="el texto a clasificar")
    d.add_argument("--tipo", choices=["choice", "noul", "score", "multi"], default="choice")
    d.add_argument("--pregunta", required=True, help="el texto de la pregunta")
    d.add_argument("--opciones", nargs="*", default=[], help="choice y multi: ids; score: el número de niveles")
    e = sub.add_parser("evaluar", help="mide un chispa-server con una muestra etiquetada (informe markdown + JSON)",
                       description="Manda cada fila (texto, etiqueta) a /v1/decide y calcula las métricas de pilotos/metrica.md: exactitud, F1 macro, "
                                   "matriz de confusión, escalado, cobertura y precisión de lo aceptado, capas, p50/p99 y, con score, MAE.",
                       epilog="Ejemplo:\n  chispa evaluar --url http://127.0.0.1:8090 --esquema pqrs.json --datos muestra.csv --precision-objetivo 0.95 --salida informe\n"
                              "Escribe informe.md e informe.json; sin --salida imprime el markdown. Cada fila es una petición (un state por petición).\n"
                              "Batería de regresión:\n  chispa evaluar --bateria ejemplos/bateria.json --modelo m.chispa --linea-base base.json --robustez --salida informe\n"
                              "Código de salida: 0 bien, 1 una métrica empeora más que su umbral, 2 manifiesto, datos o servidor mal puestos.",
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    e.add_argument("--url", help="base del servidor, p. ej. http://127.0.0.1:8090")
    e.add_argument("--esquema", help="el mismo YAML/JSON de chispa train (choice, noul, score o multi)")
    e.add_argument("--datos", help="CSV/JSONL con columnas texto|text y etiqueta|label (noul: true/false; score: 1..K)")
    e.add_argument("--bateria", metavar="MANIFIESTO", help="batería de regresión: manifiesto JSON de conjuntos (ver docs/10-bateria.md); con --url o --modelo, en vez de --esquema y --datos")
    e.add_argument("--modelo", help="con --bateria: el .chispa; arranca un chispa-server local (puerto libre) y lo apaga al acabar")
    e.add_argument("--servidor", help="con --modelo: ruta de chispa-server (por defecto CHISPA_SERVER o el PATH)")
    e.add_argument("--tok", help="con --modelo: .chispa-tok de e5 para chispa-server")
    e.add_argument("--config", help="con --modelo: JSON de configuración de chispa-server")
    e.add_argument("--servidor-arg", action="append", default=[], metavar="ARG", help="con --modelo: argumento extra para chispa-server (repetible, p. ej. --servidor-arg=-ort-lib=/x/libonnxruntime.so)")
    e.add_argument("--linea-base", help="con --bateria: JSON de la línea base; sale con 1 si una métrica empeora más que su umbral")
    e.add_argument("--guardar-linea-base", metavar="RUTA", help="con --bateria: escribe la línea base de esta corrida (con --linea-base, solo si pasa)")
    e.add_argument("--umbrales", help="con --bateria: JSON de umbrales {métrica: empeoramiento máximo, por_conjunto: {nombre: {…}}}; pisa a los del manifiesto")
    e.add_argument("--robustez", action="store_true", help="con --bateria: mide la estabilidad frente a variantes de chispa.variantes (si no existe, avisa)")
    e.add_argument("--robustez-max", type=int, default=200, help="con --robustez: filas por conjunto (a paso fijo) que se perturban (200)")
    e.add_argument("--agrupar", action="store_true", help="con --bateria: las filas con el mismo texto viajan en una sola petición (varias preguntas por texto)")
    e.add_argument("--solo", action="append", default=[], metavar="NOMBRE", help="con --bateria: solo estos conjuntos (repetible); la comparación pasa a ser parcial")
    e.add_argument("--pregunta", help="id de la pregunta si el esquema trae varias")
    e.add_argument("--precision-objetivo", type=float, default=None, help="precisión a la que se da la cobertura (0,95; con --bateria, la del manifiesto si la trae)")
    e.add_argument("--concurrencia", type=int, default=4, help="peticiones en vuelo (4)")
    e.add_argument("--timeout", type=float, default=10.0)
    e.add_argument("--reintentos", type=int, default=3)
    e.add_argument("--salida", help="prefijo de salida: escribe PREFIJO.md y PREFIJO.json")
    e.add_argument("--filas", action="store_true", help="incluye en el JSON la predicción de cada fila")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "train":
            from .train import entrenar
            entrenar(a.ejemplos, a.esquema, a.salida, l1=a.l1, ckpt=a.ckpt, l2=a.l2, conjunta=a.conjunta, repo=a.repo,
                     pregunta=a.pregunta, shrinkage_lambda=a.shrinkage_lambda, sin_soporte=a.sin_soporte, tau_l2_esquema_nuevo=a.tau_l2_esquema_nuevo, semilla=a.semilla, frac_valid=a.frac_valid, l0_max_mb=a.l0_max_mb,
                     l0tf_max_mb=a.l0tf_max_mb, l0tf_f16=a.l0tf_f16,
                     precision_objetivo=a.precision_objetivo, validacion=a.validacion, margen=a.margen, suelo=a.suelo, tope_tau=a.tope_tau,
                     texto_torre=a.texto_torre, torre=a.torre, torre_dim=a.torre_dim, torre_max_len=a.torre_max_len, torre_prefijo=a.torre_prefijo, perfil=a.perfil, sin_torre=a.sin_torre,
                     log=lambda m: print(m, file=sys.stderr))
        elif a.cmd == "evaluar" and a.bateria:
            return _bateria(a)
        elif a.cmd == "evaluar":
            if not (a.url and a.esquema and a.datos):
                raise ValueError("evaluar necesita --url, --esquema y --datos (o --bateria MANIFIESTO)")
            from .evaluar import evaluar
            r = evaluar(a.url, a.esquema, a.datos, pregunta=a.pregunta, objetivo=0.95 if a.precision_objetivo is None else a.precision_objetivo, concurrencia=a.concurrencia,
                        timeout=a.timeout, reintentos=a.reintentos)
            if a.salida:
                out = dict(r["metricas"], **({"filas": r["filas"]} if a.filas else {}))
                with open(a.salida + ".md", "w", encoding="utf-8") as f:
                    f.write(r["informe"])
                with open(a.salida + ".json", "w", encoding="utf-8") as f:
                    json.dump(out, f, ensure_ascii=False, indent=2)
                print(f"chispa: {a.salida}.md y {a.salida}.json", file=sys.stderr)
            else:
                print(r["informe"], end="")
        else:
            q = {"choice": lambda: Choice("q", a.pregunta, a.opciones), "noul": lambda: Noul("q", a.pregunta), "multi": lambda: Multi("q", a.pregunta, a.opciones),
                 "score": lambda: Score("q", a.pregunta, int(a.opciones[0]))}[a.tipo]()
            r = Chispa(a.url).decidir(a.estado, [q])[0]
            print(json.dumps(r.__dict__, ensure_ascii=False))
    except (ChispaError, ValueError, OSError) as e:
        print(f"chispa: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
