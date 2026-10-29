package decide

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"sort"
	"strconv"
	"strings"
	"testing"
)

// --- lector del subconjunto de YAML que usa api/openapi.yaml: mapas y listas por sangría,
// escalares, y valores de una línea en JSON ({...}) o en lista plana ([a, b]).

type lineaY struct {
	ind int
	txt string
}

func leerYAML(src string) (any, error) {
	var ls []lineaY
	for _, l := range strings.Split(src, "\n") {
		if strings.TrimSpace(l) == "" || strings.HasPrefix(strings.TrimSpace(l), "#") {
			continue
		}
		t := strings.TrimLeft(l, " ")
		ls = append(ls, lineaY{len(l) - len(t), t})
	}
	v, n, err := bloqueY(ls, 0, ls[0].ind)
	if err == nil && n != len(ls) {
		err = fmt.Errorf("sobran líneas desde %q", ls[n].txt)
	}
	return v, err
}

func escalarY(s string) (any, error) {
	switch {
	case strings.HasPrefix(s, "{"):
		var m any
		return m, json.Unmarshal([]byte(s), &m)
	case strings.HasPrefix(s, "["):
		var m any
		if json.Unmarshal([]byte(s), &m) == nil {
			return m, nil
		}
		out := []any{}
		for _, p := range strings.Split(strings.Trim(s, "[]"), ",") {
			out = append(out, strings.TrimSpace(p))
		}
		return out, nil
	case strings.HasPrefix(s, `"`):
		return strconv.Unquote(s)
	case s == "true" || s == "false":
		return s == "true", nil
	}
	if f, err := strconv.ParseFloat(s, 64); err == nil {
		return f, nil
	}
	return s, nil
}

func bloqueY(ls []lineaY, i, ind int) (any, int, error) {
	if strings.HasPrefix(ls[i].txt, "- ") {
		lista := []any{}
		for i < len(ls) && ls[i].ind == ind && strings.HasPrefix(ls[i].txt, "- ") {
			ls[i] = lineaY{ind + 2, ls[i].txt[2:]} // el elemento se lee como un mapa más sangrado
			v, n, err := bloqueY(ls, i, ind+2)
			if err != nil {
				return nil, 0, err
			}
			lista = append(lista, v)
			i = n
		}
		return lista, i, nil
	}
	m := map[string]any{}
	for i < len(ls) && ls[i].ind == ind {
		k, resto, ok := strings.Cut(ls[i].txt, ":")
		if !ok {
			return nil, 0, fmt.Errorf("línea sin ':': %q", ls[i].txt)
		}
		k = strings.Trim(k, `"`)
		resto = strings.TrimSpace(resto)
		i++
		if resto != "" {
			v, err := escalarY(resto)
			if err != nil {
				return nil, 0, fmt.Errorf("%s: %w", k, err)
			}
			m[k] = v
			continue
		}
		if i >= len(ls) || ls[i].ind <= ind {
			m[k] = nil
			continue
		}
		v, n, err := bloqueY(ls, i, ls[i].ind)
		if err != nil {
			return nil, 0, err
		}
		m[k], i = v, n
	}
	return m, i, nil
}

// --- validador mínimo de JSON Schema (el subconjunto que usa el OpenAPI).

type validador struct{ doc map[string]any }

func (v validador) ref(s map[string]any) map[string]any {
	r, ok := s["$ref"].(string)
	if !ok {
		return s
	}
	var cur any = v.doc
	for _, p := range strings.Split(strings.TrimPrefix(r, "#/"), "/") {
		cur = cur.(map[string]any)[p]
	}
	return cur.(map[string]any)
}

func (v validador) check(s map[string]any, x any, at string) []string {
	s = v.ref(s)
	var errs []string
	fail := func(f string, a ...any) { errs = append(errs, at+": "+fmt.Sprintf(f, a...)) }
	if en, ok := s["enum"].([]any); ok {
		hay := false
		for _, e := range en {
			hay = hay || e == x
		}
		if !hay {
			fail("%v fuera del enum %v", x, en)
		}
	}
	switch s["type"] {
	case "object":
		m, ok := x.(map[string]any)
		if !ok {
			return append(errs, at+": se esperaba objeto")
		}
		props, _ := s["properties"].(map[string]any)
		if req, ok := s["required"].([]any); ok {
			for _, r := range req {
				if _, ok := m[r.(string)]; !ok {
					fail("falta %q", r)
				}
			}
		}
		for k, val := range m {
			if p, ok := props[k]; ok {
				errs = append(errs, v.check(p.(map[string]any), val, at+"."+k)...)
			} else if ap, ok := s["additionalProperties"].(map[string]any); ok {
				errs = append(errs, v.check(ap, val, at+"."+k)...)
			} else if s["additionalProperties"] == false {
				fail("campo %q no declarado", k)
			}
		}
	case "array":
		a, ok := x.([]any)
		if !ok {
			return append(errs, at+": se esperaba array")
		}
		if n, ok := s["minItems"].(float64); ok && float64(len(a)) < n {
			fail("menos de %v elementos", n)
		}
		if n, ok := s["maxItems"].(float64); ok && float64(len(a)) > n {
			fail("más de %v elementos", n)
		}
		if it, ok := s["items"].(map[string]any); ok {
			for i, e := range a {
				errs = append(errs, v.check(it, e, fmt.Sprintf("%s[%d]", at, i))...)
			}
		}
	case "string":
		str, ok := x.(string)
		if !ok {
			return append(errs, at+": se esperaba string")
		}
		if n, ok := s["minLength"].(float64); ok && float64(len(str)) < n {
			fail("más corto que %v", n)
		}
		if n, ok := s["x-max-bytes"].(float64); ok && float64(len(str)) > n {
			fail("más largo que %v", n)
		}
	case "number", "integer":
		if _, ok := x.(float64); !ok {
			fail("se esperaba número")
		}
	case "boolean":
		if _, ok := x.(bool); !ok {
			fail("se esperaba booleano")
		}
	}
	return errs
}

func TestValidadorMinimo(t *testing.T) {
	v := validador{map[string]any{}}
	s := map[string]any{"type": "object", "additionalProperties": false, "required": []any{"a"},
		"properties": map[string]any{"a": map[string]any{"type": "string", "enum": []any{"x"}}}}
	for _, mal := range []string{`{}`, `{"a":"y"}`, `{"a":"x","b":1}`, `{"a":1}`, `[]`} {
		var x any
		json.Unmarshal([]byte(mal), &x)
		if len(v.check(s, x, "$")) == 0 {
			t.Errorf("el validador dejó pasar %s", mal)
		}
	}
	var ok any
	json.Unmarshal([]byte(`{"a":"x"}`), &ok)
	if e := v.check(s, ok, "$"); len(e) != 0 {
		t.Errorf("rechazó un objeto válido: %v", e)
	}
}

// --- tests de contrato.

func cargarSpec(t *testing.T) validador {
	t.Helper()
	b, err := os.ReadFile("../api/openapi.yaml")
	if err != nil {
		t.Fatal(err)
	}
	d, err := leerYAML(string(b))
	if err != nil {
		t.Fatalf("openapi.yaml: %v", err)
	}
	doc := d.(map[string]any)
	if doc["openapi"] != "3.1.0" {
		t.Fatalf("openapi = %v", doc["openapi"])
	}
	return validador{doc}
}

func ruta(m map[string]any, ks ...string) map[string]any {
	for _, k := range ks {
		m, _ = m[k].(map[string]any)
	}
	return m
}

func TestContratoEjemplos(t *testing.T) {
	v := cargarSpec(t)
	op := ruta(v.doc, "paths", "/v1/decide", "post")
	reqs := ruta(op, "requestBody", "content", "application/json", "examples")
	schemaReq := ruta(op, "requestBody", "content", "application/json", "schema")
	respuestas := ruta(op, "responses")
	if len(reqs) < 5 {
		t.Fatalf("pocos ejemplos de petición: %d", len(reqs))
	}
	_, h := servidorFalso(t, porPregunta{}, Stub{"L1"}, Stub{"L2"}, Stub{"L3"})
	visto := map[string]bool{}
	for nombre, e := range reqs {
		body, _ := json.Marshal(e.(map[string]any)["value"])
		t.Run(nombre, func(t *testing.T) {
			// El esquema de petición acepta los ejemplos buenos y rechaza los malos, igual que el servidor.
			rr := post(h, string(body))
			// Busca el código HTTP cuyo ejemplo lleva este nombre.
			status := ""
			for st, r := range respuestas {
				if ex := ruta(r.(map[string]any), "content", "application/json", "examples", nombre); ex != nil {
					status = st
					var want any = ex["value"]
					var got any
					if err := json.Unmarshal(rr.Body.Bytes(), &got); err != nil {
						t.Fatalf("respuesta no es JSON: %v\n%s", err, rr.Body)
					}
					sch := ruta(r.(map[string]any), "content", "application/json", "schema")
					if errs := v.check(sch, got, "$"); len(errs) != 0 {
						t.Errorf("la respuesta real no valida contra el esquema: %v\n%s", errs, rr.Body)
					}
					if errs := v.check(sch, want, "$"); len(errs) != 0 {
						t.Errorf("el ejemplo de respuesta no valida contra su esquema: %v", errs)
					}
					if st != "200" {
						gc := got.(map[string]any)["error"].(map[string]any)
						wc := want.(map[string]any)["error"].(map[string]any)
						if gc["code"] != wc["code"] || gc["question_id"] != wc["question_id"] {
							t.Errorf("error real %v ≠ ejemplo %v", gc, wc)
						}
					}
				}
			}
			if status == "" {
				t.Fatalf("el ejemplo de petición %q no tiene ejemplo de respuesta del mismo nombre", nombre)
			}
			if fmt.Sprint(rr.Code) != status {
				t.Errorf("HTTP %d, el OpenAPI dice %s: %s", rr.Code, status, rr.Body)
			}
			var x any
			json.Unmarshal(body, &x)
			if aceptado := len(v.check(schemaReq, x, "$")) == 0; aceptado != (status == "200") && nombre != "kind_invalido" && nombre != "opciones_repetidas" {
				t.Errorf("el esquema de petición y el servidor discrepan (esquema acepta=%v, HTTP %s)", aceptado, status)
			}
			visto[nombre] = true
		})
	}
	// Todo ejemplo de respuesta tiene su petición.
	for st, r := range respuestas {
		for n := range ruta(r.(map[string]any), "content", "application/json", "examples") {
			if !visto[n] {
				t.Errorf("ejemplo de respuesta %s/%s sin petición", st, n)
			}
		}
	}
}

func TestContratoEndpoints(t *testing.T) {
	v := cargarSpec(t)
	_, h := servidorFalso(t, Stub{"L0"})
	paths := ruta(v.doc, "paths")
	for _, p := range []string{"/v1/decide", "/healthz", "/metrics"} {
		if paths[p] == nil {
			t.Errorf("%s no está en el OpenAPI", p)
		}
	}
	if len(paths) != 3 {
		t.Errorf("el OpenAPI declara %d rutas, el servidor sirve 3", len(paths))
	}
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, httptest.NewRequest("GET", "/healthz", nil))
	var got any
	json.Unmarshal(rr.Body.Bytes(), &got)
	if e := v.check(ruta(paths, "/healthz", "get", "responses", "200", "content", "application/json", "schema"), got, "$"); len(e) != 0 {
		t.Errorf("healthz: %v", e)
	}
	if ct := rr.Header().Get("Content-Type"); ct != "application/json" {
		t.Errorf("healthz content-type %q", ct)
	}
	rr = httptest.NewRecorder()
	h.ServeHTTP(rr, httptest.NewRequest("GET", "/metrics", nil))
	if !strings.HasPrefix(rr.Header().Get("Content-Type"), "text/plain") {
		t.Errorf("metrics content-type %q", rr.Header().Get("Content-Type"))
	}
	// Los códigos del enum son exactamente las constantes del servidor.
	var enum []string
	for _, c := range ruta(v.doc, "components", "schemas", "ErrorCode")["enum"].([]any) {
		enum = append(enum, c.(string))
	}
	want := []string{ErrJSONInvalido, ErrCuerpoGrande, ErrMetodo, ErrNoEncontrado, ErrSinPreguntas, ErrDemasiadasPreg, ErrEstadoLargo,
		ErrIDFalta, ErrPreguntaFalta, ErrKindFalta, ErrKindInvalido, ErrPocasOpciones, ErrDemasiadasOpc, ErrOpcionesInvalidas,
		ErrOpcionIDFalta, ErrPreguntaIDDup, ErrOpcionIDDup, ErrCampoLargo}
	sort.Strings(enum)
	sort.Strings(want)
	if strings.Join(enum, ",") != strings.Join(want, ",") {
		t.Errorf("enum de ErrorCode ≠ constantes:\n%v\n%v", enum, want)
	}
}

// Los límites por defecto del OpenAPI coinciden con los del servidor.
func TestContratoLimitesPorDefecto(t *testing.T) {
	v := cargarSpec(t)
	sch := ruta(v.doc, "components", "schemas")
	l := LimitesPorDefecto()
	for _, c := range []struct {
		got  float64
		want int
		que  string
	}{
		{ruta(sch, "DecideRequest", "properties", "state")["x-max-bytes"].(float64), l.MaxEstado, "state"},
		{ruta(sch, "DecideRequest", "properties", "questions")["maxItems"].(float64), l.MaxPreguntas, "questions"},
		{ruta(sch, "Question", "properties", "options")["maxItems"].(float64), l.MaxOpciones, "options"},
		{ruta(sch, "Question", "properties", "question")["x-max-bytes"].(float64), l.MaxTexto, "question"},
		{ruta(sch, "Option", "properties", "description")["x-max-bytes"].(float64), l.MaxTexto, "description"},
		{ruta(sch, "Question", "properties", "id")["x-max-bytes"].(float64), l.MaxID, "id"},
	} {
		if int(c.got) != c.want {
			t.Errorf("%s: OpenAPI %v, servidor %d", c.que, c.got, c.want)
		}
	}
}

// Cada código de error del servidor, con su HTTP y su question_id.
func TestHTTPErroresTipados(t *testing.T) {
	_, h := servidorFalso(t, Stub{"L0"})
	srv, hl := servidorFalso(t, Stub{"L0"})
	srv.ConLimites(Limites{MaxCuerpo: 300, MaxPreguntas: 2, MaxOpciones: 3, MaxEstado: 10, MaxTexto: 8, MaxID: 4})
	q := func(extra string) string {
		return `{"questions":[{"id":"1","question":"q","kind":"choice","options":[{"id":"a"},{"id":"b"}]` + extra + `}]}`
	}
	casos := []struct {
		h         http.Handler
		body      string
		status    int
		code, qid string
	}{
		{h, `{`, 400, ErrJSONInvalido, ""},
		{h, `{"questions":[]}`, 400, ErrSinPreguntas, ""},
		{h, `{"questions":[{"question":"q","kind":"noul"}]}`, 400, ErrIDFalta, ""},
		{h, `{"questions":[{"id":"1","kind":"noul"}]}`, 400, ErrPreguntaFalta, "1"},
		{h, `{"questions":[{"id":"1","question":"q"}]}`, 400, ErrKindFalta, "1"},
		{h, `{"questions":[{"id":"1","question":"q","kind":"x"}]}`, 400, ErrKindInvalido, "1"},
		{h, `{"questions":[{"id":"1","question":"q","kind":"score","options":[{"id":"1"}]}]}`, 400, ErrPocasOpciones, "1"},
		{h, `{"questions":[{"id":"1","question":"q","kind":"noul","options":[{"id":"si"},{"id":"no"}]}]}`, 400, ErrOpcionesInvalidas, "1"},
		{h, `{"questions":[{"id":"1","question":"q","kind":"choice","options":[{"id":"a"},{"id":""}]}]}`, 400, ErrOpcionIDFalta, "1"},
		{h, `{"questions":[{"id":"1","question":"q","kind":"choice","options":[{"id":"a"},{"id":"a"}]}]}`, 400, ErrOpcionIDDup, "1"},
		{h, `{"questions":[{"id":"1","question":"q","kind":"noul"},{"id":"1","question":"q","kind":"noul"}]}`, 400, ErrPreguntaIDDup, "1"},
		{h, `{"state":"` + strings.Repeat("x", MaxEstadoByte+1) + `","questions":[{"id":"1","question":"q","kind":"noul"}]}`, 400, ErrEstadoLargo, ""},
		{h, `{"questions":[{"id":"1","question":"` + strings.Repeat("x", MaxTextoByte+1) + `","kind":"noul"}]}`, 400, ErrCampoLargo, "1"},
		{h, `{"questions":[{"id":"1","question":"q","kind":"choice","options":[{"id":"a","description":"` + strings.Repeat("x", MaxTextoByte+1) + `"},{"id":"b"}]}]}`, 400, ErrCampoLargo, "1"},
		{h, `{"state":"` + strings.Repeat("x", MaxCuerpo) + `","questions":[]}`, 413, ErrCuerpoGrande, ""},
		// límites configurados
		{hl, `{"state":"12345678901","questions":[{"id":"1","question":"q","kind":"noul"}]}`, 400, ErrEstadoLargo, ""},
		{hl, `{"questions":[{"id":"1","question":"q","kind":"noul"},{"id":"2","question":"q","kind":"noul"},{"id":"3","question":"q","kind":"noul"}]}`, 400, ErrDemasiadasPreg, ""},
		{hl, `{"questions":[{"id":"1","question":"q","kind":"choice","options":[{"id":"a"},{"id":"b"},{"id":"c"},{"id":"d"}]}]}`, 400, ErrDemasiadasOpc, "1"},
		{hl, `{"questions":[{"id":"1","question":"123456789","kind":"noul"}]}`, 400, ErrCampoLargo, "1"},
		{hl, `{"questions":[{"id":"12345","question":"q","kind":"noul"}]}`, 400, ErrCampoLargo, ""},
		{hl, q(`,"nonce":"12345"`), 400, ErrCampoLargo, "1"},
		{hl, `{"state":"` + strings.Repeat("x", 300) + `"}`, 413, ErrCuerpoGrande, ""},
	}
	for i, c := range casos {
		rr := post(c.h, c.body)
		var got errorHTTP
		if err := json.Unmarshal(rr.Body.Bytes(), &got); err != nil {
			t.Errorf("caso %d: cuerpo no JSON: %s", i, rr.Body)
			continue
		}
		if rr.Code != c.status || got.Error.Code != c.code || got.Error.QuestionID != c.qid || got.Error.Message == "" {
			t.Errorf("caso %d: %d %+v, esperaba %d %s question_id=%q", i, rr.Code, got.Error, c.status, c.code, c.qid)
		}
		if ct := rr.Header().Get("Content-Type"); ct != "application/json" {
			t.Errorf("caso %d: content-type %q", i, ct)
		}
	}
	for _, c := range []struct {
		método, ruta string
		status       int
		code         string
	}{{"GET", "/v1/decide", 405, ErrMetodo}, {"GET", "/nada", 404, ErrNoEncontrado}} {
		rr := httptest.NewRecorder()
		h.ServeHTTP(rr, httptest.NewRequest(c.método, c.ruta, nil))
		var got errorHTTP
		json.Unmarshal(rr.Body.Bytes(), &got)
		if rr.Code != c.status || got.Error.Code != c.code {
			t.Errorf("%s %s → %d %s", c.método, c.ruta, rr.Code, rr.Body)
		}
	}
}

// Lo que acepta hoy no se rompe: ids de score, noul sin opciones, límites a 0 = por defecto.
func TestHTTPCompatibilidad(t *testing.T) {
	srv, h := servidorFalso(t, porPregunta{})
	srv.ConLimites(Limites{})
	if srv.lim != LimitesPorDefecto() {
		t.Fatalf("ConLimites(0) debía dejar los valores por defecto: %+v", srv.lim)
	}
	for _, b := range []string{
		`{"questions":[{"id":"1","question":"q","kind":"noul"}]}`,
		`{"questions":[{"id":"1","question":"q","kind":"score","options":[{"id":"1"},{"id":"2"}]}]}`,
		`{"questions":[{"id":"1","question":"q","kind":"choice","options":[{"id":"a"},{"id":"b"}],"nonce":"` + strings.Repeat("n", MaxIDByte) + `"}]}`,
	} {
		if rr := post(h, b); rr.Code != 200 {
			t.Errorf("%s → %d %s", b, rr.Code, rr.Body)
		}
	}
	cfg := ConfigPorDefecto()
	cfg.Limites.MaxOpciones = -1
	if cfg.Validar() == nil {
		t.Error("un límite negativo debía invalidar la config")
	}
}
