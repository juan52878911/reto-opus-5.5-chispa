# Etiquetado humano

Para quien etiqueta: no necesita internet ni instalar nada.

1. Abre `etiquetar.html` con doble clic (Chrome o Firefox).
2. Escribe tu nombre (siempre el mismo, para que el orden y tu progreso se mantengan) y elige el fichero `.jsonl` que te hayan pasado.
3. Lee la pregunta y el texto; elige la opción que mejor encaje según su descripción.
4. Atajos: `1`-`9` elige la opción (y pasa a la siguiente) · `←` `→` navegan · `e` = escalate (si la fila lo permite) · `?` marca la fila como dudosa.
5. El progreso se guarda solo en tu navegador: si recargas, sigues donde lo dejaste. No uses ventana privada ni borres los datos del navegador.
6. Al terminar (o cuando quieras parar) pulsa **Exportar JSONL**. Entrega el fichero `etiquetas_<tu nombre>.jsonl`.

Reglas: etiqueta por tu cuenta, sin consultar a la otra persona ni al modelo; en la duda, elige lo más probable y marca `?`.

## Para quien prepara y mide

```
python -m model.etiquetado.preparar --entrada a.jsonl b.jsonl --por-tarea 300 --semilla 7 --salida muestra.jsonl
python -m model.etiquetado.acuerdo --a ana.jsonl --b luis.jsonl --oro muestra.jsonl --salida adjudicado.jsonl
```
`preparar` toma solo `split: test`, estratificado por clase, y excluye `uso_comercial: false` salvo `--incluir-no-comercial`.
`acuerdo` imprime κ por tarea y global, confusión, acuerdo con la etiqueta original y discrepancias; el adjudicado usa mayoría
(el original desempata) o marca `conflicto`. Tests: `python -m unittest discover -s model -t .`.
