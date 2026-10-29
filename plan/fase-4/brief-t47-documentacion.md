# T4.7 Documentación de producto de Chispa

## Antecedentes
La salida de la fase 4 pide documentación. Hoy solo hay README técnicos sueltos:
- `README.md` y `server/README.md`;
- `sdk/python/README.md`, `sdk/android`, `sdk/ios` y `demo/wasm`;
- `format/chispa3`, `model/l2/README.md` y `server/deploy/README.md`.

Las cifras medidas están en `model/informes/fase-0.md`, `fase-1.md` y `fase-2.md`, y en `server/deploy/resultados/*/LEEME.md`.

## Hipótesis
Una documentación de producto en `docs/`, escrita para quien integra Chispa y no para quien lo desarrolla, permite pasar
de cero a un `/v1/decide` que funciona siguiendo solo los documentos. Se comprueba con un recorrido en seco: cada comando
de los documentos existe en el repo con esos flags (compruébalo con `--help` o leyendo el código).

## Terminado cuando
- `docs/` contiene:
  - `00-indice.md`;
  - `01-que-es.md`: preguntas tipadas choice, noul y score; la cascada L0 → L1 → L2c → escalar; cuándo escala;
  - `02-inicio-rapido.md`: de 50 ejemplos por clase a un `.chispa` con `chispa train --conjunta`, y de ahí a
    `chispa-server` y una petición `curl`;
  - `03-api.md`: `/v1/decide`, `/healthz` y `/metrics`, con petición y respuesta reales (sácalas de los tests de
    `server/`) y los límites, como `MaxOpciones` 256;
  - `04-formato-chispa.md`: las secciones META, L0, L1, L2, ESQUEMAS, CALIB, CONJ y L0TF; qué lleva cada una y la
    compatibilidad;
  - `05-sdks.md`: Python, Android, iOS (sin compilar) y WASM;
  - `06-despliegue.md`: la imagen OCI, `-tags ort`, el tokenizador `-tok` y el patrón de AWS;
  - `07-rendimiento-y-limites.md`: las cifras medidas con su fuente y las excepciones de G2 (el ECE de hatecheck e
    inyecciones, y la abstención con su objetivo del 20 %).
- Español, frases cortas y sin adornos. Cada cifra lleva enlace a su fuente en el repo, y no se inventa ninguna.
- Enlace a `docs/00-indice.md` desde el `README.md` raíz: una línea.
- Recorrido en seco: lista en el informe los comandos de `02-inicio-rapido.md` y dónde está definido cada flag.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `docs/**` y una línea en `README.md`.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- Host Linux sin Go ni torch: no compiles ni corras modelos. Lee el código.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 90 min de reloj · ≤ 6 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 10 líneas:
- rama y sha;
- los ficheros;
- el recorrido en seco;
- las cifras que no encontraste en el repo.
