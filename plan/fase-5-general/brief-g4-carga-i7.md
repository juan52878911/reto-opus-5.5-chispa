# G.4 Prueba de carga en el i7-8700T: ≥ 5 k decisiones/s con L1 y ≥ 300/s con L2

## Antecedentes
La salida de la fase 4 pide una prueba de carga en el i7 con al menos 5 k decisiones/s con L1 y 300/s con L2. Hasta ahora:
- servidor: `server/` (`cmd/chispa-server`, `cmd/carga`);
- medidas sueltas: 15,9 k decisiones/s en la VM de kindling sin L2, L1 a 166 µs y e5 int8 a 30,6 ms de p99 en el i7
  (`model/bench/i7/resultados.md`), y L2c a ~10 ms de p99 en una c6a (`server/deploy/resultados/e2e-20261028-l0tf/`).

Este nodo es una microVM en el host pve (i7-8700T, 4 GB) y solo se usa para medir.

## Hipótesis
En el i7, con 4 hilos:
- `chispa-server` sirve ≥ 5.000 decisiones/s con L0 + L1, con un p99 < 20 ms;
- sirve ≥ 300 decisiones/s con L2 forzado, el codificador e5 int8 en cada petición.

Se refuta midiendo.

## Terminado cuando
- `model/bench/carga/` (tu zona) contiene:
  - un script que arma los `.chispa` de prueba **dentro de la VM**:
    - L0 + L1 con `chispa train` sobre los datos del golden (`~/datos`, massive);
    - L2 con `model/l2/exportar.py` sobre e5 de `~/hf` y una cabeza **con pesos aleatorios y semilla fija**. La latencia no
      depende de los pesos y aquí no hay S3 para el checkpoint real. Dilo en el informe;
  - el tokenizador de e5 exportado con `runtime/tok/exportar.py`;
  - `chispa-server` compilado con `-tags ort`, si hay ORT en la VM. Si no lo hay, L2 queda en stub: mide solo L0 + L1 y
    dilo;
  - la carga con `server/cmd/carga`, sin cambiarlo: concurrencia 1, 4, 16 y 64, 30 s por punto, mensajes reales de
    massive y modos L0/L1 y L2 forzado;
  - el entorno: CPU, loadavg antes y durante, y la versión de ORT.
- `model/bench/carga/resultados-i7.md`: tabla de decisiones/s y p50/p99 por modo y concurrencia frente a los objetivos, y
  la variación entre 3 tandas, porque el host es compartido.
- No cambies `server/` ni `sdk/`: son de otra sesión. Si `cmd/carga` o el servidor necesitan un cambio, descríbelo en el
  informe.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `model/bench/carga/**`.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Go en `~/go-sdk/bin`, Python en `~/venv`, modelos en `~/hf` y datos en `~/datos`. Sin red salvo la
  API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 90 min de reloj · ≤ 5 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 10 líneas:
- rama y sha;
- la tabla resumida frente a los objetivos;
- qué no se pudo medir.
