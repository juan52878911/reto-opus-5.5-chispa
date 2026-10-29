package main

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"math"
	"os"
	"testing"

	"chispa/format/chispa3"
	"github.com/juan52878911/chispa/server/decide"
)

// Paridad exportador ↔ servidor (R9): el fixture es lo que escribe `exportar.esquemas_json` (generado con tests/gen_r9.py).
type fixtureR9 struct {
	Esquemas json.RawMessage `json:"esquemas"`
}

type sesionFalsa struct{ S [][]float32 }

func (s sesionFalsa) Ranuras([]int64) ([][]float32, error) { return s.S, nil }

type tokFalso struct{}

func (tokFalso) IDs(string) []int64 { return []int64{0, 5, 2} }

func cargarR9(t *testing.T) (*chispa3.Esquemas, esquemasJSON) {
	b, err := os.ReadFile("../tests/fixtures/esquemas-r9.json")
	if err != nil {
		t.Fatal(err)
	}
	var f fixtureR9
	if err := json.Unmarshal(b, &f); err != nil {
		t.Fatal(err)
	}
	var j esquemasJSON
	if err := json.Unmarshal(f.Esquemas, &j); err != nil {
		t.Fatal(err)
	}
	sec, err := codificarEsquemas(f.Esquemas)
	if err != nil {
		t.Fatal(err)
	}
	esq, err := chispa3.DecodificarEsquemas(sec)
	if err != nil {
		t.Fatal(err)
	}
	return esq, j
}

func TestR9MultiElServidorEncuentraCadaClave(t *testing.T) {
	esq, j := cargarR9(t)
	n := 0
	for _, e := range j.Entradas {
		if e.Kind != "multi" {
			continue
		}
		n++
		if len(e.Opciones) != 1 {
			t.Fatalf("multi: %d opciones en una entrada", len(e.Opciones))
		}
		o := e.Opciones[0]
		// la misma llamada que hace server/decide (buscarTorre) por cada opción de multi
		if _, _, ok := esq.BuscarEsquema(e.Pregunta, "multi", []chispa3.OpcionClave{{ID: o.ID, Descripcion: o.Description}}); !ok {
			t.Errorf("el servidor no encuentra %q · %q", e.Pregunta, o.ID)
		}
	}
	if n != 3 {
		t.Fatalf("entradas multi = %d, esperaba 3", n)
	}
	// y L2 opina en multi (Conf > 0) con esas claves, sin torres al vuelo
	s := make([]float32, 256)
	s[0] = 1
	l := decide.NuevoL2Con(sesionFalsa{[][]float32{s}}, esq, chispa3.Calib{Tipos: map[string]chispa3.ParamsTipo{"multi": {A: 1, Theta: 0.5}}}, tokFalso{})
	ops := []decide.Opcion{{ID: "precio", Description: "Cuánto cuesta."}, {ID: "envio"}, {ID: "garantia", Description: "Cobertura."}}
	r, err := l.Decidir(context.Background(), decide.Pregunta{Texto: "¿Qué temas toca?", Kind: decide.KindMulti, Opciones: ops})
	if err != nil || r.Conf == 0 || len(r.Probs) != 3 {
		t.Fatalf("multi sin opinión: %+v %v", r, err)
	}
}

// noul: las dos preguntas del fixture (opciones [false,true] y [true,false] al exportar) deben dar en el servidor la
// decisión de la torre de «true», pidan las opciones en el orden que pidan.
func TestR9NoulParidadDeDecision(t *testing.T) {
	esq, j := cargarR9(t)
	vec := map[string][]float64{}
	for _, e := range j.Entradas {
		if e.Kind != "noul" {
			continue
		}
		raw, _ := base64.StdEncoding.DecodeString(e.Vec)
		v := make([]float64, len(raw))
		for i, x := range raw {
			v[i] = float64(int8(x)) * float64(e.Escala)
		}
		vec[e.Pregunta] = v
	}
	if len(vec) != 2 {
		t.Fatalf("noul: %d preguntas", len(vec))
	}
	// S = el vector de la torre de «true» de la pregunta A normalizado: la decisión sólo coincide si ambas guardan «true»
	prm := chispa3.ParamsTipo{T: 1, A: 1, B: -1, Theta: 0.5}
	l := func(S []float32) *decide.L2 {
		return decide.NuevoL2Con(sesionFalsa{[][]float32{S}}, esq, chispa3.Calib{Tipos: map[string]chispa3.ParamsTipo{"noul": prm}}, tokFalso{})
	}
	for preg, v := range vec {
		S := make([]float32, len(v))
		for i := range v {
			S[i] = float32(v[i])
		}
		var s float64
		for i := range v {
			s += v[i] * float64(S[i])
		}
		esperado := 1 / (1 + math.Exp(-(prm.A*math.Log1p(math.Exp(s)) + prm.B)))
		for _, ops := range [][]decide.Opcion{{{ID: "false"}, {ID: "true"}}, {{ID: "true"}, {ID: "false"}}} {
			// la descripción de la petición completa la clave, igual que al exportar
			ops = append([]decide.Opcion(nil), ops...)
			for i := range ops {
				if ops[i].ID == "true" {
					ops[i].Description = "Mensaje no deseado."
				} else {
					ops[i].Description = "Mensaje legítimo."
				}
			}
			r, err := l(S).Decidir(context.Background(), decide.Pregunta{Texto: preg, Kind: decide.KindNoul, Opciones: ops})
			if err != nil || r.Conf == 0 {
				t.Fatalf("%q %v: %+v %v", preg, ops, r, err)
			}
			if math.Abs(r.Probs["true"]-esperado) > 1e-6 {
				t.Errorf("%q con opciones %v: p(true) = %v, esperaba %v (torre de true)", preg, ops, r.Probs["true"], esperado)
			}
		}
	}
}
