package main

import (
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"

	"github.com/juan52878911/chispa/server/decide"
)

// ZH: el tope de tamaño del .chispa se configura con max_fichero (bytes); sin la clave sigue siendo 1 GiB.
func TestMaxFicheroConfig(t *testing.T) {
	const modelo = "../../testdata/urgencia.chispa"
	st, err := os.Stat(modelo)
	if err != nil {
		t.Fatal(err)
	}
	pequeno := strconv.FormatInt(st.Size()-1, 10) // un tope pequeño de test: el fichero lo supera sin generar nada grande
	dir := t.TempDir()
	armar := func(modelo, extra string) error {
		p := filepath.Join(dir, "c.json")
		if err := os.WriteFile(p, []byte(`{"cache_esquemas":8`+extra+`}`), 0o600); err != nil {
			t.Fatal(err)
		}
		a, err := armarModelo(decide.NuevasMetricas(), p, modelo, "")
		if err == nil && a.Cerrar != nil {
			a.Cerrar()
		}
		return err
	}
	if c := decide.ConfigPorDefecto(); c.MaxFicheroBytes() != 1<<30 {
		t.Fatalf("el tope por defecto cambió: %d", c.MaxFicheroBytes())
	}
	if err := armar(modelo, ""); err != nil {
		t.Fatalf("con el tope por defecto debe cargar: %v", err)
	}
	err = armar(modelo, `,"max_fichero":`+pequeno)
	if err == nil {
		t.Fatal("un fichero mayor que el tope debe rechazarse")
	}
	for _, q := range []string{`"max_fichero"`, pequeno + " bytes", "de max_fichero"} {
		if !strings.Contains(err.Error(), q) {
			t.Errorf("el error no dice %q: %v", q, err)
		}
	}
	if err := armar(modelo, `,"max_fichero":`+strconv.FormatInt(st.Size(), 10)); err != nil {
		t.Fatalf("al subir el tope debe cargar: %v", err)
	}
	for _, v := range []string{"0", "-5"} {
		if err := armar("", `,"max_fichero":`+v); err == nil || !strings.Contains(err.Error(), "max_fichero debe ser > 0") {
			t.Errorf("max_fichero %s debe fallar con un mensaje claro: %v", v, err)
		}
	}
}
