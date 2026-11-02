package chispa3

import (
	"bytes"
	"errors"
	"os"
	"path/filepath"
	"testing"
)

func abrirConMeta(t *testing.T, meta string) *Fichero {
	t.Helper()
	var buf bytes.Buffer
	secs := []Seccion{{Tipo: L2, Datos: []byte("x")}}
	if meta != "" {
		secs = append([]Seccion{{Tipo: META, Datos: []byte(meta)}}, secs...)
	}
	if err := Escribir(&buf, secs); err != nil {
		t.Fatal(err)
	}
	ruta := filepath.Join(t.TempDir(), "m.chispa")
	if err := os.WriteFile(ruta, buf.Bytes(), 0o600); err != nil {
		t.Fatal(err)
	}
	f, err := Abrir(ruta)
	if err != nil {
		t.Fatal(err)
	}
	return f
}

// VersionTextoTorre lee solo texto_torre: tolera licencias anidadas, dorado libre y campos desconocidos.
func TestVersionTextoTorreTolerante(t *testing.T) {
	libre := `"licencias":{"massive":{"licencia":"CC-BY"}},"dorado":"dorado/v3.jsonl","otro":1`
	for meta, want := range map[string]string{
		"":                                   TextoTorreV1,
		`{"version":1,` + libre + `}`:        TextoTorreV1,
		`{"texto_torre":"v1",` + libre + `}`: TextoTorreV1,
		`{"texto_torre":"v2_sin_id",` + libre + `}`: TextoTorreV2SinID,
	} {
		got, err := abrirConMeta(t, meta).VersionTextoTorre()
		if err != nil || got != want {
			t.Errorf("%q: %q, %v (quería %q)", meta, got, err, want)
		}
	}
	for _, meta := range []string{`{"texto_torre":"v9"}`, `{"texto_torre":3}`, `no json`} {
		if _, err := abrirConMeta(t, meta).VersionTextoTorre(); !errors.Is(err, ErrContenido) {
			t.Errorf("%q: error %v", meta, err)
		}
	}
}
