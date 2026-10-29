# Datos y consentimiento del piloto

> **Esto no es asesoría legal.** Es una lista de verificación de trabajo. La empresa debe validarla con su oficial de protección de datos o su abogado,
> y con la Superintendencia de Industria y Comercio (SIC) si tiene dudas. Si hay datos de salud (EPS) o de menores, las reglas son más estrictas.

Normas de referencia (habeas data en Colombia): **Ley 1581 de 2012** (régimen general de protección de datos personales) y **Decreto 1377 de 2013**
(reglamenta parcialmente la ley: autorización, aviso de privacidad, políticas de tratamiento). Los datos de salud son **datos sensibles** (art. 5 de la Ley 1581):
su tratamiento requiere autorización explícita y se puede negar. Verifique la versión vigente de las normas y de sus compilaciones (el Decreto 1377 de 2013
quedó incorporado en el Decreto Único 1074 de 2015); no se verificó aquí ningún texto.

## 1. Qué se recoge
- [ ] Solo el **texto del mensaje** (y, si hace falta medir, la etiqueta que le pone una persona). Nada más.
- [ ] Una lista escrita de los campos que **no** se recogen: nombre, cédula, correo, teléfono, dirección, número de afiliado o de pedido, diagnósticos, datos de tarjetas.
- [ ] Una muestra de evaluación de ≥ 300 mensajes ([`metrica.md`](metrica.md#tamaño-de-la-muestra)), elegida al azar en un periodo, no «los que se ven bien».
- [ ] Un conjunto aparte de ejemplos para few-shot (pocos por opción), distinto de la muestra de evaluación, para no medir con lo que se entrenó.

## 2. Anonimización (antes de que el texto salga de la base del cliente)
- [ ] Quitar o reemplazar nombres, cédulas, NIT, correos, teléfonos, direcciones, números de afiliación, de pedido, de cuenta y de tarjeta. Ejemplo: `[NOMBRE]`, `[CEDULA]`.
- [ ] Revisar a mano una muestra del resultado (p. ej. 50 mensajes): las expresiones regulares fallan con textos libres.
- [ ] Quitar diagnósticos, medicamentos con nombre del paciente y todo dato sensible que no cambie la clasificación.
- [ ] Guardar la tabla de reemplazos (si existe) **solo en el cliente**, separada del texto anonimizado.
- [ ] Decidir si el texto anonimizado sigue siendo dato personal: si se puede reidentificar con otra información del cliente, **sigue siéndolo** y aplica todo lo demás.
- Chispa **no anonimiza**: no tiene esa función. Lo hace el cliente antes de llamar a `/v1/decide` ([`README.md`](README.md#pendiente-de-producto), punto 7).

## 3. Dónde viven los datos
| Dato | Dónde | Sale del cliente |
|---|---|---|
| Mensajes originales con datos personales | Sistemas del cliente | **No** |
| Tabla de reemplazos de la anonimización | Sistemas del cliente | **No** |
| Muestra etiquetada (texto anonimizado + etiqueta) | Sistemas del cliente | **No** (el informe lleva solo métricas agregadas) |
| `.chispa` entrenados con ejemplos del cliente | Servidor del cliente | Solo si el cliente lo autoriza por escrito: contiene información derivada de sus ejemplos |
| Servidor `chispa-server` | On-prem o nube del cliente, con red controlada | No hay llamadas a servicios externos |
| Informe final | Cliente y equipo de Chispa | Métricas agregadas; ningún texto |

- [ ] Si el servidor está en una nube, anotar el país de la región: si los datos pasan a otro país, aplica el régimen de **transferencia y transmisión** de la Ley 1581 (art. 26 y Decreto 1377); verifíquelo con su asesor.
- [ ] Estas afirmaciones de «no sale» las cumple el cliente con su red y sus permisos. El producto no las impone.
- Lo que sí se sabe del producto: el servidor corre en CPU, sin GPU, y por sí mismo no tiene una opción de enviar datos a terceros ([`main.go`](../server/cmd/chispa-server/main.go): solo `-addr`, `-config`, `-modelo`, `-tok`).
  El único registro que conserva es el de métricas agregadas en `/metrics` (contadores) y una caché de respuestas por `nonce` en memoria. No se ha auditado el log del servidor con datos reales: sin verificar.

## 4. Retención
- [ ] Definir cuánto tiempo se guarda cada cosa. Propuesta de partida, a ajustar por el cliente: muestra etiquetada hasta el informe final + 30 días; tabla de reemplazos mientras dure la muestra; logs sin texto.
- [ ] Un responsable y una fecha para borrar, y una constancia de borrado al final del piloto.
- [ ] Al terminar: borrar la muestra y los `.chispa` entrenados con datos del cliente, o conservarlos solo si hay una autorización nueva (finalidad distinta = autorización distinta).
- [ ] Una caché por `nonce` vive en memoria del proceso: reiniciar el servidor la vacía.

## 5. Consentimiento (habeas data)
- [ ] **Finalidad:** el aviso de privacidad o la política de tratamiento del cliente ya cubre «mejorar la atención y clasificar solicitudes con herramientas automáticas». Si no la cubre, hace falta una autorización nueva o usar solo datos anonimizados de forma irreversible. Un asesor decide cuál.
- [ ] **Autorización previa, expresa e informada** del titular (Ley 1581, art. 9; Decreto 1377, arts. 5–7), conservada como prueba. Verifique la numeración actual.
- [ ] **Datos sensibles** (salud, etc.): autorización explícita y aviso de que no está obligado a darla (Ley 1581, art. 6).
- [ ] **Menores:** solo con respeto del interés superior y autorización de sus representantes; mejor excluirlos del piloto.
- [ ] **Encargado del tratamiento:** si el equipo de Chispa ve texto real, hay una relación de encargado y se necesita un contrato o cláusula de transmisión (Decreto 1377). Si el equipo de Chispa no ve texto (el cliente corre todo), anótelo.
- [ ] **Derechos de los titulares** (consultar, actualizar, rectificar, suprimir, revocar): el canal ya existe y el piloto no lo bloquea. Si el titular pide suprimir su dato, se borra también de la muestra.
- [ ] **Decisiones automáticas:** durante el piloto una persona sigue decidiendo (modo sombra, [guía](guia-integracion.md#6-conectar-su-sistema)); Chispa no decide solo sobre derechos de nadie.
- [ ] **Registro Nacional de Bases de Datos (RNBD):** el cliente revisa si el piloto crea o cambia una base que deba registrarse.
- [ ] **Seguridad:** acceso por rol a la muestra, cifrado en reposo y en tránsito (TLS en un proxy del cliente, [guía](guia-integracion.md#seguridad-de-red-pendiente-del-lado-del-cliente)), registro de quién accede.

## 6. Qué no sale del cliente (resumen)
Mensajes originales, datos personales, tabla de reemplazos, la muestra etiquetada y los modelos entrenados con sus ejemplos. Al equipo de Chispa solo llegan, por escrito y si el cliente lo permite:
las métricas del piloto y los textos anonimizados que el cliente decida compartir para ajustar descripciones.

## Firmas
Responsable de datos del cliente: ______  Patrocinador: ______  Equipo de Chispa: ______  Fecha: ______
