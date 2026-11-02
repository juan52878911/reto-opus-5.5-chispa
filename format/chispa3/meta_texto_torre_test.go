package chispa3

import (
	"errors"
	"strings"
	"testing"
)

func TestMetaTextoTorre(t *testing.T) {
	casos := []struct{ json, quiere string }{
		{`{"version":1}`, TextoTorreV1},
		{`{"version":1,"texto_torre":"v1"}`, TextoTorreV1},
		{`{"version":1,"texto_torre":"v2_sin_id"}`, TextoTorreV2SinID},
	}
	for _, c := range casos {
		m, err := DecodificarMetaTexto([]byte(c.json))
		if err != nil || m.VersionTextoTorre() != c.quiere {
			t.Errorf("%s: %q, %v; quiere %q", c.json, m.VersionTextoTorre(), err, c.quiere)
		}
	}
	for _, j := range []string{`{"version":1,"texto_torre":"v3"}`, `{"version":1,"texto_torre":"V1"}`} {
		_, err := DecodificarMetaTexto([]byte(j))
		if !errors.Is(err, ErrContenido) || !strings.Contains(err.Error(), "texto_torre") {
			t.Errorf("%s: error %v, quería ErrContenido sobre texto_torre", j, err)
		}
	}
	b, err := MetaTexto{Meta: Meta{Version: 1}, TextoTorre: TextoTorreV2SinID}.Codificar()
	if err != nil || !strings.Contains(string(b), `"texto_torre":"v2_sin_id"`) {
		t.Errorf("Codificar: %s, %v", b, err)
	}
	if b, _ = (Meta{Version: 1}).Codificar(); strings.Contains(string(b), "texto_torre") {
		t.Errorf("v1 implícito no debería escribirse: %s", b)
	}
	if _, err := (MetaTexto{Meta: Meta{Version: 1}, TextoTorre: "x"}).Codificar(); err == nil {
		t.Error("Codificar acepta valor desconocido")
	}
}
