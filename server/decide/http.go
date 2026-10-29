package decide

import (
	"bytes"
	"context"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"sync"
	"sync/atomic"
	"time"
)

// Valores por defecto de los límites (ver Limites).
const (
	MaxCuerpo     = 1 << 20
	MaxPreguntas  = 256
	MaxOpciones   = 256
	MaxEstadoByte = 256 << 10
	MaxTextoByte  = 4 << 10 // question, description de opción
	MaxIDByte     = 256     // id de pregunta, id de opción, nonce
)

// Códigos de error de la API (campo error.code). Contrato: server/api/openapi.yaml.
const (
	ErrJSONInvalido      = "invalid_json"
	ErrCuerpoGrande      = "request_too_large"
	ErrMetodo            = "method_not_allowed"
	ErrNoEncontrado      = "not_found"
	ErrSinPreguntas      = "empty_questions"
	ErrDemasiadasPreg    = "too_many_questions"
	ErrEstadoLargo       = "state_too_long"
	ErrIDFalta           = "missing_id"
	ErrPreguntaFalta     = "missing_question"
	ErrKindFalta         = "missing_kind"
	ErrKindInvalido      = "invalid_kind"
	ErrPocasOpciones     = "too_few_options"
	ErrDemasiadasOpc     = "too_many_options"
	ErrOpcionesInvalidas = "invalid_options"
	ErrOpcionIDFalta     = "missing_option_id"
	ErrPreguntaIDDup     = "duplicate_question_id"
	ErrOpcionIDDup       = "duplicate_option_id"
	ErrCampoLargo        = "field_too_long"
	ErrNoAutorizado      = "unauthorized"
	ErrRecargaFallida    = "reload_failed"
	ErrLimitada          = "rate_limited"
)

// Limites son los topes de entrada de /v1/decide. Un valor 0 en el JSON de configuración
// conserva el valor por defecto.
type Limites struct {
	MaxCuerpo    int `json:"max_cuerpo"`    // bytes del cuerpo HTTP → 413
	MaxPreguntas int `json:"max_preguntas"` // preguntas por petición
	MaxOpciones  int `json:"max_opciones"`  // opciones por pregunta
	MaxEstado    int `json:"max_estado"`    // bytes de state
	MaxTexto     int `json:"max_texto"`     // bytes de question y de cada description
	MaxID        int `json:"max_id"`        // bytes de cada id y nonce
}

func LimitesPorDefecto() Limites {
	return Limites{MaxCuerpo, MaxPreguntas, MaxOpciones, MaxEstadoByte, MaxTextoByte, MaxIDByte}
}

func (l Limites) validar() error {
	for n, v := range map[string]int{"max_cuerpo": l.MaxCuerpo, "max_preguntas": l.MaxPreguntas, "max_opciones": l.MaxOpciones,
		"max_estado": l.MaxEstado, "max_texto": l.MaxTexto, "max_id": l.MaxID} {
		if v < 0 {
			return fmt.Errorf("config: limites.%s no puede ser negativo, llegó %d", n, v)
		}
	}
	return nil
}

// Servidor expone la cascada por HTTP.
type Servidor struct {
	Met *Metricas
	cur atomic.Pointer[vivo] // modelo en servicio: cascada, caché de nonces y límites (ver recarga.go)

	armador    Armador
	adminToken string
	recMu      sync.Mutex // serializa Recargar

	enCurso            chan struct{} // semáforo de peticiones simultáneas a /v1/decide (nil = sin tope)
	plazoCuerpo        time.Duration // plazo para recibir el cuerpo entero (0 = plazoCuerpoDefecto, <0 = sin plazo)
	metricasProtegidas bool          // /metrics pide admin_token o una clave de API
}

// plazoCuerpoDefecto es lo que tiene un cliente para mandar el cuerpo entero de /v1/decide.
const plazoCuerpoDefecto = 10 * time.Second

// ConMaxEnCurso limita las peticiones a /v1/decide en curso a la vez (n ≤ 0 = sin tope). Al llenarse responde 429 rate_limited
// con Retry-After. Acota la memoria de las decodificaciones simultáneas. Se llama antes de servir.
func (s *Servidor) ConMaxEnCurso(n int) *Servidor {
	if n > 0 {
		s.enCurso = make(chan struct{}, n)
	} else {
		s.enCurso = nil
	}
	return s
}

// ConPlazoCuerpo fija el plazo para recibir el cuerpo de /v1/decide (0 = 10 s, negativo = sin plazo). Se llama antes de servir.
func (s *Servidor) ConPlazoCuerpo(d time.Duration) *Servidor {
	s.plazoCuerpo = d
	return s
}

// ConMetricasProtegidas hace que /metrics exija Authorization: Bearer con el admin_token o una clave de API válida. Sin ninguna de
// las dos configuradas responde 401 siempre. Por defecto (false) /metrics sigue abierto. Se llama antes de servir.
func (s *Servidor) ConMetricasProtegidas(p bool) *Servidor {
	s.metricasProtegidas = p
	return s
}

// metricasAutorizado dice si la petición puede leer /metrics.
func (s *Servidor) metricasAutorizado(r *http.Request) bool {
	if !s.metricasProtegidas {
		return true
	}
	got, ok := bearer(r.Header.Get("Authorization"))
	if !ok {
		return false
	}
	if s.adminToken != "" {
		a, b := sha256.Sum256([]byte(got)), sha256.Sum256([]byte(s.adminToken))
		if subtle.ConstantTimeCompare(a[:], b[:]) == 1 {
			return true
		}
	}
	if a := s.cur.Load().auth; a != nil && a.busca(got) != nil {
		return true
	}
	return false
}

func NuevoServidor(c *Cascada, met *Metricas, cacheRespuestas int) *Servidor {
	s := &Servidor{Met: met}
	s.cur.Store(s.nuevoVivo(&Armado{Cascada: c, CacheRespuestas: cacheRespuestas, Limites: LimitesPorDefecto()}, 1, nil))
	return s
}

// ConLimites cambia los topes de entrada (los campos a 0 se quedan en su valor por defecto). Se llama antes de servir;
// las recargas traen los suyos en Armado.Limites.
func (s *Servidor) ConLimites(l Limites) *Servidor {
	s.cur.Load().lim = normalizaLimites(l)
	return s
}

func normalizaLimites(l Limites) Limites {
	d := LimitesPorDefecto()
	for _, p := range []struct {
		dst *int
		v   int
	}{{&d.MaxCuerpo, l.MaxCuerpo}, {&d.MaxPreguntas, l.MaxPreguntas},
		{&d.MaxOpciones, l.MaxOpciones}, {&d.MaxEstado, l.MaxEstado}, {&d.MaxTexto, l.MaxTexto}, {&d.MaxID, l.MaxID}} {
		if p.v > 0 {
			*p.dst = p.v
		}
	}
	return d
}

func (s *Servidor) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/v1/decide", s.conAuth(s.decide))
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		io.WriteString(w, `{"status":"ok"}`+"\n")
	})
	mux.HandleFunc("/metrics", func(w http.ResponseWriter, r *http.Request) {
		if !s.metricasAutorizado(r) {
			s.Met.AuthRechazo()
			w.Header().Set("WWW-Authenticate", "Bearer")
			s.fallo(w, http.StatusUnauthorized, ErrNoAutorizado, "", "/metrics pide Authorization: Bearer con el admin_token o una clave de API")
			return
		}
		w.Header().Set("Content-Type", "text/plain; version=0.0.4")
		s.Met.Escribe(w)
	})
	if s.adminToken != "" {
		mux.HandleFunc("/v1/admin/recargar", s.admin)
	}
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		s.fallo(w, http.StatusNotFound, ErrNoEncontrado, "", "ruta %s no existe", r.URL.Path)
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

// errorHTTP es el cuerpo de todo error: {"error":{"code","message","question_id"}}.
type errorHTTP struct {
	Error cuerpoError `json:"error"`
}

type cuerpoError struct {
	Code       string `json:"code"`
	Message    string `json:"message"`
	QuestionID string `json:"question_id,omitempty"`
}

// errAPI es un error de validación: código HTTP, código tipado y la pregunta implicada.
type errAPI struct {
	status int
	code   string
	qid    string
	msg    string
}

func (e *errAPI) Error() string { return e.msg }

func (s *Servidor) fallo(w http.ResponseWriter, status int, code, qid, format string, a ...any) {
	s.Met.Peticion(status)
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(errorHTTP{cuerpoError{Code: code, Message: fmt.Sprintf(format, a...), QuestionID: qid}})
}

func (s *Servidor) decide(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		w.Header().Set("Allow", "POST")
		s.fallo(w, http.StatusMethodNotAllowed, ErrMetodo, "", "método %s no permitido: usa POST", r.Method)
		return
	}
	if s.enCurso != nil {
		select {
		case s.enCurso <- struct{}{}:
			defer func() { <-s.enCurso }()
		default:
			w.Header().Set("Retry-After", "1")
			s.fallo(w, http.StatusTooManyRequests, ErrLimitada, "", "servidor saturado: demasiadas peticiones en curso")
			return
		}
	}
	// El cuerpo se lee (con plazo) antes de tomar el modelo: un cliente lento no retiene el modelo retirado.
	lim := s.cur.Load().lim
	body, err := s.leeCuerpo(w, r, lim.MaxCuerpo)
	if err != nil {
		var mbe *http.MaxBytesError
		if errors.As(err, &mbe) {
			s.fallo(w, http.StatusRequestEntityTooLarge, ErrCuerpoGrande, "", "cuerpo de más de %d bytes", lim.MaxCuerpo)
		} else {
			s.fallo(w, http.StatusBadRequest, ErrJSONInvalido, "", "no se pudo leer el cuerpo: %v", err)
		}
		return
	}
	v := s.adquirir()
	defer v.soltar()
	if len(body) > v.lim.MaxCuerpo {
		s.fallo(w, http.StatusRequestEntityTooLarge, ErrCuerpoGrande, "", "cuerpo de más de %d bytes", v.lim.MaxCuerpo)
		return
	}
	if ea := escaneaPeticion(body, v.lim); ea != nil {
		s.fallo(w, ea.status, ea.code, ea.qid, "%s", ea.msg)
		return
	}
	var req peticion
	dec := json.NewDecoder(bytes.NewReader(body))
	dec.DisallowUnknownFields()
	if err := dec.Decode(&req); err != nil {
		s.fallo(w, http.StatusBadRequest, ErrJSONInvalido, "", "JSON no válido: %v", err)
		return
	}
	if dec.More() {
		s.fallo(w, http.StatusBadRequest, ErrJSONInvalido, "", "JSON no válido: datos tras el objeto")
		return
	}
	preguntas, ea := v.lim.validarPeticion(req)
	if ea != nil {
		s.fallo(w, ea.status, ea.code, ea.qid, "%s", ea.msg)
		return
	}
	// La clave paga el resto de preguntas (la primera ya la cobró conAuth con la petición).
	cl := cobroDe(r.Context())
	cl.cobra(len(preguntas) - 1)
	idClave := cl.id()
	out := respuestaHTTP{Results: make([]json.RawMessage, len(preguntas))}
	ctx := conPresupuesto(r.Context())
	for i, p := range preguntas {
		if ctx.Err() != nil {
			s.cuentaTimeout(ctx)
			return // cliente ido: nada que escribir ni que cachear
		}
		var ck string
		if p.Nonce != "" {
			h := sha256.Sum256([]byte(p.Estado))
			ck = idClave + "|" + p.Nonce + "|" + hex.EncodeToString(h[:8]) + "|" + ClaveEsquema(p) + "|" + p.ID
			if b, ok := v.nonces.Get(ck); ok {
				s.Met.NonceHits.Add(1)
				out.Results[i] = b
				continue
			}
		}
		res := v.casc.Decidir(ctx, p)
		if ctx.Err() != nil {
			s.cuentaTimeout(ctx)
			return
		}
		b, _ := json.Marshal(res)
		if ck != "" && !res.Incompleto {
			v.nonces.Put(ck, b)
		}
		out.Results[i] = b
	}
	if ctx.Err() != nil { // el plazo pudo vencer tras el último Decidir: el cliente recibe el 503 del timeout
		s.cuentaTimeout(ctx)
		return
	}
	s.Met.Peticion(http.StatusOK)
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(out)
}

type ctxRW struct{}

// leeCuerpo lee el cuerpo con tope de tamaño y plazo. El plazo va en la conexión (SetReadDeadline) porque cerrar el cuerpo desde
// otra goroutine no desbloquea una lectura en curso. Bajo ConTimeout el w de aquí no deja llegar a la conexión: se usa el original.
func (s *Servidor) leeCuerpo(w http.ResponseWriter, r *http.Request, max int) ([]byte, error) {
	plazo := s.plazoCuerpo
	if plazo == 0 {
		plazo = plazoCuerpoDefecto
	}
	var rc *http.ResponseController
	if plazo > 0 {
		rw := w
		if o, ok := r.Context().Value(ctxRW{}).(http.ResponseWriter); ok {
			rw = o
		}
		rc = http.NewResponseController(rw)
		if rc.SetReadDeadline(time.Now().Add(plazo)) != nil {
			rc = nil
		}
	}
	body, err := io.ReadAll(http.MaxBytesReader(w, r.Body, int64(max)))
	if err != nil {
		// Con el cuerpo a medias el servidor intentaría vaciarlo antes de responder: se cierra la conexión y se deja el plazo vencido.
		w.Header().Set("Connection", "close")
		return nil, err
	}
	if rc != nil {
		rc.SetReadDeadline(time.Time{})
	}
	return body, nil
}

// --- Escaneo previo del JSON: nombres exactos, sin duplicados y topes, sin asignar memoria ---

const profMaxJSON = 32

// Nodos del esquema de la petición que el escáner conoce; kAny es todo lo demás (sin comprobaciones).
const (
	kAny = iota
	kRoot
	kQuestions
	kQuestion
	kOptions
	kOption
)

var errSintaxis = errors.New("sintaxis")

type escaner struct {
	b   []byte
	i   int
	l   Limites
	qid string // id de la pregunta en curso, si ya se vio
}

// escaneaPeticion recorre el cuerpo ya leído en una pasada, sin asignar, y rechaza con 400 los nombres de campo que no coinciden
// exactamente con el contrato (p. ej. STATE), los campos repetidos, el exceso de preguntas u opciones y la profundidad excesiva.
// Si encuentra un fallo de sintaxis no lo describe: devuelve nil y la decodificación posterior responde el 400 de JSON no válido.
func escaneaPeticion(body []byte, l Limites) *errAPI {
	e := escaner{b: body, l: l}
	err := e.valor(kRoot, 0)
	if err == nil {
		return nil
	}
	if ea, ok := err.(*errAPI); ok {
		return ea
	}
	return nil
}

func (e *escaner) ws() {
	for e.i < len(e.b) {
		switch e.b[e.i] {
		case ' ', '\t', '\n', '\r':
			e.i++
		default:
			return
		}
	}
}

// cadena consume una cadena JSON y devuelve su contenido crudo (sin comillas) y si trae escapes.
func (e *escaner) cadena() (raw []byte, esc bool, err error) {
	if e.i >= len(e.b) || e.b[e.i] != '"' {
		return nil, false, errSintaxis
	}
	e.i++
	ini := e.i
	for e.i < len(e.b) {
		switch c := e.b[e.i]; {
		case c == '"':
			raw = e.b[ini:e.i]
			e.i++
			return raw, esc, nil
		case c == '\\':
			esc = true
			e.i += 2
		case c < 0x20:
			return nil, false, errSintaxis
		default:
			e.i++
		}
	}
	return nil, false, errSintaxis
}

// texto devuelve el contenido de la cadena ya sin escapes (solo asigna si los trae).
func texto(raw []byte, esc bool) (string, error) {
	if !esc {
		return string(raw), nil
	}
	var s string
	q := make([]byte, 0, len(raw)+2)
	q = append(q, '"')
	q = append(q, raw...)
	q = append(q, '"')
	if err := json.Unmarshal(q, &s); err != nil {
		return "", errSintaxis
	}
	return s, nil
}

// escalar salta un número o literal (true/false/null); la validación fina la hace la decodificación posterior.
func (e *escaner) escalar() error {
	ini := e.i
	for e.i < len(e.b) {
		switch e.b[e.i] {
		case ',', ']', '}', ' ', '\t', '\n', '\r', '"', '{', '[', ':':
			if e.i == ini {
				return errSintaxis
			}
			return nil
		}
		e.i++
	}
	if e.i == ini {
		return errSintaxis
	}
	return nil
}

func (e *escaner) valor(k, prof int) error {
	e.ws()
	if e.i >= len(e.b) {
		return errSintaxis
	}
	switch e.b[e.i] {
	case '"':
		_, _, err := e.cadena()
		return err
	case '{':
		return e.objeto(k, prof)
	case '[':
		return e.array(k, prof)
	}
	return e.escalar()
}

func (e *escaner) objeto(k, prof int) error {
	if prof > profMaxJSON {
		return bad(ErrJSONInvalido, "", "JSON no válido: anidado de más de %d niveles", profMaxJSON)
	}
	e.i++
	if k == kQuestion {
		e.qid = ""
	}
	var visto uint8
	primero := true
	for {
		e.ws()
		if e.i >= len(e.b) {
			return errSintaxis
		}
		if e.b[e.i] == '}' {
			e.i++
			return nil
		}
		if !primero {
			if e.b[e.i] != ',' {
				return errSintaxis
			}
			e.i++
			e.ws()
		}
		primero = false
		raw, esc, err := e.cadena()
		if err != nil {
			return err
		}
		sub := kAny
		var kid string
		var campo = -1
		if k == kRoot || k == kQuestion || k == kOption {
			if esc {
				kid, err = texto(raw, true)
				if err != nil {
					return err
				}
				raw = []byte(kid)
			}
			switch k {
			case kRoot:
				switch string(raw) {
				case "state":
					campo = 0
				case "questions":
					campo, sub = 1, kQuestions
				}
			case kQuestion:
				switch string(raw) {
				case "id":
					campo = 0
				case "question":
					campo = 1
				case "kind":
					campo = 2
				case "nonce":
					campo = 3
				case "options":
					campo, sub = 4, kOptions
				}
			case kOption:
				switch string(raw) {
				case "id":
					campo = 0
				case "description":
					campo = 1
				}
			}
			if campo < 0 {
				return bad(ErrJSONInvalido, "", "JSON no válido: unknown field %q (campo desconocido: los nombres van exactos, en minúsculas)", string(raw))
			}
			if visto&(1<<campo) != 0 {
				return bad(ErrJSONInvalido, "", "JSON no válido: campo %q repetido", string(raw))
			}
			visto |= 1 << campo
		}
		e.ws()
		if e.i >= len(e.b) || e.b[e.i] != ':' {
			return errSintaxis
		}
		e.i++
		e.ws()
		if k == kQuestion && campo == 0 && e.i < len(e.b) && e.b[e.i] == '"' {
			r, es, err := e.cadena()
			if err != nil {
				return err
			}
			if e.qid, err = texto(r, es); err != nil {
				return err
			}
			continue
		}
		if err := e.valor(sub, prof+1); err != nil {
			return err
		}
	}
}

func (e *escaner) array(k, prof int) error {
	if prof > profMaxJSON {
		return bad(ErrJSONInvalido, "", "JSON no válido: anidado de más de %d niveles", profMaxJSON)
	}
	e.i++
	max, elem := 0, kAny
	switch k {
	case kQuestions:
		max, elem = e.l.MaxPreguntas, kQuestion
	case kOptions:
		max, elem = e.l.MaxOpciones, kOption
	}
	n := 0
	for {
		e.ws()
		if e.i >= len(e.b) {
			return errSintaxis
		}
		if e.b[e.i] == ']' {
			e.i++
			return nil
		}
		if n > 0 {
			if e.b[e.i] != ',' {
				return errSintaxis
			}
			e.i++
		}
		n++
		if max > 0 && n > max {
			if k == kQuestions {
				return bad(ErrDemasiadasPreg, "", "questions: máximo %d por petición, llegaron más", max)
			}
			return bad(ErrDemasiadasOpc, e.qid, "options: máximo %d opciones", max)
		}
		if err := e.valor(elem, prof+1); err != nil {
			return err
		}
	}
}

// cuentaTimeout apunta las peticiones que acaban por plazo vencido (no las que el cliente cancela).
func (s *Servidor) cuentaTimeout(ctx context.Context) {
	if errors.Is(ctx.Err(), context.DeadlineExceeded) {
		s.Met.Timeouts.Add(1)
	}
}

func bad(code, qid, format string, a ...any) *errAPI {
	return &errAPI{http.StatusBadRequest, code, qid, fmt.Sprintf(format, a...)}
}

func (l Limites) validarPeticion(req peticion) ([]Pregunta, *errAPI) {
	if len(req.State) > l.MaxEstado {
		return nil, bad(ErrEstadoLargo, "", "state de más de %d bytes", l.MaxEstado)
	}
	if len(req.Questions) == 0 {
		return nil, bad(ErrSinPreguntas, "", "questions: hace falta al menos una pregunta")
	}
	if len(req.Questions) > l.MaxPreguntas {
		return nil, bad(ErrDemasiadasPreg, "", "questions: máximo %d por petición, llegaron %d", l.MaxPreguntas, len(req.Questions))
	}
	ids := map[string]bool{}
	out := make([]Pregunta, len(req.Questions))
	for i, q := range req.Questions {
		at := fmt.Sprintf("questions[%d]", i)
		if q.ID == "" {
			return nil, bad(ErrIDFalta, "", "%s.id: obligatorio", at)
		}
		if len(q.ID) > l.MaxID {
			return nil, bad(ErrCampoLargo, "", "%s.id: más de %d bytes", at, l.MaxID)
		}
		if ids[q.ID] {
			return nil, bad(ErrPreguntaIDDup, q.ID, "%s.id: %q repetido", at, q.ID)
		}
		ids[q.ID] = true
		if q.Question == "" {
			return nil, bad(ErrPreguntaFalta, q.ID, "%s.question: obligatorio", at)
		}
		if len(q.Question) > l.MaxTexto {
			return nil, bad(ErrCampoLargo, q.ID, "%s.question: más de %d bytes", at, l.MaxTexto)
		}
		if len(q.Nonce) > l.MaxID {
			return nil, bad(ErrCampoLargo, q.ID, "%s.nonce: más de %d bytes", at, l.MaxID)
		}
		ops := q.Options
		switch q.Kind {
		case KindChoice, KindScore:
			if len(ops) < 2 {
				return nil, bad(ErrPocasOpciones, q.ID, "%s.options: %s necesita al menos 2 opciones", at, q.Kind)
			}
		case KindNoul:
			if len(ops) == 0 {
				ops = []Opcion{{ID: "false"}, {ID: "true"}}
			} else if len(ops) != 2 || firma([]string{ops[0].ID, ops[1].ID}) != firma([]string{"false", "true"}) {
				return nil, bad(ErrOpcionesInvalidas, q.ID, `%s.options: noul solo admite los ids "false" y "true"`, at)
			}
		case "":
			return nil, bad(ErrKindFalta, q.ID, "%s.kind: obligatorio (choice, score o noul)", at)
		default:
			return nil, bad(ErrKindInvalido, q.ID, "%s.kind: %q no válido (choice, score o noul)", at, q.Kind)
		}
		if len(ops) > l.MaxOpciones {
			return nil, bad(ErrDemasiadasOpc, q.ID, "%s.options: máximo %d opciones", at, l.MaxOpciones)
		}
		seen := map[string]bool{}
		for j, o := range ops {
			if o.ID == "" {
				return nil, bad(ErrOpcionIDFalta, q.ID, "%s.options[%d].id: obligatorio", at, j)
			}
			if len(o.ID) > l.MaxID {
				return nil, bad(ErrCampoLargo, q.ID, "%s.options[%d].id: más de %d bytes", at, j, l.MaxID)
			}
			if len(o.Description) > l.MaxTexto {
				return nil, bad(ErrCampoLargo, q.ID, "%s.options[%d].description: más de %d bytes", at, j, l.MaxTexto)
			}
			if seen[o.ID] {
				return nil, bad(ErrOpcionIDDup, q.ID, "%s.options[%d].id: %q repetido", at, j, o.ID)
			}
			seen[o.ID] = true
		}
		out[i] = Pregunta{ID: q.ID, Estado: req.State, Texto: q.Question, Kind: q.Kind, Opciones: ops, Nonce: q.Nonce}
	}
	return out, nil
}

// RetryAfterTimeout son los segundos que pide Retry-After en la respuesta de timeout.
const RetryAfterTimeout = 5

// ConTimeout limita cada petición a d (cancela su ctx). Al vencer responde 503 con
// Content-Type application/json, Retry-After y el código de error «timeout».
func ConTimeout(h http.Handler, d time.Duration) http.Handler { return ConTimeoutMet(h, d, nil) }

// ConTimeoutMet es ConTimeout y además cuenta cada 503 de timeout en chispa_peticiones_total{codigo="503"} (met puede ser nil).
func ConTimeoutMet(h http.Handler, d time.Duration, met *Metricas) http.Handler {
	cuerpo := `{"error":{"code":"timeout","message":"la petición superó el tiempo máximo"}}`
	th := http.TimeoutHandler(h, d, cuerpo)
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// TimeoutHandler esconde la conexión: el original va en el ctx para poder fijar el plazo de lectura del cuerpo.
		th.ServeHTTP(&escrituraTimeout{ResponseWriter: w, met: met}, r.WithContext(context.WithValue(r.Context(), ctxRW{}, w)))
	})
}

// escrituraTimeout añade las cabeceras de timeout cuando http.TimeoutHandler escribe su 503.
type escrituraTimeout struct {
	http.ResponseWriter
	met *Metricas
}

func (e *escrituraTimeout) WriteHeader(status int) {
	if status == http.StatusServiceUnavailable {
		e.Header().Set("Content-Type", "application/json")
		e.Header().Set("Retry-After", strconv.Itoa(RetryAfterTimeout))
		if e.met != nil {
			e.met.Peticion(status)
		}
	}
	e.ResponseWriter.WriteHeader(status)
}
