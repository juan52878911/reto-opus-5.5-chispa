package main

import (
	"bytes"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"chispa/format/chispa3"
)

// chispaGrande escribe un .chispa de unos 3000 bytes (una sección L1 de relleno).
func chispaGrande(t *testing.T) string {
	t.Helper()
	var buf bytes.Buffer
	if err := chispa3.Escribir(&buf, []chispa3.Seccion{{Tipo: chispa3.L1, Datos: make([]byte, 3000)}}); err != nil {
		t.Fatal(err)
	}
	ruta := filepath.Join(t.TempDir(), "g.chispa")
	if err := os.WriteFile(ruta, buf.Bytes(), 0o644); err != nil {
		t.Fatal(err)
	}
	return ruta
}

func TestPlanLimitesLlevaMaxFichero(t *testing.T) {
	if got := (&Plan{MaxFichero: 1234}).limites().MaxFichero; got != 1234 {
		t.Errorf("MaxFichero %d, quería 1234", got)
	}
	if got := (&Plan{}).limites().MaxFichero; got != 0 {
		t.Errorf("sin tope debe dejar 0 (1 GiB por defecto): %d", got)
	}
}

func TestEvaluarAbreConElTopeDelPlan(t *testing.T) {
	ruta := chispaGrande(t)
	_, err := evaluar(&Plan{Salida: ruta, MaxFichero: 1000})
	if !errors.Is(err, chispa3.ErrTamano) {
		t.Fatalf("con tope 1000 quería ErrTamano, salió: %v", err)
	}
	_, err = evaluar(&Plan{Salida: ruta, MaxFichero: 1 << 20})
	if errors.Is(err, chispa3.ErrTamano) {
		t.Errorf("con tope 1 MiB no debe fallar por tamaño: %v", err)
	}
}

func TestEntrenarAbreL2ConElTopeDelPlan(t *testing.T) {
	l2 := chispaGrande(t)
	ej := filepath.Join(t.TempDir(), "ej.jsonl")
	if err := os.WriteFile(ej, []byte(`{"text":"hola","label":"a"}`+"\n"+`{"text":"adios","label":"b"}`+"\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	mk := func(tope int64) *Plan {
		p := &Plan{Ejemplos: ej, Salida: filepath.Join(t.TempDir(), "s.chispa"), L2Chispa: l2, SinL0: true, MaxFichero: tope}
		p.Pregunta.Kind = "choice"
		p.Pregunta.Opciones = []opcion{{ID: "a"}, {ID: "b"}}
		return p
	}
	_, err := entrenar(mk(1000))
	if !errors.Is(err, chispa3.ErrTamano) || !strings.Contains(err.Error(), "--l2") {
		t.Fatalf("con tope 1000 quería --l2 + ErrTamano, salió: %v", err)
	}
	_, err = entrenar(mk(1 << 20))
	if errors.Is(err, chispa3.ErrTamano) {
		t.Errorf("con tope 1 MiB el --l2 debe abrir: %v", err)
	}
}
