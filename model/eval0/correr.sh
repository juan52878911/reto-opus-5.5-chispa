#!/bin/bash
# Uso: N1=120 N4=30 correr.sh <script.py> [args extra]. 4 tareas: 1 hilo (N1 ejemplos, 0 = todo) y 4 hilos (N4, 0 = omitir). Un proceso a la vez.
source ~/.profile
s=$1; shift
for t in intencion toxicidad whatsapp_comercio herramientas; do
  python $s --tarea $t --hilos 1 --n ${N1:-0} "$@" 2>&1 | tail -1 >> out/log.txt
  [ "${N4:-0}" != 0 ] && python $s --tarea $t --hilos 4 --n $N4 "$@" 2>&1 | tail -1 >> out/log.txt
done
