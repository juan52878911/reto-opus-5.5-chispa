package chispa3

import (
	"bytes"
	"errors"
	"math"
	"testing"
)

func datosL0TF(f16 bool) *DatosL0TF {
	d := &DatosL0TF{Etiquetas: []string{"a", "z", "ñu"}, F16: f16}
	d.Vocab = []string{" a", " ab", "a ", "ab", "b ", "ñ "}
	// orden por bytes: " a" < " ab" < "a " < "ab" < "b " < "ñ "
	for i := range d.Vocab {
		d.IDF = append(d.IDF, 1+float32(i)/4)
		for c := 0; c < 3; c++ {
			d.Coef = append(d.Coef, float32(i-c)*0.37)
		}
	}
	d.Inter = []float32{0.1, -0.2, 0.3}
	return d
}

func TestL0TFIdaYVuelta(t *testing.T) {
	for _, f16 := range []bool{false, true} {
		d := datosL0TF(f16)
		b, err := CodificarL0TF(d)
		if err != nil {
			t.Fatal(err)
		}
		m, err := DecodificarL0TF(b)
		if err != nil {
			t.Fatal(err)
		}
		if m.NumNGramas() != 6 || m.NumClases() != 3 {
			t.Fatal("tamaños")
		}
		re, err := CodificarL0TF(m.Datos())
		if err != nil || !bytes.Equal(re, b) {
			t.Fatalf("ida y vuelta f16=%v: %v", f16, err)
		}
		p := m.Probs("ab Ab ñ")
		var s float64
		for _, x := range p {
			s += x
		}
		if math.Abs(s-1) > 1e-12 {
			t.Fatalf("suma %v", s)
		}
	}
}

func TestL0TFEnFichero(t *testing.T) {
	b, _ := CodificarL0TF(datosL0TF(false))
	sin := seccionesDePrueba(t)
	con := append(append([]Seccion(nil), sin...), Seccion{L0TF, b})
	if L0TF.String() != "L0TF" || L0TF != 8 {
		t.Fatal("L0TF debe ser el tipo 8")
	}
	f, err := Desde(construir(t, sin), Limites{})
	if err != nil {
		t.Fatal(err)
	}
	if f.Tiene(L0TF) {
		t.Fatal("sin L0TF")
	}
	if _, err := f.L0TF(); !errors.Is(err, ErrNoHay) {
		t.Fatalf("ErrNoHay, no %v", err)
	}
	f, err = Desde(construir(t, con), Limites{})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := f.L0TF(); err != nil {
		t.Fatal(err)
	}
	for _, s := range sin { // las secciones antiguas conservan sus bytes
		x, err := f.Bytes(s.Tipo)
		if err != nil || !bytes.Equal(x, s.Datos) {
			t.Fatalf("%v cambió", s.Tipo)
		}
	}
}

func TestL0TFInvalido(t *testing.T) {
	bueno, _ := CodificarL0TF(datosL0TF(false))
	cambia := func(f func(*DatosL0TF)) *DatosL0TF { d := datosL0TF(false); f(d); return d }
	for nombre, d := range map[string]*DatosL0TF{
		"vocabulario desordenado": cambia(func(d *DatosL0TF) { d.Vocab[0], d.Vocab[1] = d.Vocab[1], d.Vocab[0] }),
		"n-grama de 1":            cambia(func(d *DatosL0TF) { d.Vocab[0] = "a" }),
		"n-grama de 6":            cambia(func(d *DatosL0TF) { d.Vocab[5] = "ñabcde" }),
		"etiquetas repetidas":     cambia(func(d *DatosL0TF) { d.Etiquetas[1] = "a" }),
		"una clase":               cambia(func(d *DatosL0TF) { d.Etiquetas = d.Etiquetas[:1] }),
		"idf cero":                cambia(func(d *DatosL0TF) { d.IDF[2] = 0 }),
		"coef NaN":                cambia(func(d *DatosL0TF) { d.Coef[3] = float32(math.NaN()) }),
		"coef fuera de f16":       cambia(func(d *DatosL0TF) { d.F16 = true; d.Coef[3] = 1e6 }),
		"tamaño de coef":          cambia(func(d *DatosL0TF) { d.Coef = d.Coef[1:] }),
	} {
		if _, err := CodificarL0TF(d); !errors.Is(err, ErrContenido) {
			t.Errorf("%s: %v", nombre, err)
		}
	}
	for n := 0; n < len(bueno); n++ { // todo prefijo propio es inválido
		if _, err := DecodificarL0TF(bueno[:n]); err == nil {
			t.Fatalf("prefijo de %d bytes aceptado", n)
		}
	}
	if _, err := DecodificarL0TF(append(append([]byte(nil), bueno...), 0)); err == nil {
		t.Fatal("bytes sobrantes")
	}
	mal := append([]byte(nil), bueno...)
	mal[0] = 2
	if _, err := DecodificarL0TF(mal); !errors.Is(err, ErrContenido) {
		t.Fatal("versión")
	}
}

func TestF16(t *testing.T) {
	for h := 0; h < 1<<16; h++ {
		x := f16aF32(uint16(h))
		if math.IsNaN(float64(x)) {
			continue
		}
		if g := f32aF16(x); g != uint16(h) {
			t.Fatalf("%#04x → %v → %#04x", h, x, g)
		}
	}
	for _, c := range []struct {
		x float32
		h uint16
	}{{1, 0x3c00}, {-2, 0xc000}, {65504, 0x7bff}, {65520, 0x7c00}, {1e-8, 0}, {5.9604645e-8, 1}, {0.1, 0x2e66}} {
		if g := f32aF16(c.x); g != c.h {
			t.Errorf("%v → %#04x, quiero %#04x", c.x, g, c.h)
		}
	}
}

func TestMinusculasPy(t *testing.T) {
	for in, want := range map[string]string{
		"ÁÉÑ Ü": "áéñ ü", "İstanbul": "i̇stanbul", "ΟΔΟΣ ΣΟΦΟΣ.": "οδος σοφος.", "Σ": "σ", "aΣ": "aς", "AΣb": "aσb",
		"😀 ÀB": "😀 àb", "ǅ": "ǆ",
	} {
		if got := minusculasPy(in); got != want {
			t.Errorf("%q → %q, quiero %q", in, got, want)
		}
	}
}

func FuzzL0TF(f *testing.F) {
	for _, f16 := range []bool{false, true} {
		b, _ := CodificarL0TF(datosL0TF(f16))
		f.Add(b)
	}
	f.Add([]byte{})
	f.Fuzz(func(t *testing.T, data []byte) {
		m, err := DecodificarL0TF(data)
		if err != nil {
			return
		}
		re, err := CodificarL0TF(m.Datos())
		if err != nil || !bytes.Equal(re, data) {
			t.Fatalf("lo aceptado no recodifica igual: %v", err)
		}
		p := m.Probs("Hola ñandú 😀  ab")
		var s float64
		for _, x := range p {
			s += x
		}
		if len(p) != m.NumClases() || math.Abs(s-1) > 1e-9 {
			t.Fatalf("probabilidades %v", s)
		}
	})
}
