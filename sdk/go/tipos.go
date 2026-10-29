package chispa

import "encoding/json"

// Tipos de la API de POST /v1/decide (server/api/openapi.yaml). Están copiados a mano: el cliente no importa el servidor.

const (
	KindChoice = "choice"
	KindScore  = "score"
	KindNoul   = "noul"
	// KindMulti es multietiqueta: cada opción es un sí/no independiente; Resultado.Answers trae las activas.
	KindMulti = "multi"
)

// Opcion es una opción de respuesta. En zero-shot, Description es lo único que Chispa ve de ella.
type Opcion struct {
	ID          string `json:"id"`
	Description string `json:"description,omitempty"`
}

// Pregunta es una pregunta tipada. Nonce es opcional: Decidir pone uno a las que no lo traen.
type Pregunta struct {
	ID       string   `json:"id"`
	Texto    string   `json:"question"`
	Kind     string   `json:"kind"`
	Opciones []Opcion `json:"options,omitempty"`
	Nonce    string   `json:"nonce,omitempty"`
}

// Resultado es la respuesta a una pregunta. Answer va vacío si ninguna capa opinó; Escalate es true si ninguna llegó a su tau
// (entonces Layer vale "escalar"). Probs trae una probabilidad por opción: suman 1 en choice, score y noul; en multi cada opción lleva
// la suya (en [0,1], no suman 1). Answers solo viene en multi: las opciones activas, en el orden de la pregunta (vacía si ninguna);
// Answer es entonces la activa de mayor probabilidad.
type Resultado struct {
	ID       string             `json:"id"`
	Kind     string             `json:"kind"`
	Answer   string             `json:"answer"`
	Answers  []string           `json:"answers,omitempty"`
	Probs    map[string]float64 `json:"probs"`
	Layer    string             `json:"layer"`
	Escalate bool               `json:"escalate"`
	MS       float64            `json:"ms"`
	Nonce    string             `json:"nonce,omitempty"`
}

type peticion struct {
	State     string     `json:"state"`
	Questions []Pregunta `json:"questions"`
}

type respuesta struct {
	Results []Resultado `json:"results"`
}

type cuerpoError struct {
	Error json.RawMessage `json:"error"`
}
