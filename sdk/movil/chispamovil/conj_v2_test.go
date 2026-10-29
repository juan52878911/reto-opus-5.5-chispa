package chispamovil

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"chispa/format/chispa3"
)

// El fichero que escribió `chispa train --conjunta` (lo versiona el servidor): ESQUEMAS v2 y CONJ v2.
const ficheroConjV2 = "../../../server/decide/testdata/conj-v2.chispa"

func TestAvisoSiEsquemasYConjDifierenDeVersion(t *testing.T) {
	c, err := Abrir(ficheroConjV2)
	if err != nil {
		t.Fatal(err)
	}
	if !c.TieneConj() || strings.Contains(c.Avisos(), "CONJ v") {
		t.Fatalf("fichero consistente: conj=%v avisos=%q", c.TieneConj(), c.Avisos())
	}
	c.Cerrar()

	f, err := chispa3.Abrir(ficheroConjV2)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	esq1, err := chispa3.CodificarEsquemas(256, []chispa3.EntradaEsquema{
		{Hash: chispa3.HashEsquema("¿Qué tan urgente es?", []string{"alta", "baja"}), Escala: 1, Vec: make([]int8, 256)}})
	if err != nil {
		t.Fatal(err)
	}
	var secs []chispa3.Seccion
	for _, tp := range f.Tipos() {
		b, err := f.Bytes(tp)
		if err != nil {
			t.Fatal(err)
		}
		if tp == chispa3.ESQUEMAS {
			b = esq1
		}
		secs = append(secs, chispa3.Seccion{Tipo: tp, Datos: b})
	}
	var buf bytes.Buffer
	if err := chispa3.Escribir(&buf, secs); err != nil {
		t.Fatal(err)
	}
	ruta := filepath.Join(t.TempDir(), "mixto.chispa")
	if err := os.WriteFile(ruta, buf.Bytes(), 0o600); err != nil {
		t.Fatal(err)
	}
	c, err = Abrir(ruta)
	if err != nil {
		t.Fatal(err)
	}
	defer c.Cerrar()
	if !strings.Contains(c.Avisos(), "ESQUEMAS v1 y CONJ v2") {
		t.Fatalf("sin aviso de versiones distintas: %q", c.Avisos())
	}
}
