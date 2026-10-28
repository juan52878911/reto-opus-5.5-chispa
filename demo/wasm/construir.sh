#!/bin/sh
# Compila chispa.wasm y (si hay modelo y vocabulario) genera potion-es.chispa-l1. Ver README.md.
set -e
cd "$(dirname "$0")"
GOOS=js GOARCH=wasm go build -o chispa.wasm .
ls -l chispa.wasm
