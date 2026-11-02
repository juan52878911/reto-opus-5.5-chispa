# «Chispa: Caída» en el servidor local (i7, CT 109 `kling-pve`, 4 núcleos y 4 GB), 2026-11-02

- **Binario:** `chispa-server` linux/amd64 con ORT 1.31.1, del tar de la otra sesión (`64047d99…`). Cliente `demos/caida`.
- **Modelos:**
  - `servidor/`: **el de servidor del ajuste 1**, fp32 sin poda, L0 + L2 + TORR + CALIB, 945 MB. **No lleva L1**, porque con
    potion pasaba de 1 GiB de `format/chispa3`.
  - `fp16/`: el perfil móvil fp16 con poda (332 MB, con L1), solo como referencia.

## Latencia: una petición de 3 preguntas, cliente en serie

| modelo | caché de torres | p50 | p95 | p99 | decisiones/s |
|---|---|---|---|---|---|
| servidor fp32 | fría | 290 ms | 340 ms | 386 ms | 3,4 |
| servidor fp32 | caliente | 58 ms | 66 ms | 129 ms | 16,4 |
| móvil fp16 | fría | 316 ms | 371 ms | 407 ms | 3,1 |
| móvil fp16 | caliente | 63 ms | 70 ms | 79 ms | 15,4 |

- **ms por torre e5 en el i7** ≈ (fría − caliente) / unas 18 torres nuevas por petición:
  - **≈ 13 ms/torre en fp32**, ≈ 77 torres/s por núcleo ocupado;
  - ≈ 14 ms/torre en fp16, porque fp16 no se acelera en esta CPU.

## Partidas: 20 por agente, tope de 150 piezas, `--decidir tau` (el defecto actual)

| agente | piezas | filas | puntos | escudo | p50 / p99 por decisión |
|---|---|---|---|---|---|
| aleatorio | 21,6 | 0,05 | 236 | — | 0,08 / 0,25 ms |
| profesor | 117,3 | 23,4 | 4702 | — | 0,5 / 1,1 ms |
| Chispa zero-shot (servidor) | 117,3 | 23,4 | 4702 | **100 %** | 69 / 269 ms |
| Chispa few-shot | igual | igual | igual | **100 %** | 69 / 85 ms |

**Chispa no decide ninguna jugada**, porque todas escalan: `tau_escalate_l2` = 0,93, con preguntas nuevas de opciones casi
iguales. El escudo (el profesor) las juega todas, y por eso las cifras coinciden con las del profesor.
- La «few-shot» de esta tabla **no es un `.chispa` few-shot**: todavía no hay entrenador Go en el CT. Llega en el tar de CD2.
- CD2 añade `--decidir argmax`, que juega el argmax bajo τ y lo separa en la traza.

**Vídeo:** `~/Documents/chispa-caida/caida-zeroshot-servidor-i7.mp4`, 90 s, 1080p y 30 fps, renderizado en el Mac (excepción
aprobada por Juan). Muestra al escudo, no a Chispa: hay que repetirlo con CD2.

## Con CD2 y `--decidir argmax` (Chispa juega su argmax aunque escale)
Modelo de servidor fp32, 20 partidas por agente, 2 peticiones por turno (choice por un lado; score y noul por otro):

| agente | piezas | filas | puntos | coincide con el profesor | p50 / p99 por decisión |
|---|---|---|---|---|---|
| aleatorio | 21,6 | 0,05 | 236 | 11,1 % | 0,08 / 0,2 ms |
| **Chispa zero-shot** | **40,9** | **3,0** | **882** | **28,2 %** | 185 / 347 ms |
| profesor | 117,3 | 23,4 | 4702 | 100 % | 0,5 / 1,0 ms |

- 805 decisiones de Chispa, todas bajo τ (escalaría) y ninguna de escudo.
- **Latencia aislada:** fría p50 390 ms (2,5 decisiones/s) y caliente 87 ms (11,1 decisiones/s).
- **Vídeo:** `~/Documents/chispa-caida/caida-zeroshot-argmax-i7.mp4`, 21 s, partida de 35 piezas.
- **Few-shot pendiente:**
  - los tres `.chispa` solo L0 se entrenan en el CT con el entrenador estático, que funciona;
  - pero `chispa-server` no los acepta como `modelos` de la config: «checksum mismatch»;
  - cómo servirlo es una pregunta abierta a la otra sesión.
