// Package decide implementa el servidor de decisiones de Chispa: una cascada
// de capas (L0..L3) detrás de POST /v1/decide.
package decide

import (
	"context"
	"encoding/hex"
	"hash/fnv"
	"sort"
)

const (
	KindChoice = "choice"
	KindScore  = "score"
	KindNoul   = "noul"
)

type Opcion struct {
	ID          string `json:"id"`
	Description string `json:"description,omitempty"`
}

// Pregunta es una pregunta ya validada. Estado es el texto que se clasifica.
type Pregunta struct {
	ID       string   `json:"id"`
	Estado   string   `json:"-"`
	Texto    string   `json:"question"`
	Kind     string   `json:"kind"`
	Opciones []Opcion `json:"options"`
	Nonce    string   `json:"nonce,omitempty"`
}

// Respuesta de una capa. Conf es la confianza top-1; 0 significa «sin opinión».
type Respuesta struct {
	Answer string
	Probs  map[string]float64
	Conf   float64
}

// Decisor es una capa de la cascada.
type Decisor interface {
	Decidir(ctx context.Context, p Pregunta) (Respuesta, error)
	Nombre() string
}

// ClaveEsquema es el hash estable de question + options (ordenadas por id,
// así que el orden de las opciones no cambia la clave).
func ClaveEsquema(p Pregunta) string {
	ops := append([]Opcion(nil), p.Opciones...)
	sort.Slice(ops, func(i, j int) bool { return ops[i].ID < ops[j].ID })
	h := fnv.New128a()
	w := func(s string) {
		var n [4]byte
		n[0], n[1], n[2], n[3] = byte(len(s)>>24), byte(len(s)>>16), byte(len(s)>>8), byte(len(s))
		h.Write(n[:])
		h.Write([]byte(s))
	}
	w(p.Kind)
	w(p.Texto)
	for _, o := range ops {
		w(o.ID)
		w(o.Description)
	}
	return hex.EncodeToString(h.Sum(nil))
}
