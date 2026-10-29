package chispamovil

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"chispa/format/chispa3"
)

// ficheroSopl escribe un .chispa con SOPL1 y CALIB con (o sin, si lc es nil) l1_lambda_calib.
func ficheroSopl(t *testing.T, lc *float64) string {
	t.Helper()
	meta := metaYCalib(t)[0]
	calib, err := chispa3.Calib{TauEscalate: 0.42, L1LambdaCalib: lc,
		Tipos: map[string]chispa3.ParamsTipo{"choice": {T: 0.1, A: 1, B: 0, Theta: .5}}}.Codificar()
	if err != nil {
		t.Fatal(err)
	}
	sopl, err := chispa3.CodificarSopl1(4, []chispa3.EntradaSopl1{{Hash: [32]byte{1}, Ids: []string{"a", "b"},
		K: []uint32{1, 0}, Escala: []float32{0, 0}, Media: make([]int8, 8)}})
	if err != nil {
		t.Fatal(err)
	}
	var buf bytes.Buffer
	if err := chispa3.Escribir(&buf, []chispa3.Seccion{meta, {Tipo: chispa3.CALIB, Datos: calib}, {Tipo: chispa3.SOPL1, Datos: sopl}}); err != nil {
		t.Fatal(err)
	}
	ruta := filepath.Join(t.TempDir(), "c.chispa")
	if err := os.WriteFile(ruta, buf.Bytes(), 0o600); err != nil {
		t.Fatal(err)
	}
	return ruta
}

func TestLambdaCalibTresCasos(t *testing.T) {
	cuatro, tres := 4.0, 3.0
	// con campo y mismo λ: activo, sin aviso
	c, err := Abrir(ficheroSopl(t, &cuatro))
	if err != nil || c.sopl == nil || c.lambdaL1 == nil || *c.lambdaL1 != 4 || c.Avisos() != "" {
		t.Fatalf("mismo λ: %v sopl=%v avisos=%q", err, c.sopl, c.Avisos())
	}
	c.Cerrar()
	// con campo y λ distinto: activo con aviso
	c, err = Abrir(ficheroSopl(t, &tres))
	if err != nil || c.sopl == nil || !strings.Contains(c.Avisos(), "l1_lambda_calib=3") {
		t.Fatalf("λ distinto: %v sopl=%v avisos=%q", err, c.sopl, c.Avisos())
	}
	c.Cerrar()
	// sin campo: apagado con Abrir (default); λ explícito se respeta, con aviso
	c, err = Abrir(ficheroSopl(t, nil))
	if err != nil || c.sopl != nil || c.lambdaL1 != nil || !strings.Contains(c.Avisos(), "sin encogimiento") {
		t.Fatalf("sin campo: %v sopl=%v avisos=%q", err, c.sopl, c.Avisos())
	}
	c.Cerrar()
	c, err = AbrirConSoporte(ficheroSopl(t, nil), 4, SoporteApagado)
	if err != nil || c.sopl == nil || c.lambdaL1 == nil || !strings.Contains(c.Avisos(), "sin encogimiento") {
		t.Fatalf("explícito sin campo: %v sopl=%v avisos=%q", err, c.sopl, c.Avisos())
	}
	c.Cerrar()
}
