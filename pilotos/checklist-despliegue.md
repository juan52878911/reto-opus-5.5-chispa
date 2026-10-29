# Lista de verificación de despliegue de `chispa-server`

Una página. El detalle y el porqué de cada punto están en [`operacion.md`](operacion.md). `$URL` = `http://127.0.0.1:8090` (o la del servicio).
Valores marcados *(sug.)* son sugerencias, no compromisos del producto.

**Antes**
- [ ] `.chispa` del cliente en una ruta de solo lectura, con fecha en el nombre; `sha256sum` guardado.
- [ ] Si el modelo trae `TORR` o L2: `e5.chispa-tok` (12 MB) montado y binario/imagen compilado con `-tags ort` (+ `libonnxruntime.so` compatible).
- [ ] Máquina con RAM para el `.chispa` + el tokenizador + montón de Go + margen (orientativo y sin medir: 512 MB con L1 de 155 MB; 1 GB con L2, `deploy/kindling/README.md`).
- [ ] `config.json` válido (τ en [0,1], cachés ≥ 1, límites ≥ 0); probado en un puerto auxiliar con `-addr 127.0.0.1:18090`.
- [ ] El puerto solo es alcanzable desde el sistema del cliente: el servidor no trae TLS ni autenticación (pendiente de producto); los pone el proxy del cliente.
- [ ] `-addr` correcto: por defecto es `127.0.0.1:8090` (solo local); en contenedor, `0.0.0.0`.

**Arranque**
- [ ] `chispa-server -addr … -modelo … [-tok …] [-config …] [-timeout 30s]` (o `docker run` / `kling run`, ver `operacion.md` §2).
- [ ] Reinicio automático configurado (`--restart unless-stopped` o unidad systemd).
- [ ] El log de arranque dice `chispa-server en <addr>: N modelos en L0` y **no** avisa de «falta -tok» ni de L2 en stub (si L2 es necesario).

**Prueba de humo**
- [ ] `curl -fsS $URL/healthz` → `{"status":"ok"}` (solo dice que el proceso vive).
- [ ] `curl $URL/v1/decide -d '{…}'` (ejemplo de `operacion.md` §7) → 200, con `layer`, `answer`, `probs`.
- [ ] `chispa decide --url $URL --estado "…" --pregunta "…" --opciones a b c` responde.
- [ ] `chispa evaluar --url $URL --esquema esquema.yaml --datos muestra.csv --salida humo-AAAAMMDD` genera `.md` y `.json`; exactitud y escalado cerca de la línea base.
- [ ] No todo da `escalar`: algunas decisiones salen de L0, L1 o L2 (`chispa_decididas_total{capa}`).

**Vigilancia (alertas *(sug.)*)**
- [ ] Escalado `chispa_escalados_total / chispa_preguntas_total` > 20 % durante 15 min.
- [ ] `chispa_peticiones_total{codigo}`: 4xx > 5 % en 10 min; cualquier 5xx sostenido.
- [ ] `chispa_timeouts_total` creciendo; p99 de `chispa_capa_latencia_segundos` > 2× la línea base (L2 > 20 ms).
- [ ] `chispa_capa_errores_total` y `chispa_torres_errores_total` > 0 sostenido.
- [ ] Línea base de la semana 1 anotada; RAM y CPU del proceso vigiladas con las herramientas del sistema (no están en `/metrics`).

**Registros**
- [ ] stderr recogido (`docker logs` / `journalctl`) y log de arranque conservado. No hay log de peticiones; el servidor no guarda textos.

**Actualizar el modelo**
- [ ] Modelo nuevo con otro nombre; no sobrescribir el abierto. Probado en puerto auxiliar con humo + `chispa evaluar`.
- [ ] `mv` atómico del `.chispa` nuevo sobre la ruta de `-modelo` y recarga en caliente (`kill -HUP` o `POST /v1/admin/recargar` con `admin_token`); sin ventana de caída. Un 500 `reload_failed` deja el modelo viejo en servicio.
- [ ] `chispa_recargas_total{resultado="ok"}` sube y el log dice `modelo N en servicio`; humo después. Si falla, `mv` del `.chispa` anterior y recargar.
- [ ] Cliente: el 503 `timeout` y el 504 no se reintentan; el resto de 503 sí, con `Retry-After` y backoff.

**Copia de seguridad**
- [ ] Guardados: los 3 últimos `.chispa`, `config.json`, `e5.chispa-tok`, el esquema, la línea de arranque, versiones de binario/imagen y de ORT, `SHA256SUMS`.

**Si algo falla**
- [ ] Latencia, escalado, 4xx, 5xx o memoria: `operacion.md` §9. Misma causa dos veces seguidas: parar y escalar a SDK.
