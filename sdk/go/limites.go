package chispa

import "fmt"

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

// validar comprueba la petición como el servidor (todo o nada, mismos códigos). Devuelve *ErrorChispa con Status 0.
func (l Limites) validar(estado string, qs []Pregunta) *ErrorChispa {
	if len(estado) > l.MaxEstado {
		return falla("state_too_long", fmt.Sprintf("state: %d bytes, máximo %d", len(estado), l.MaxEstado), "")
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
		if len(q.ID) > l.MaxID {
			return falla("field_too_long", fmt.Sprintf("%s.id: %d bytes, máximo %d", r, len(q.ID), l.MaxID), q.ID)
		}
		if vistos[q.ID] {
			return falla("duplicate_question_id", fmt.Sprintf("%s.id: %q repetido", r, q.ID), q.ID)
		}
		vistos[q.ID] = true
		if q.Texto == "" {
			return falla("missing_question", r+".question: obligatorio", q.ID)
		}
		if len(q.Texto) > l.MaxTexto {
			return falla("field_too_long", fmt.Sprintf("%s.question: %d bytes, máximo %d", r, len(q.Texto), l.MaxTexto), q.ID)
		}
		if q.Kind == "" {
			return falla("missing_kind", r+".kind: obligatorio", q.ID)
		}
		if q.Kind != KindChoice && q.Kind != KindScore && q.Kind != KindNoul {
			return falla("invalid_kind", fmt.Sprintf("%s.kind: %q no válido (choice, score o noul)", r, q.Kind), q.ID)
		}
		if len(q.Nonce) > l.MaxID {
			return falla("field_too_long", fmt.Sprintf("%s.nonce: %d bytes, máximo %d", r, len(q.Nonce), l.MaxID), q.ID)
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
		if len(o.ID) > l.MaxID {
			return falla("field_too_long", fmt.Sprintf("%s.id: %d bytes, máximo %d", ro, len(o.ID), l.MaxID), q.ID)
		}
		if vistas[o.ID] {
			return falla("duplicate_option_id", fmt.Sprintf("%s.id: %q repetido", ro, o.ID), q.ID)
		}
		vistas[o.ID] = true
		if len(o.Description) > l.MaxTexto {
			return falla("field_too_long", fmt.Sprintf("%s.description: %d bytes, máximo %d", ro, len(o.Description), l.MaxTexto), q.ID)
		}
	}
	return nil
}
