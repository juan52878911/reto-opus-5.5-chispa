package decide

import (
	"encoding/json"
	"testing"
)

// R9 #11: HashEsquema2 separa con 0x1d/0x1e/0x1f sin prefijos de longitud; un texto con ellos daría la clave de otro esquema.
func TestRechazaSeparadoresDeClave(t *testing.T) {
	_, h := servidorFalso(t, Stub{"L0"})
	casos := map[string]struct {
		body string
		code string
	}{
		"pregunta":    {`{"questions":[{"id":"1","question":"a\u001db","kind":"choice","options":[{"id":"a"},{"id":"b"}]}]}`, ErrCampoLargo},
		"id opción":   {`{"questions":[{"id":"1","question":"q","kind":"choice","options":[{"id":"a\u001e"},{"id":"b"}]}]}`, ErrOpcionesInvalidas},
		"descripción": {`{"questions":[{"id":"1","question":"q","kind":"choice","options":[{"id":"a","description":"x\u001db\u001ey"},{"id":"b"}]}]}`, ErrOpcionesInvalidas},
		"desc 0x1f":   {`{"questions":[{"id":"1","question":"q","kind":"multi","options":[{"id":"a","description":"\u001f"},{"id":"b"}]}]}`, ErrOpcionesInvalidas},
	}
	for nombre, c := range casos {
		rr := post(h, c.body)
		var got errorHTTP
		_ = json.Unmarshal(rr.Body.Bytes(), &got)
		if rr.Code != 400 || got.Error.Code != c.code {
			t.Errorf("%s: %d %s, quiero 400 %s", nombre, rr.Code, rr.Body.String(), c.code)
		}
	}
	// Control: otros caracteres de control y tab no se rechazan por esto.
	rr := post(h, `{"questions":[{"id":"1","question":"a\u001cb\tc","kind":"noul"}]}`)
	if rr.Code != 200 {
		t.Errorf("0x1c y tab deben pasar: %d %s", rr.Code, rr.Body.String())
	}
}
