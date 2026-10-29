package chispamovil

import (
	"bytes"
	"crypto/sha256"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"chispa/format/chispa3"
)

func abrirSecciones(t *testing.T, secs ...chispa3.Seccion) (*Chispa, error) {
	t.Helper()
	var buf bytes.Buffer
	if err := chispa3.Escribir(&buf, append(metaYCalib(t), secs...)); err != nil {
		t.Fatal(err)
	}
	ruta := filepath.Join(t.TempDir(), "m.chispa")
	if err := os.WriteFile(ruta, buf.Bytes(), 0o600); err != nil {
		t.Fatal(err)
	}
	c, err := Abrir(ruta)
	if err == nil {
		t.Cleanup(func() { c.Cerrar() })
	}
	return c, err
}

// Hallazgo 9: leerPregunta valida como el servidor.
func TestR1LeerPreguntaValida(t *testing.T) {
	malas := map[string]string{
		"ids repetidos":      `{"question":"q","kind":"choice","options":[{"id":"a"},{"id":"a"},{"id":"b"}]}`,
		"id vacío":           `{"question":"q","kind":"choice","options":[{"id":""},{"id":"b"}]}`,
		"una sola opción":    `{"question":"q","kind":"choice","options":[{"id":"a"}]}`,
		"score una opción":   `{"question":"q","kind":"score","options":[{"id":"1"}]}`,
		"noul si/no":         `{"question":"q","kind":"noul","options":[{"id":"si"},{"id":"no"}]}`,
		"noul tres":          `{"question":"q","kind":"noul","options":[{"id":"true"},{"id":"false"},{"id":"x"}]}`,
		"noul true repetido": `{"question":"q","kind":"noul","options":[{"id":"true"},{"id":"true"}]}`,
		"demasiadas":         `{"question":"q","kind":"choice","options":[` + strings.TrimSuffix(strings.Repeat(`{"id":"x"},`, 1), ",") + `]}`,
	}
	var sb strings.Builder
	for i := 0; i <= maxOpciones; i++ {
		fmt.Fprintf(&sb, `{"id":"o%d"},`, i)
	}
	malas["demasiadas"] = `{"question":"q","kind":"choice","options":[` + strings.TrimSuffix(sb.String(), ",") + `]}`
	for n, js := range malas {
		if _, err := leerPregunta(js); err == nil {
			t.Errorf("%s: debía rechazarse", n)
		}
	}
	for n, js := range map[string]string{
		"choice":   `{"question":"q","kind":"choice","options":[{"id":"a"},{"id":"b"}]}`,
		"noul":     `{"question":"q","kind":"noul","options":[{"id":"true"},{"id":"false"}]}`,
		"sin kind": `{"question":"q","options":[{"id":"a"},{"id":"b"}]}`,
		"score":    `{"question":"q","kind":"score","options":[{"id":"1"},{"id":"2"},{"id":"3"}]}`,
	} {
		if _, err := leerPregunta(js); err != nil {
			t.Errorf("%s: %v", n, err)
		}
	}
	p, err := leerPregunta(`{"question":"q","kind":"noul"}`)
	if err != nil || len(p.Opciones) != 2 {
		t.Fatalf("noul vacío debía tomar false/true: %v %v", p.Opciones, err)
	}
}

// Hallazgo 4: TORR v1 exige «passage: »; el error nombra versión y prefijo.
func TestR1PrefijoTORR(t *testing.T) {
	for _, pref := range []string{"", "query: ", "passage:"} {
		tb, err := chispa3.CodificarTORR(chispa3.Torre{Dim: 4, MaxLen: 8, Prefijo: pref, ONNX: []byte("x")})
		if err != nil {
			t.Fatal(err)
		}
		_, err = abrirSecciones(t, chispa3.Seccion{Tipo: chispa3.TORR, Datos: tb})
		want := fmt.Sprintf("TORR v1: prefijo %q no válido; se espera \"passage: \"", pref)
		if err == nil || !strings.Contains(err.Error(), want) {
			t.Errorf("prefijo %q: error %v, quería %q", pref, err, want)
		}
	}
	tb, _ := chispa3.CodificarTORR(chispa3.Torre{Dim: 4, MaxLen: 8, Prefijo: "passage: ", ONNX: []byte("x")})
	tb[0] = 7
	if _, err := abrirSecciones(t, chispa3.Seccion{Tipo: chispa3.TORR, Datos: tb}); err == nil || !strings.Contains(err.Error(), "7") {
		t.Errorf("versión desconocida debía fallar nombrando 7: %v", err)
	}
	if err := validarPrefijoVersion(2, "x"); err == nil || !strings.Contains(err.Error(), "v2") {
		t.Errorf("v2 desconocida: %v", err)
	}
}

// Hallazgo 3: ExtraerL2 reemplaza el destino por rename (no lo trunca in situ) y no deja temporales.
func TestR1ExtraerL2Atomico(t *testing.T) {
	onnx := bytes.Repeat([]byte("nuevo"), 1000)
	c, err := abrirSecciones(t, chispa3.Seccion{Tipo: chispa3.L2, Datos: onnx})
	if err != nil {
		t.Fatal(err)
	}
	dir := t.TempDir()
	dst := filepath.Join(dir, "l2.onnx")
	if err := os.WriteFile(dst, []byte("viejo-completo"), 0o600); err != nil {
		t.Fatal(err)
	}
	lector, err := os.Open(dst) // quien ya tiene abierto el ONNX viejo no ve bytes a medias
	if err != nil {
		t.Fatal(err)
	}
	defer lector.Close()
	if err := c.ExtraerL2(dst); err != nil {
		t.Fatal(err)
	}
	if b, _ := os.ReadFile(dst); !bytes.Equal(b, onnx) {
		t.Fatal("destino sin el ONNX nuevo")
	}
	buf := make([]byte, 64)
	n, _ := lector.Read(buf)
	if string(buf[:n]) != "viejo-completo" {
		t.Fatalf("el destino se truncó in situ: %q", buf[:n])
	}
	es, _ := os.ReadDir(dir)
	if len(es) != 1 {
		t.Fatalf("temporales sobrantes: %v", es)
	}
	if err := c.ExtraerL2(filepath.Join(dir, "no", "existe.onnx")); err == nil {
		t.Fatal("directorio inexistente debía fallar")
	}
}

func TestR1HashSeccionYTauL2c(t *testing.T) {
	onnx := []byte("onnx-l2")
	c, err := abrirSecciones(t, chispa3.Seccion{Tipo: chispa3.L2, Datos: onnx})
	if err != nil {
		t.Fatal(err)
	}
	if h := c.HashSeccion(int(chispa3.L2)); h != fmt.Sprintf("%x", sha256sum(onnx)) {
		t.Fatalf("hash L2 %q", h)
	}
	if c.HashSeccion(int(chispa3.TORR)) != "" {
		t.Fatal("sección ausente debía dar \"\"")
	}
	if c.TauL2c() != -1 || c.TauL2EsquemaNuevo() != -1 {
		t.Fatalf("sin tau_l2c: %v, %v", c.TauL2c(), c.TauL2EsquemaNuevo())
	}
	tau, tauNuevo := 0.9, 0.3
	calib, _ := chispa3.Calib{TauEscalate: 0.6, TauL2c: &tau, TauL2EsquemaNuevo: &tauNuevo, Tipos: map[string]chispa3.ParamsTipo{"choice": {T: 0.1, A: 1, Theta: .5}}}.Codificar()
	var buf bytes.Buffer
	if err := chispa3.Escribir(&buf, []chispa3.Seccion{metaYCalib(t)[0], {Tipo: chispa3.CALIB, Datos: calib}}); err != nil {
		t.Fatal(err)
	}
	ruta := filepath.Join(t.TempDir(), "t.chispa")
	os.WriteFile(ruta, buf.Bytes(), 0o600)
	c2, err := Abrir(ruta)
	if err != nil {
		t.Fatal(err)
	}
	defer c2.Cerrar()
	if c2.TauL2c() != 0.9 || c2.TauEscalate() != 0.6 || c2.TauL2EsquemaNuevo() != 0.3 {
		t.Fatalf("tau_l2c %v, nuevo %v", c2.TauL2c(), c2.TauL2EsquemaNuevo())
	}
}

// Hallazgo 15: al pasar de maxDin se desalojan las torres más antiguas, no todas.
func TestR1DynLRU(t *testing.T) {
	c := &Chispa{tieneL2: true}
	torres := func(d int) []byte { return make([]byte, 4*2*d) }
	preg := func(i int) string {
		return fmt.Sprintf(`{"question":"q%d","kind":"choice","options":[{"id":"a"},{"id":"b"}]}`, i)
	}
	inst := func(i int) {
		if !c.InstalarTorresL2(preg(i), torres(4), 2) {
			t.Fatalf("instalar %d", i)
		}
	}
	for i := 0; i < 400; i++ {
		inst(i)
	}
	inst(1000)                 // «A»: instalada por un hilo
	for i := 0; i < 112; i++ { // «B» desborda maxDin (1024)
		inst(2000 + i)
	}
	if len(c.dyn) > maxDin {
		t.Fatalf("dyn %d > %d", len(c.dyn), maxDin)
	}
	p, _ := leerPregunta(preg(1000))
	if _, err := c.torresNuevas(p); err != nil {
		t.Fatalf("las torres de A se perdieron: %v", err)
	}
	p, _ = leerPregunta(preg(0))
	if _, err := c.torresNuevas(p); err == nil {
		t.Fatal("la más antigua debía haberse desalojado")
	}
}

func sha256sum(b []byte) [32]byte { return sha256.Sum256(b) }
