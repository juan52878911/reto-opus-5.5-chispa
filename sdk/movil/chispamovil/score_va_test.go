package chispamovil

import (
	"encoding/json"
	"fmt"
	"math"
	"os"
	"testing"

	"chispa/format/chispa3"
)

// score: el orden de las opciones en la petición no cambia la respuesta (se ordenan por id numérico antes de CORAL).
func TestScoreOrdenDeOpcionesNoCambiaRespuesta(t *testing.T) {
	c := &Chispa{calib: calibCoral()}
	dec := func(ids ...string) respuesta {
		var ops []opcion
		for _, id := range ids {
			ops = append(ops, opcion{ID: id})
		}
		return c.score(pregunta{Kind: "score", Opciones: ops}, sCero)
	}
	want := dec("1", "2", "3")
	if want.Answer != "2" {
		t.Fatalf("referencia: %+v", want)
	}
	for _, ids := range [][]string{{"3", "2", "1"}, {"2", "3", "1"}, {"1", "3", "2"}} {
		got := dec(ids...)
		if got.Answer != want.Answer || math.Abs(got.Conf-want.Conf) > 1e-12 {
			t.Fatalf("orden %v: %+v ≠ %+v", ids, got, want)
		}
		for id, p := range want.Probs {
			if math.Abs(got.Probs[id]-p) > 1e-12 {
				t.Fatalf("orden %v: prob %s", ids, id)
			}
		}
	}
	if r := dec("1", "2", "4"); r.Opina {
		t.Fatalf("ids que no son 1..K no deben opinar: %+v", r)
	}
}

func opsIDs(ids ...string) []opcion {
	var ops []opcion
	for _, id := range ids {
		ops = append(ops, opcion{ID: id})
	}
	return ops
}

func calibNiveles(K int) chispa3.Calib {
	t := map[string]chispa3.ParamsTipo{fmt.Sprintf("score%d", K): {T: 1, A: 2, B: 0, Theta: 0.5}}
	for j := 1; j < K-1; j++ {
		t[fmt.Sprintf("score%d#%d", K, j)] = chispa3.ParamsTipo{A: 0.4}
	}
	return chispa3.Calib{TauEscalate: 0.5, Tipos: t}
}

// score con 12 niveles: cualquier permutación (incluido "10" < "2" lexicográfico) da lo mismo que 1..12.
func TestScoreDocePermutado(t *testing.T) {
	var base []string
	for i := 1; i <= 12; i++ {
		base = append(base, fmt.Sprint(i))
	}
	perm := []string{"10", "2", "12", "1", "7", "3", "11", "5", "9", "4", "8", "6"}
	c := &Chispa{calib: calibNiveles(12)}
	want := c.score(pregunta{Kind: "score", Opciones: opsIDs(base...)}, 1)
	got := c.score(pregunta{Kind: "score", Opciones: opsIDs(perm...)}, 1)
	if want.Conf == 0 || got.Answer != want.Answer || math.Abs(got.Conf-want.Conf) > 1e-12 || len(got.Probs) != 12 {
		t.Fatalf("12 niveles permutados: %+v ≠ %+v", got, want)
	}
}

// ids no 1..K (bajo/medio/alto, 0..K-1…): L2 no opina y dice por qué.
func TestScoreNoNumericosNoOpina(t *testing.T) {
	c := &Chispa{calib: calibNiveles(3)}
	for _, ids := range [][]string{{"bajo", "medio", "alto"}, {"0", "1", "2"}, {"01", "2", "3"}} {
		r := c.score(pregunta{Kind: "score", Opciones: opsIDs(ids...)}, 1)
		if r.Opina || r.Conf != 0 || r.EscalateReason != "score_ids_no_validos" {
			t.Fatalf("%v: %+v", ids, r)
		}
	}
}

// Paridad con model/l2/modelo.py (server/decide/testdata/gen_score_orden.py → score_orden.json).
func TestScoreParidadPythonOrden(t *testing.T) {
	b, err := os.ReadFile("../../../server/decide/testdata/score_orden.json")
	if err != nil {
		t.Fatal(err)
	}
	var casos []struct {
		Caso     string   `json:"caso"`
		Opciones []string `json:"opciones"`
		Consulta string   `json:"consulta"`
		Error    bool     `json:"error"`
	}
	if err := json.Unmarshal(b, &casos); err != nil || len(casos) == 0 {
		t.Fatal(err)
	}
	for _, c := range casos {
		ops := opsIDs(c.Opciones...)
		orden, num := ordenNivel(ops)
		if c.Error {
			if num {
				t.Fatalf("%s: Python rechaza y aquí vale", c.Caso)
			}
			continue
		}
		if got := opcionesConsulta(pregunta{Kind: "score", Opciones: ops})[0].ID; !num || got != c.Consulta || orden[len(orden)-1].ID != c.Consulta || orden[0].ID != "1" {
			t.Fatalf("%s: torre %q, Python %q, orden %v", c.Caso, got, c.Consulta, orden)
		}
	}
}
