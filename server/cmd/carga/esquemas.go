package main

import (
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"strings"
)

// Esquemas son las preguntas de un esquemas-carga.json y sus lotes con nombre.
type Esquemas struct {
	Preguntas []json.RawMessage // en el orden del fichero; cada una es una pregunta válida del API tal cual
	ids       []string
	Lotes     map[string][]string
}

type preguntaAPI struct {
	ID       string `json:"id"`
	Question string `json:"question"`
	Kind     string `json:"kind"`
	Options  []struct {
		ID          string `json:"id"`
		Description string `json:"description"`
	} `json:"options"`
}

// validarPregunta comprueba a mano lo que pide Question/Option de api/openapi.yaml.
func validarPregunta(p preguntaAPI) error {
	if p.ID == "" || len(p.ID) > 256 {
		return fmt.Errorf("id vacío o de más de 256 bytes")
	}
	if p.Question == "" || len(p.Question) > 4096 {
		return fmt.Errorf("question vacía o de más de 4096 bytes")
	}
	ids := map[string]bool{}
	for _, o := range p.Options {
		if o.ID == "" || len(o.ID) > 256 || len(o.Description) > 4096 {
			return fmt.Errorf("opción %q inválida", o.ID)
		}
		if ids[o.ID] {
			return fmt.Errorf("opción %q repetida", o.ID)
		}
		ids[o.ID] = true
	}
	switch p.Kind {
	case "choice", "score":
		if len(p.Options) < 2 {
			return fmt.Errorf("%s necesita al menos 2 opciones", p.Kind)
		}
	case "noul":
		for id := range ids {
			if id != "true" && id != "false" {
				return fmt.Errorf("noul solo admite las opciones false y true, no %q", id)
			}
		}
	default:
		return fmt.Errorf("kind %q desconocido", p.Kind)
	}
	return nil
}

// cargarEsquemas lee y valida el fichero: preguntas, ids únicos, lotes que apuntan a ids existentes sin repetir.
func cargarEsquemas(path string) (*Esquemas, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var d struct {
		Preguntas []json.RawMessage   `json:"preguntas"`
		Lotes     map[string][]string `json:"lotes"`
	}
	if err := json.Unmarshal(b, &d); err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	if len(d.Preguntas) == 0 {
		return nil, fmt.Errorf("%s: sin preguntas", path)
	}
	e := &Esquemas{Preguntas: d.Preguntas, Lotes: d.Lotes}
	vistos := map[string]bool{}
	for i, raw := range d.Preguntas {
		var p preguntaAPI
		if err := json.Unmarshal(raw, &p); err != nil {
			return nil, fmt.Errorf("%s: pregunta %d: %w", path, i, err)
		}
		if err := validarPregunta(p); err != nil {
			return nil, fmt.Errorf("%s: pregunta %d (%s): %w", path, i, p.ID, err)
		}
		if vistos[p.ID] {
			return nil, fmt.Errorf("%s: id %q repetido", path, p.ID)
		}
		vistos[p.ID] = true
		e.ids = append(e.ids, p.ID)
	}
	for n, ids := range d.Lotes {
		if len(ids) == 0 {
			return nil, fmt.Errorf("%s: lote %q vacío", path, n)
		}
		dentro := map[string]bool{}
		for _, id := range ids {
			if !vistos[id] || dentro[id] {
				return nil, fmt.Errorf("%s: lote %q: id %q desconocido o repetido", path, n, id)
			}
			dentro[id] = true
		}
	}
	return e, nil
}

func (e *Esquemas) nombresLotes() string {
	ns := make([]string, 0, len(e.Lotes))
	for n := range e.Lotes {
		ns = append(ns, n)
	}
	sort.Strings(ns)
	return strings.Join(ns, ", ")
}

func (e *Esquemas) pregunta(id string) json.RawMessage {
	for i, x := range e.ids {
		if x == id {
			return e.Preguntas[i]
		}
	}
	return nil
}

// construirCuerposEsquemas arma un cuerpo por estado. Con nombre, todas las peticiones llevan las
// preguntas de ese lote; sin él, la petición i lleva n preguntas consecutivas del fichero empezando
// en la i-ésima (circular), de modo que rotan junto con los textos. Devuelve también las preguntas por petición.
func construirCuerposEsquemas(e *Esquemas, estados []string, nombre string, n int) ([][]byte, int, error) {
	var fijas []json.RawMessage
	if nombre != "" {
		ids, ok := e.Lotes[nombre]
		if !ok {
			return nil, 0, fmt.Errorf("lote %q no existe; hay: %s", nombre, e.nombresLotes())
		}
		for _, id := range ids {
			fijas = append(fijas, e.pregunta(id))
		}
		n = len(fijas)
	} else if n < 1 || n > len(e.Preguntas) {
		return nil, 0, fmt.Errorf("-lote %d fuera de 1..%d (preguntas del fichero)", n, len(e.Preguntas))
	}
	out := make([][]byte, len(estados))
	for i, s := range estados {
		qs := fijas
		if qs == nil {
			qs = make([]json.RawMessage, n)
			for j := range qs {
				qs[j] = e.Preguntas[(i+j)%len(e.Preguntas)]
			}
		}
		b, err := json.Marshal(struct {
			State     string            `json:"state"`
			Questions []json.RawMessage `json:"questions"`
		}{s, qs})
		if err != nil {
			return nil, 0, err
		}
		out[i] = b
	}
	return out, n, nil
}

// formatoPreguntas imprime las claves "q:<id>/<capa>" de cn como id/capa:n, ordenadas.
func formatoPreguntas(cn map[string]int) string {
	var ks []string
	for k := range cn {
		if strings.HasPrefix(k, "q:") {
			ks = append(ks, k)
		}
	}
	sort.Strings(ks)
	parts := make([]string, len(ks))
	for i, k := range ks {
		parts[i] = fmt.Sprintf("%s:%d", strings.TrimPrefix(k, "q:"), cn[k])
	}
	return strings.Join(parts, ",")
}
