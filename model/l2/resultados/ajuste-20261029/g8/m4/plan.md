# M4 plan de reentrenamiento para cerrar la brecha es − en (preparado, NO lanzado)

Motivo: |es − en| > 3 puntos (ver `espanol.json`).

## Fuentes en español con licencia comercial

| fuente | para qué | filas aprox. | uso | licencia en la tarjeta de HF | entra en train |
|---|---|---|---|---|---|
| SINAI/ALIA-es-discriminative-hate-speech | toxicidad/odio en español | 8000 | train | cc-by-4.0 | sí |
| Multilingual-Perspectivist-NLU/MultiPICo | ironía en español (perspectivista) | 6000 | train | cc-by-4.0 | sí |
| bgonzalezbustamante/toxicity-Constitution-ES | toxicidad en español | 4000 | train | cc-by-4.0 | sí |
| bgonzalezbustamante/toxicity-protests-ES | toxicidad en español (protestas) | 4000 | train | cc-by-4.0 | sí |
| google-research-datasets/paws-x | paráfrasis es/en (noul) | 49000 | train | other | NO hasta comprobar |
| Davlan/sib200 | tema es/en (7 clases) | 700 | train | cc-by-sa-4.0 | sí |
| (PQRS propios) | PQRS en español colombiano | - | solo test | propia (sin publicar) | solo test |

Las licencias se leen de `README.md` de la caché de ~/hf; si no está ahí, queda «NO COMPROBADA». PQRS solo entra en test.

## Tamaño

≈ 71700 filas nuevas en español en `train` (tope por tarea 2000 y p ∝ n^0,3, así que cada fuente aporta como mucho 2000 por tarea tras el reparto: unas 10000 filas efectivas). Es < 10 % de la mezcla de G.8.

## Cambios en `model/l2/aws/general.sh`

1. `CONV`: pasar `--fuentes` con las nuevas (`odio_alia`, `toxicidad_constitucion`, `toxicidad_protestas` ya están en `model.datos`; MultiPICo, PAWS-X y SIB-200 necesitan conversor nuevo en `model/datos/` con licencia comprobada en la tarjeta).
2. Descarga de HF: `snapshot_download` de esos datasets (con `HF_HUB_OFFLINE=1` después).
3. `EXCLUIR`: dejar `massive,hatecheck,inyecciones` fuera del entrenamiento (siguen siendo el test no visto) y añadir `xnli` solo a test.
4. `G8`: mantener `--tope-tarea 2000 --alfa 0.3 --max-tok 256`; subir `--frac-es` (o equivalente) si el reparto lo permite, sin tocar el resto.
5. Evaluar con `python -m model.l2.espanol` y `model.l2.robustez` al terminar (mismo checkpoint) para comprobar que la brecha baja de 3 puntos.

## Coste en GPU

g5.xlarge, ~1.01 USD/h: reentrenamiento completo ≈ 3.0 h de entrenamiento + 1 h de descarga y evaluación = tope de 240 min de general.sh = **≈ 4.0 USD** (+ ~0,1 USD de disco). Una corrida de ajuste fino desde el checkpoint de G.8 (1 h de entrenamiento) saldría en ≈ 2.0 USD.
