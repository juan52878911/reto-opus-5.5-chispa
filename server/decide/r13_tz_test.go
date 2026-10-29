package decide

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// R13: el servidor da too_many_options antes que los errores de la pregunta; los SDK (Go, JS, móvil) deben dar lo mismo.
// Esta tabla es la misma que usan sus tests de orden.
func TestR13TooManyOptionsAntesQueErroresDePregunta(t *testing.T) {
	srv, h := servidorFalso(t, Stub{"L0"})
	srv.ConLimites(Limites{MaxCuerpo: 1 << 16, MaxPreguntas: 8, MaxOpciones: 3, MaxEstado: 100, MaxTexto: 100, MaxID: 20})
	cuatro := `[{"id":"a"},{"id":"b"},{"id":"c"},{"id":"d"}]`
	casos := []struct{ body, qid string }{
		{`{"questions":[{"id":"1","question":"q","options":` + cuatro + `}]}`, "1"},
		{`{"questions":[{"question":"q","kind":"noul"},{"id":"2","question":"q","kind":"choice","options":` + cuatro + `}]}`, "2"},
		{`{"questions":[{"id":"1","question":"q","kind":"noul","options":` + cuatro + `}]}`, "1"},
	}
	for _, c := range casos {
		w := httptest.NewRecorder()
		h.ServeHTTP(w, httptest.NewRequest("POST", "/v1/decide", strings.NewReader(c.body)))
		b := w.Body.String()
		if w.Code != http.StatusBadRequest || !strings.Contains(b, ErrDemasiadasOpc) || !strings.Contains(b, `"question_id":"`+c.qid+`"`) {
			t.Errorf("%.70s: %d %s", c.body, w.Code, b)
		}
	}
}
