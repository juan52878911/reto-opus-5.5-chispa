package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const ficheroEsquemas = "../../carga/esquemas-carga.json"

func decodificarEstricto(t *testing.T, b []byte) struct {
	State     string        `json:"state"`
	Questions []preguntaAPI `json:"questions"`
} {
	t.Helper()
	var r struct {
		State     string        `json:"state"`
		Questions []preguntaAPI `json:"questions"`
	}
	d := json.NewDecoder(strings.NewReader(string(b)))
	d.DisallowUnknownFields() // DecideRequest e Question tienen additionalProperties:false
	if err := d.Decode(&r); err != nil {
		t.Fatalf("cuerpo inválido: %v\n%s", err, b)
	}
	return r
}

func TestEsquemasFicheroCasaConAPI(t *testing.T) {
	e, err := cargarEsquemas(ficheroEsquemas)
	if err != nil {
		t.Fatal(err)
	}
	if len(e.Preguntas) != 8 {
		t.Fatalf("preguntas=%d", len(e.Preguntas))
	}
	for n, tam := range map[string]int{"uno": 1, "tres": 3, "cinco": 5, "ocho": 8} {
		c, nq, err := construirCuerposEsquemas(e, []string{"hola"}, n, 0)
		if err != nil || nq != tam {
			t.Fatalf("%s: nq=%d err=%v", n, nq, err)
		}
		r := decodificarEstricto(t, c[0])
		if r.State != "hola" || len(r.Questions) != tam {
			t.Fatalf("%s: %+v", n, r)
		}
		vistos := map[string]bool{}
		for _, q := range r.Questions {
			if err := validarPregunta(q); err != nil || vistos[q.ID] {
				t.Fatalf("%s/%s: %v", n, q.ID, err)
			}
			vistos[q.ID] = true
		}
	}
}

func TestEsquemasRotanTextosYPreguntas(t *testing.T) {
	e, _ := cargarEsquemas(ficheroEsquemas)
	c, nq, err := construirCuerposEsquemas(e, []string{"a", "b", "c"}, "", 3)
	if err != nil || nq != 3 || len(c) != 3 {
		t.Fatal(nq, err)
	}
	r0, r1 := decodificarEstricto(t, c[0]), decodificarEstricto(t, c[1])
	if r0.Questions[0].ID == r1.Questions[0].ID || r0.Questions[1].ID != r1.Questions[0].ID {
		t.Fatalf("la ventana no rota: %v %v", r0.Questions, r1.Questions)
	}
	// al final del fichero la ventana da la vuelta sin repetir ids
	c, _, _ = construirCuerposEsquemas(e, make([]string, 8), "", 8)
	r := decodificarEstricto(t, c[5])
	ids := map[string]bool{}
	for _, q := range r.Questions {
		ids[q.ID] = true
	}
	if len(ids) != 8 {
		t.Fatalf("ids repetidos: %v", ids)
	}
}

func TestEsquemasErrores(t *testing.T) {
	e, _ := cargarEsquemas(ficheroEsquemas)
	if _, _, err := construirCuerposEsquemas(e, []string{"x"}, "nope", 1); err == nil || !strings.Contains(err.Error(), "cinco") {
		t.Fatalf("lote inexistente debe listar los que hay: %v", err)
	}
	if _, _, err := construirCuerposEsquemas(e, []string{"x"}, "", 9); err == nil {
		t.Fatal("-lote mayor que las preguntas debe fallar")
	}
	malos := map[string]string{
		"kind":     `{"preguntas":[{"id":"a","question":"q","kind":"x"}],"lotes":{}}`,
		"1opcion":  `{"preguntas":[{"id":"a","question":"q","kind":"choice","options":[{"id":"x"}]}],"lotes":{}}`,
		"noul":     `{"preguntas":[{"id":"a","question":"q","kind":"noul","options":[{"id":"x"}]}],"lotes":{}}`,
		"lote":     `{"preguntas":[{"id":"a","question":"q","kind":"noul"}],"lotes":{"l":["b"]}}`,
		"repetida": `{"preguntas":[{"id":"a","question":"q","kind":"noul"},{"id":"a","question":"q","kind":"noul"}],"lotes":{}}`,
		"vacio":    `{"preguntas":[],"lotes":{}}`,
	}
	for n, s := range malos {
		p := filepath.Join(t.TempDir(), n+".json")
		os.WriteFile(p, []byte(s), 0o644)
		if _, err := cargarEsquemas(p); err == nil {
			t.Errorf("%s: debía fallar", n)
		}
	}
}

func TestCapasPorPregunta(t *testing.T) {
	cn := map[string]int{}
	contarCapas([]byte(`{"results":[{"id":"a","layer":"L1"},{"id":"b","layer":"escalar"},{"id":"a","layer":"L1"}]}`), cn)
	if s := formatoCapas(cn); s != "L1:2,escalar:1" {
		t.Fatal(s)
	}
	if s := formatoPreguntas(cn); s != "a/L1:2,b/escalar:1" {
		t.Fatal(s)
	}
}
