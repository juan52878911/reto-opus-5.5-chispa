package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"strings"

	"github.com/juan52878911/kindling/pkg/chispa"
)

type opcion struct {
	ID          string `json:"id"`
	Description string `json:"description"`
}

type pregunta struct {
	ID       string   `json:"id"`
	Texto    string   `json:"texto"`
	Kind     string   `json:"kind"` // choice | noul | score
	Opciones []opcion `json:"opciones"`
}

// Plan es lo que Python pasa al entrenador.
type Plan struct {
	Ejemplos  string   `json:"ejemplos"` // JSONL {"text","label"}
	Prueba    string   `json:"prueba"`   // idem, solo para `evaluar`
	Pregunta  pregunta `json:"pregunta"`
	L1        string   `json:"l1"`        // .chispa-l1; vacío = sin L1
	L2Chispa  string   `json:"l2_chispa"` // .chispa v3 de model/l2/exportar.py: de aquí salen L2 y ESQUEMAS; vacío = sin L2
	Meta      Meta     `json:"meta"`
	Salida    string   `json:"salida"`
	Semilla   uint64   `json:"semilla"`
	FracValid float64  `json:"frac_valid"`    // 0,2 por defecto
	TauL0     float64  `json:"tau_l0"`        // τ de L0 en `evaluar` (el servidor lo toma de su config): 0,8
	TauObj    float64  `json:"tau_precision"` // precisión objetivo de τ de escalate: 0,95
}

type Meta struct {
	Version   int               `json:"version"`
	Tareas    []string          `json:"tareas"`
	Licencias map[string]string `json:"licencias"`
	Dorado    string            `json:"dorado"`
}

func leerPlan(ruta string) (*Plan, error) {
	b, err := os.ReadFile(ruta)
	if err != nil {
		return nil, err
	}
	var p Plan
	d := json.NewDecoder(bytes.NewReader(b))
	d.DisallowUnknownFields()
	if err := d.Decode(&p); err != nil {
		return nil, fmt.Errorf("%s: %w", ruta, err)
	}
	if p.FracValid <= 0 || p.FracValid >= 1 {
		p.FracValid = 0.2
	}
	if p.TauObj <= 0 || p.TauObj > 1 {
		p.TauObj = 0.95
	}
	if p.TauL0 <= 0 || p.TauL0 > 1 {
		p.TauL0 = 0.8
	}
	if p.Semilla == 0 {
		p.Semilla = 1
	}
	if p.Meta.Version < 1 {
		p.Meta.Version = 1
	}
	if p.Meta.Tareas == nil {
		p.Meta.Tareas = []string{p.Pregunta.ID}
	}
	if p.Meta.Licencias == nil {
		p.Meta.Licencias = map[string]string{}
	}
	if len(p.Pregunta.Opciones) < 2 {
		return nil, fmt.Errorf("la pregunta necesita ≥ 2 opciones")
	}
	return &p, nil
}

func leerEjemplos(ruta string, ids []string) ([]chispa.Example, error) {
	ok := map[string]bool{}
	for _, i := range ids {
		ok[i] = true
	}
	f, err := os.Open(ruta)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	var out []chispa.Example
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 1<<20), 1<<24)
	for n := 1; sc.Scan(); n++ {
		if strings.TrimSpace(sc.Text()) == "" {
			continue
		}
		var e struct {
			Text  string `json:"text"`
			Label string `json:"label"`
		}
		if err := json.Unmarshal(sc.Bytes(), &e); err != nil {
			return nil, fmt.Errorf("%s:%d: %w", ruta, n, err)
		}
		if !ok[e.Label] {
			return nil, fmt.Errorf("%s:%d: etiqueta %q no es una opción", ruta, n, e.Label)
		}
		out = append(out, chispa.Example{Text: e.Text, Label: e.Label})
	}
	return out, sc.Err()
}

func idsDe(p pregunta) []string {
	ids := make([]string, len(p.Opciones))
	for i, o := range p.Opciones {
		ids[i] = o.ID
	}
	return ids
}

// textoOpcion es el de server/decide/l1.go: «pregunta · opción · descripción».
func textoOpcion(p pregunta, o opcion) string {
	s := []string{p.Texto, o.ID}
	if o.Description != "" {
		s = append(s, o.Description)
	}
	return strings.Join(s, " · ")
}
