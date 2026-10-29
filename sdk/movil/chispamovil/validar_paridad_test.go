package chispamovil

import (
	"encoding/json"
	"strings"
	"testing"
)

// R5 hallazgo 8: casos que server/decide rechaza con 400 deben fallar también en el motor móvil.
func TestValidarParidadServidor(t *testing.T) {
	op := `[{"id":"a"},{"id":"b"}]`
	q := func(kind, texto, nonce, ops string) string {
		b, _ := json.Marshal(texto)
		return `{"kind":"` + kind + `","question":` + string(b) + `,"nonce":"` + nonce + `","options":` + ops + `}`
	}
	largo := func(n int) string { return strings.Repeat("x", n) }
	casos := map[string]string{
		"missing_kind":      q("", "hola", "", op),
		"question_vacia":    q("choice", "", "", op),
		"question_larga":    q("choice", largo(4097), "", op),
		"nonce_largo":       q("choice", "hola", largo(257), op),
		"opcion_id_largo":   q("choice", "hola", "", `[{"id":"`+largo(257)+`"},{"id":"b"}]`),
		"opcion_desc_larga": q("score", "hola", "", `[{"id":"a","description":"`+largo(4097)+`"},{"id":"b"}]`),
		"kind_invalido":     q("otro", "hola", "", op),
	}
	for n, js := range casos {
		if _, err := leerPregunta(js); err == nil {
			t.Errorf("%s: el servidor rechaza y el motor móvil acepta", n)
		}
	}
	// en el límite exacto el servidor acepta
	if _, err := leerPregunta(q("choice", largo(4096), largo(256), `[{"id":"`+largo(256)+`","description":"`+largo(4096)+`"},{"id":"b"}]`)); err != nil {
		t.Errorf("límite exacto debe aceptarse: %v", err)
	}
	// bytes, no runas: 2049 'é' = 4098 bytes
	if _, err := leerPregunta(q("choice", strings.Repeat("é", 2049), "", op)); err == nil {
		t.Error("el tope es en bytes")
	}
}
