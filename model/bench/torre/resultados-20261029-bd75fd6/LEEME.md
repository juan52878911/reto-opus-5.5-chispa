# G.6 con la rama SDK `bd75fd6` (2 c6a, 2026-10-29)

## Torre al vuelo en el servidor: funciona y coincide con Python
- `chispa train --torre`, `chispa-server -tags ort` y `TestIgualdadTransformersPasaje` (prefijo «passage»): **OK**.
- **JevBench a través del servidor**, con torres calculadas al vuelo y los 231 casos fuera de cualquier `.chispa`: exactitud
  **0,411**, frente a 0,407 en Python con los mismos casos. El servidor reproduce a L2.
- **Los 231 casos escalan.** L2 nunca supera su τ, el `tau_escalate` de CALIB calculado para L2 en las tareas de train, así
  que la capa sale «escalar». La respuesta devuelta es la de L2. Que el script marque «FALLO» en «decididos por L2» se debe
  al τ, no a la torre.
- **Fidelidad del int8 dinámico, igual que antes:** coseno 0,986 sin `<unk>` y top-1 0,937. Lo de G.7 (fp32 y estático)
  sigue pendiente.
- **`TestTorreConTokenizadorReal` se salta:** busca `/tmp/e5.chispa-tok`, una ruta fija, en lugar de `CHISPA_TOK`. Es un
  problema de la rama SDK.

## Android sobre `bd75fd6`: falla antes de los tests
- `:demo:processDebugMainManifest` no puede leer `sdk/android/demo/src/main/AndroidManifest.xml`. No se ejecuta ningún test
  JVM y no hay APK. El AAR (5,5 MB) sí se genera. Es un problema de la rama SDK. La cola del log está en
  `android-cola.log`.

Coste: dos c6a, unos 15 min en total, ≈ 0,05 USD.
