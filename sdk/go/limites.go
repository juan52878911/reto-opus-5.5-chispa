package chispa

import (
	"fmt"
	"strings"
	"unicode/utf8"
)

// Limites son los topes del servidor (sección `limites` de su config), en BYTES UTF-8 como los cuenta él, no en caracteres.
type Limites struct {
	MaxEstado    int
	MaxPreguntas int
	MaxID        int
	MaxTexto     int
	MaxOpciones  int
	MaxCuerpo    int
}

// LimitesPorDefecto son los valores por defecto de server/api/openapi.yaml.
func LimitesPorDefecto() Limites {
	return Limites{MaxEstado: 262144, MaxPreguntas: 256, MaxID: 256, MaxTexto: 4096, MaxOpciones: 256, MaxCuerpo: 1 << 20}
}

// lon son los bytes que de verdad se envían: json.Encoder cambia cada byte UTF-8 inválido por U+FFFD (3 bytes).
func lon(s string) int {
	n := 0
	for i := 0; i < len(s); {
		r, w := utf8.DecodeRuneInString(s[i:])
		if r == utf8.RuneError && w == 1 {
			n += 3
		} else {
			n += w
		}
		i += w
	}
	return n
}

// validar comprueba la petición como el servidor (todo o nada, mismos códigos). Devuelve *ErrorChispa con Status 0.
func (l Limites) validar(estado string, qs []Pregunta) *ErrorChispa {
	if lon(estado) > l.MaxEstado {
		return falla("state_too_long", fmt.Sprintf("state: %d bytes, máximo %d", lon(estado), l.MaxEstado), "")
	}
	if len(qs) == 0 {
		return falla("empty_questions", "questions: hace falta al menos una pregunta", "")
	}
	if len(qs) > l.MaxPreguntas {
		return falla("too_many_questions", fmt.Sprintf("questions: %d, máximo %d", len(qs), l.MaxPreguntas), "")
	}
	vistos := map[string]bool{}
	for i, q := range qs {
		r := fmt.Sprintf("questions[%d]", i)
		if q.ID == "" {
			return falla("missing_id", r+".id: obligatorio", "")
		}
		if lon(q.ID) > l.MaxID {
			return falla("field_too_long", fmt.Sprintf("%s.id: %d bytes, máximo %d", r, lon(q.ID), l.MaxID), q.ID)
		}
		if vistos[q.ID] {
			return falla("duplicate_question_id", fmt.Sprintf("%s.id: %q repetido", r, q.ID), q.ID)
		}
		vistos[q.ID] = true
		if q.Texto == "" {
			return falla("missing_question", r+".question: obligatorio", q.ID)
		}
		if lon(q.Texto) > l.MaxTexto {
			return falla("field_too_long", fmt.Sprintf("%s.question: %d bytes, máximo %d", r, lon(q.Texto), l.MaxTexto), q.ID)
		}
		if tieneSeparador(q.Texto) {
			return falla("invalid_characters", r+".question: no admite los caracteres de control U+001D–U+001F", q.ID)
		}
		if q.Kind == "" {
			return falla("missing_kind", r+".kind: obligatorio", q.ID)
		}
		if q.Kind != KindChoice && q.Kind != KindScore && q.Kind != KindNoul && q.Kind != KindMulti {
			return falla("invalid_kind", fmt.Sprintf("%s.kind: %q no válido (choice, score, noul o multi)", r, q.Kind), q.ID)
		}
		if lon(q.Nonce) > l.MaxID {
			return falla("field_too_long", fmt.Sprintf("%s.nonce: %d bytes, máximo %d", r, lon(q.Nonce), l.MaxID), q.ID)
		}
		if e := l.validarOpciones(q, r); e != nil {
			return e
		}
	}
	return nil
}

func (l Limites) validarOpciones(q Pregunta, r string) *ErrorChispa {
	ops := q.Opciones
	if q.Kind != KindNoul && len(ops) < 2 {
		return falla("too_few_options", fmt.Sprintf("%s.options: %s necesita al menos 2 opciones", r, q.Kind), q.ID)
	}
	// como el servidor: noul admite 0 opciones o exactamente {false, true}
	if q.Kind == KindNoul && len(ops) != 0 {
		ok := len(ops) == 2 && (ops[0].ID == "true" && ops[1].ID == "false" || ops[0].ID == "false" && ops[1].ID == "true")
		if !ok {
			return falla("invalid_options", r+`.options: noul solo admite los ids "false" y "true"`, q.ID)
		}
	}
	if len(ops) > l.MaxOpciones {
		return falla("too_many_options", fmt.Sprintf("%s.options: %d, máximo %d", r, len(ops), l.MaxOpciones), q.ID)
	}
	vistas := map[string]bool{}
	for j, o := range ops {
		ro := fmt.Sprintf("%s.options[%d]", r, j)
		if o.ID == "" {
			return falla("missing_option_id", ro+".id: obligatorio", q.ID)
		}
		if lon(o.ID) > l.MaxID {
			return falla("field_too_long", fmt.Sprintf("%s.id: %d bytes, máximo %d", ro, lon(o.ID), l.MaxID), q.ID)
		}
		if lon(o.Description) > l.MaxTexto {
			return falla("field_too_long", fmt.Sprintf("%s.description: %d bytes, máximo %d", ro, lon(o.Description), l.MaxTexto), q.ID)
		}
		if tieneSeparador(o.ID) {
			return falla("invalid_characters", ro+".id: no admite los caracteres de control U+001D–U+001F", q.ID)
		}
		if tieneSeparador(o.Description) {
			return falla("invalid_characters", ro+".description: no admite los caracteres de control U+001D–U+001F", q.ID)
		}
		if vistas[o.ID] {
			return falla("duplicate_option_id", fmt.Sprintf("%s.id: %q repetido", ro, o.ID), q.ID)
		}
		vistas[o.ID] = true
	}
	return nil
}

// tieneSeparador dice si s trae U+001D–U+001F, los separadores de HashEsquema2; el servidor los rechaza con invalid_characters.
func tieneSeparador(s string) bool { return strings.ContainsAny(s, "\x1d\x1e\x1f") }
