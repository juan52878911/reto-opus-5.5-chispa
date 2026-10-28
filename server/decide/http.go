package decide

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
)

const (
	MaxCuerpo     = 1 << 20
	MaxPreguntas  = 256
	MaxOpciones   = 256
	MaxEstadoByte = 256 << 10
)

// Servidor expone la cascada por HTTP.
type Servidor struct {
	Cascada *Cascada
	Met     *Metricas
	nonces  *LRU[[]byte] // nonce+contenido → Resultado serializado
}

func NuevoServidor(c *Cascada, met *Metricas, cacheRespuestas int) *Servidor {
	return &Servidor{Cascada: c, Met: met, nonces: NewLRU[[]byte](cacheRespuestas)}
}

func (s *Servidor) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/v1/decide", s.decide)
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		io.WriteString(w, `{"status":"ok"}`+"\n")
	})
	mux.HandleFunc("/metrics", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain; version=0.0.4")
		s.Met.Escribe(w)
	})
	return mux
}

type peticion struct {
	State     string `json:"state"`
	Questions []struct {
		ID       string   `json:"id"`
		Question string   `json:"question"`
		Kind     string   `json:"kind"`
		Options  []Opcion `json:"options"`
		Nonce    string   `json:"nonce"`
	} `json:"questions"`
}

type respuestaHTTP struct {
	Results []json.RawMessage `json:"results"`
}

type errorHTTP struct {
	Error string `json:"error"`
}

func (s *Servidor) fallo(w http.ResponseWriter, code int, format string, a ...any) {
	s.Met.Peticion(code)
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	json.NewEncoder(w).Encode(errorHTTP{fmt.Sprintf(format, a...)})
}

func (s *Servidor) decide(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		w.Header().Set("Allow", "POST")
		s.fallo(w, http.StatusMethodNotAllowed, "método %s no permitido: usa POST", r.Method)
		return
	}
	body, err := io.ReadAll(http.MaxBytesReader(w, r.Body, MaxCuerpo))
	if err != nil {
		var mbe *http.MaxBytesError
		if errors.As(err, &mbe) {
			s.fallo(w, http.StatusRequestEntityTooLarge, "cuerpo de más de %d bytes", MaxCuerpo)
		} else {
			s.fallo(w, http.StatusBadRequest, "no se pudo leer el cuerpo: %v", err)
		}
		return
	}
	var req peticion
	dec := json.NewDecoder(bytes.NewReader(body))
	dec.DisallowUnknownFields()
	if err := dec.Decode(&req); err != nil {
		s.fallo(w, http.StatusBadRequest, "JSON no válido: %v", err)
		return
	}
	if dec.More() {
		s.fallo(w, http.StatusBadRequest, "JSON no válido: datos tras el objeto")
		return
	}
	preguntas, err := validar(req)
	if err != nil {
		s.fallo(w, http.StatusBadRequest, "%v", err)
		return
	}
	out := respuestaHTTP{Results: make([]json.RawMessage, len(preguntas))}
	for i, p := range preguntas {
		var ck string
		if p.Nonce != "" {
			h := sha256.Sum256([]byte(p.Estado))
			ck = p.Nonce + "|" + hex.EncodeToString(h[:8]) + "|" + ClaveEsquema(p) + "|" + p.ID
			if b, ok := s.nonces.Get(ck); ok {
				s.Met.NonceHits.Add(1)
				out.Results[i] = b
				continue
			}
		}
		b, _ := json.Marshal(s.Cascada.Decidir(r.Context(), p))
		if ck != "" {
			s.nonces.Put(ck, b)
		}
		out.Results[i] = b
	}
	s.Met.Peticion(http.StatusOK)
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(out)
}

func validar(req peticion) ([]Pregunta, error) {
	if len(req.State) > MaxEstadoByte {
		return nil, fmt.Errorf("state de más de %d bytes", MaxEstadoByte)
	}
	if len(req.Questions) == 0 {
		return nil, errors.New("questions: hace falta al menos una pregunta")
	}
	if len(req.Questions) > MaxPreguntas {
		return nil, fmt.Errorf("questions: máximo %d por petición, llegaron %d", MaxPreguntas, len(req.Questions))
	}
	ids := map[string]bool{}
	out := make([]Pregunta, len(req.Questions))
	for i, q := range req.Questions {
		at := fmt.Sprintf("questions[%d]", i)
		if q.ID == "" {
			return nil, fmt.Errorf("%s.id: obligatorio", at)
		}
		if ids[q.ID] {
			return nil, fmt.Errorf("%s.id: %q repetido", at, q.ID)
		}
		ids[q.ID] = true
		if q.Question == "" {
			return nil, fmt.Errorf("%s.question: obligatorio", at)
		}
		ops := q.Options
		switch q.Kind {
		case KindChoice, KindScore:
			if len(ops) < 2 {
				return nil, fmt.Errorf("%s.options: %s necesita al menos 2 opciones", at, q.Kind)
			}
		case KindNoul:
			if len(ops) == 0 {
				ops = []Opcion{{ID: "false"}, {ID: "true"}}
			} else if len(ops) != 2 || firma([]string{ops[0].ID, ops[1].ID}) != firma([]string{"false", "true"}) {
				return nil, fmt.Errorf(`%s.options: noul solo admite los ids "false" y "true"`, at)
			}
		case "":
			return nil, fmt.Errorf("%s.kind: obligatorio (choice, score o noul)", at)
		default:
			return nil, fmt.Errorf("%s.kind: %q no válido (choice, score o noul)", at, q.Kind)
		}
		if len(ops) > MaxOpciones {
			return nil, fmt.Errorf("%s.options: máximo %d opciones", at, MaxOpciones)
		}
		seen := map[string]bool{}
		for j, o := range ops {
			if o.ID == "" {
				return nil, fmt.Errorf("%s.options[%d].id: obligatorio", at, j)
			}
			if seen[o.ID] {
				return nil, fmt.Errorf("%s.options[%d].id: %q repetido", at, j, o.ID)
			}
			seen[o.ID] = true
		}
		out[i] = Pregunta{ID: q.ID, Estado: req.State, Texto: q.Question, Kind: q.Kind, Opciones: ops, Nonce: q.Nonce}
	}
	return out, nil
}
