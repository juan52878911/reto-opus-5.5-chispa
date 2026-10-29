# audio/: Jev de audio de Chispa (fase 5)

Diseño en `DISENO.md`; esqueleto sin modelos en `chispa_audio/` (solo numpy). Tests: `python3 -m unittest discover -s tests -t .` desde esta carpeta.

## Capa `A1` y contrato de `layer`
La cabeza de audio responde con la forma de `/v1/decide` pero con `layer: "A1"`. El audio **no** entra por `POST /v1/decide`, así que `A1` no está en el `layer` de `server/api/openapi.yaml` (L0–L3 y `escalar`). Un consumidor que filtre por capa y mezcle ambas fuentes debe tratar `layer` como valor abierto y aceptar `A1`.
