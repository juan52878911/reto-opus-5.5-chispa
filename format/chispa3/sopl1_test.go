package chispa3

import (
	"bytes"
	"errors"
	"math"
	"os"
	"path/filepath"
	"testing"
)

func soplDePrueba() []EntradaSopl1 {
	esc, q := CuantizarMedia([]float32{0.5, -0.25, 0, 0.125})
	return []EntradaSopl1{{
		Hash: ClaveConj("¿p?", []string{"b", "a"}), Ids: []string{"a", "b"}, K: []uint32{3, 0},
		Escala: []float32{esc, 0}, Media: append(q, 0, 0, 0, 0),
	}}
}

func TestSOPL1IdaYVuelta(t *testing.T) {
	b, err := CodificarSopl1(4, soplDePrueba())
	if err != nil {
		t.Fatal(err)
	}
	s, err := DecodificarSopl1(b)
	if err != nil || s.Len() != 1 || s.Dim() != 4 {
		t.Fatalf("%+v %v", s, err)
	}
	e, ok := s.Buscar(ClaveConj("¿p?", []string{"a", "b"}))
	if !ok {
		t.Fatal("no encuentra la pregunta")
	}
	k, m, ok := e.Opcion("a", 4)
	if !ok || k != 3 || math.Abs(float64(m[0])-0.5) > 1e-6 || math.Abs(float64(m[1])+0.25) > 0.003 {
		t.Fatalf("a: k=%d %v", k, m)
	}
	if k, m, ok := e.Opcion("b", 4); !ok || k != 0 || m[0] != 0 {
		t.Fatalf("b: k=%d %v", k, m)
	}
	if _, _, ok := e.Opcion("z", 4); ok {
		t.Fatal("z no existe")
	}
	if _, ok := s.Buscar(ClaveConj("otra", []string{"a", "b"})); ok {
		t.Fatal("otra pregunta no está")
	}
	// Dentro de un fichero con todas las demás secciones.
	ruta := filepath.Join(t.TempDir(), "x.chispa")
	if err := os.WriteFile(ruta, construir(t, append(seccionesDePrueba(t), Seccion{SOPL1, b})), 0o644); err != nil {
		t.Fatal(err)
	}
	f, err := Abrir(ruta)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	if g, err := f.Sopl1(); err != nil || g.Len() != 1 || SOPL1.String() != "SOPL1" {
		t.Fatalf("%v %v", g, err)
	}
}

// Los .chispa sin la sección se leen igual y Sopl1() dice que no hay.
func TestSOPL1AusenteEnTestdata(t *testing.T) {
	for _, n := range []string{"urgencia", "injection", "torre"} {
		f, err := Abrir("testdata/" + n + ".chispa")
		if err != nil {
			t.Fatal(n, err)
		}
		if f.Tiene(SOPL1) {
			t.Errorf("%s: no debería traer SOPL1", n)
		}
		if _, err := f.Sopl1(); !errors.Is(err, ErrNoHay) {
			t.Errorf("%s: %v", n, err)
		}
		f.Close()
	}
}

func TestSOPL1Invalida(t *testing.T) {
	ok, _ := CodificarSopl1(4, soplDePrueba())
	malas := map[string][]byte{
		"vacía":    nil,
		"corta":    ok[:10],
		"versión":  append([]byte{9}, ok[1:]...),
		"truncada": ok[:len(ok)-1],
		"sobrante": append(append([]byte(nil), ok...), 0),
		"dim 0":    append(append([]byte(nil), ok[:4]...), append([]byte{0, 0, 0, 0}, ok[8:]...)...),
	}
	for n, b := range malas {
		if _, err := DecodificarSopl1(b); !errors.Is(err, ErrContenido) {
			t.Errorf("%s: %v", n, err)
		}
	}
	e := soplDePrueba()[0]
	e.Ids = []string{"b", "a"}
	if _, err := CodificarSopl1(4, []EntradaSopl1{e}); !errors.Is(err, ErrContenido) {
		t.Errorf("ids desordenados: %v", err)
	}
	e = soplDePrueba()[0]
	e.Media = e.Media[:7]
	if _, err := CodificarSopl1(4, []EntradaSopl1{e}); !errors.Is(err, ErrContenido) {
		t.Errorf("media corta: %v", err)
	}
}

// testdata/soporte.chispa lo escribe el escritor Python (sdk/python/tests/test_sopl1.py): los bytes de SOPL1 deben ser los de CodificarSopl1.
func TestSOPL1FicheroEscritoPorPython(t *testing.T) {
	f, err := Abrir(filepath.Join("testdata", "soporte.chispa"))
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	want, err := CodificarSopl1(4, soplDePrueba())
	if err != nil {
		t.Fatal(err)
	}
	raw, err := f.Bytes(SOPL1)
	if err != nil || !bytes.Equal(raw, want) {
		t.Fatalf("bytes distintos: %x vs %x (%v)", raw, want, err)
	}
}

func TestPesoSoporteYMezclar(t *testing.T) {
	inf, cero, dos := math.Inf(1), 0.0, 2.0
	for _, c := range []struct {
		k      int
		lambda *float64
		want   float64
	}{{3, nil, 0}, {3, &inf, 0}, {0, &dos, 0}, {2, &dos, 0.5}, {6, &dos, 0.75}, {3, &cero, 1}} {
		if got := PesoSoporte(c.k, c.lambda); got != c.want {
			t.Errorf("k=%d λ=%v: %v, quería %v", c.k, c.lambda, got, c.want)
		}
	}
	d, m := []float32{1, 0}, []float32{0, 1}
	if g := Mezclar(d, m, 0); &g[0] != &d[0] {
		t.Error("w=0 debe devolver la descripción tal cual")
	}
	g := Mezclar(d, m, 0.5)
	if math.Abs(float64(g[0])-math.Sqrt2/2) > 1e-6 || math.Abs(float64(g[1])-math.Sqrt2/2) > 1e-6 {
		t.Errorf("w=0,5: %v", g)
	}
	if g := Mezclar(d, m, 1); math.Abs(float64(g[1])-1) > 1e-6 {
		t.Errorf("w=1: %v", g)
	}
	if g := Mezclar(d, []float32{-1, 0}, 0.5); &g[0] != &d[0] {
		t.Error("mezcla nula: debe devolver la descripción")
	}
}

// Casos calculados a mano de la fórmula de shrinkage de G.8 (model/l2/formula-shrinkage.md; κ ≡ λ del runtime):
//
//	λ_c = κ/(κ+n) · Q_k = λ_c·h + (1−λ_c)·M_k · P_k = Q_k/‖Q_k‖ · simproto = mean_s max_k (s·P_k)
func casi(t *testing.T, nombre string, got, want []float64) {
	t.Helper()
	for i := range want {
		if math.Abs(got[i]-want[i]) > 1e-6 {
			t.Errorf("%s[%d] = %.7f, quería %.7f", nombre, i, got[i], want[i])
		}
	}
}

// casiTol es casi con tolerancia explícita (las ranuras de CONJ van en int8: error ≤ 0,4 % por componente).
func casiTol(t *testing.T, nombre string, got, want []float64, tol float64) {
	t.Helper()
	for i := range want {
		if math.Abs(got[i]-want[i]) > tol {
			t.Errorf("%s[%d] = %.7f, quería %.7f (tol %g)", nombre, i, got[i], want[i], tol)
		}
	}
}

func f64(v []float32) []float64 {
	o := make([]float64, len(v))
	for i, x := range v {
		o[i] = float64(x)
	}
	return o
}

func TestLambdaClase(t *testing.T) {
	cuatro, cero, inf := 4.0, 0.0, math.Inf(1)
	for _, c := range []struct {
		n     int
		kappa *float64
		want  float64
	}{{1, &cuatro, 0.8}, {32, &cuatro, 4.0 / 36}, {3, &cero, 0}, {3, nil, 0}, {3, &inf, 1}} {
		if got := LambdaClase(c.n, c.kappa); math.Abs(got-c.want) > 1e-12 {
			t.Errorf("n=%d κ=%v: %v, quería %v", c.n, c.kappa, got, c.want)
		}
	}
	for _, n := range []int{1, 2, 7} { // 1−λ_c es el peso de los ejemplos de PesoSoporte
		if math.Abs(1-LambdaClase(n, &cuatro)-PesoSoporte(n, &cuatro)) > 1e-12 {
			t.Errorf("n=%d: LambdaClase y PesoSoporte no suman 1", n)
		}
	}
}

// L1: la media va SIN normalizar. desc=(0,1,0), media=(0.6,0,0) (norma 0,6, la de dos ejemplos que no coinciden del todo),
// κ=2, n=2 ⇒ λ=0,5: Q=(0,3, 0,5, 0), ‖Q‖=√0,34 ⇒ P=(0,514496, 0,857493, 0). Si se normalizara la media antes saldría (√½, √½, 0).
func TestShrinkageL1MediaSinNormalizar(t *testing.T) {
	dos := 2.0
	got := Mezclar([]float32{0, 1, 0}, []float32{0.6, 0, 0}, PesoSoporte(2, &dos))
	casi(t, "n=2 κ=2", f64(got), []float64{0.3 / math.Sqrt(0.34), 0.5 / math.Sqrt(0.34), 0})
	casi(t, "n=2 κ=2 (valores)", f64(got), []float64{0.514496, 0.857493, 0})
	// n=1, κ=4 ⇒ λ=0,8: Q=(0,2, 0, 0,8, 0), ‖Q‖=√0,68 ⇒ P=(0,242536, 0, 0,970143, 0).
	cuatro := 4.0
	got = Mezclar([]float32{0, 0, 1, 0}, []float32{1, 0, 0, 0}, PesoSoporte(1, &cuatro))
	casi(t, "n=1 κ=4", f64(got), []float64{0.242536, 0, 0.970143, 0})
}

func conjProtos(k, d int, escala float32, protos ...[]int8) *EntradaConj {
	e := &EntradaConj{K: k, D: d, Clases: []string{"a"}}
	for _, p := range protos {
		e.Escala = append(e.Escala, escala)
		for _, q := range p {
			e.Proto = append(e.Proto, byte(q))
		}
	}
	return e
}

// L2c, dim 3 y 2 ranuras. h=(1,0,0); ranuras de CONJ (0,1,0) y (0,0,1); κ=4, n=1 ⇒ λ=0,8.
// Q0=(0,8, 0,2, 0), Q1=(0,8, 0, 0,2), ‖Q‖=√0,68 ⇒ P0=(0,970143, 0,242536, 0), P1=(0,970143, 0, 0,242536).
// S: s0=(1,0,0) da 0,970143 con las dos ranuras; s1=(0,1,0), max(0,242536, 0). simproto = (0,970143+0,242536)/2 = 0,606339.
func TestShrinkageL2cDosRanuras(t *testing.T) {
	e := conjProtos(2, 3, 1, []int8{0, 1, 0}, []int8{0, 0, 1})
	h := []float32{1, 0, 0}
	p := e.ProtosMezclados(0, h, 0.8, nil)
	casi(t, "P", f64(p), []float64{0.970143, 0.242536, 0, 0.970143, 0, 0.242536})
	S := [][]float32{{1, 0, 0}, {0, 1, 0}}
	casi(t, "simproto", []float64{simprotoF(S, p, 3)}, []float64{0.606339})
	// El camino completo (SOPL1 con k=1, κ=4, torre int8 (127,0,0)·1/127).
	sop := &EntradaSopl1{Ids: []string{"a"}, K: []uint32{1}}
	cuatro := 4.0
	got := SimprotoMezclado(e, sop, &cuatro, []string{"a"}, S, func(int) ([]byte, float32, bool) { return []byte{127, 0, 0}, 1.0 / 127, true })
	casi(t, "SimprotoMezclado", got, []float64{0.606339})
	// κ=0 ⇒ solo ejemplos: P = ranuras de CONJ; κ=∞ ⇒ solo descripción: P = h en las 2 ranuras.
	casi(t, "κ=0", f64(e.ProtosMezclados(0, h, 0, nil)), []float64{0, 1, 0, 0, 0, 1})
	casi(t, "κ=∞", f64(e.ProtosMezclados(0, h, 1, nil)), []float64{1, 0, 0, 1, 0, 0})
	// Un Q nulo se queda en 0: ranura (−1,0,0) y h=(1,0,0) con λ=0,5.
	z := conjProtos(1, 3, 1, []int8{-1, 0, 0})
	casi(t, "Q=0", f64(z.ProtosMezclados(0, h, 0.5, nil)), []float64{0, 0, 0})
}

// L2c, dim 4 y 2 ranuras de norma 1 (escala 0,1): M0=(0,1,0,0), M1=(0,0,0,6, 0,8); h=(1,0,0,0); κ=1, n=3 ⇒ λ=0,25.
// Q0=(0,25, 0,75, 0, 0), ‖Q0‖=√0,625 ⇒ P0=(0,316228, 0,948683, 0, 0).
// Q1=(0,25, 0, 0,45, 0,6), ‖Q1‖²=0,0625+0,2025+0,36=0,625 ⇒ P1=(0,316228, 0, 0,569210, 0,758947).
func TestShrinkageL2cDim4(t *testing.T) {
	e := conjProtos(2, 4, 0.1, []int8{0, 10, 0, 0}, []int8{0, 0, 6, 8})
	p := e.ProtosMezclados(0, []float32{1, 0, 0, 0}, 0.25, nil)
	casi(t, "P0", f64(p[:4]), []float64{0.316228, 0.948683, 0, 0})
	casi(t, "P1", f64(p[4:]), []float64{0.316228, 0, 0.569210, 0.758947})
	// s=(0,0,0,1): solo la ranura 1 puntúa, 0,758947; s=(1,0,0,0): ambas dan 0,316228 ⇒ simproto = 0,537588.
	S := [][]float32{{0, 0, 0, 1}, {1, 0, 0, 0}}
	casi(t, "simproto", []float64{simprotoF(S, p, 4)}, []float64{(0.758947 + 0.316228) / 2})
}

// L2c con las 16 ranuras de G.8: pares M=(0,1,0), impares M=(0,0,1); h=(1,0,0); κ=2, n=2 ⇒ λ=0,5 ⇒ Q=(0,5, 0,5, 0) o (0,5, 0, 0,5),
// P=(√½, √½, 0) o (√½, 0, √½). Las tres ranuras de consulta (e_y, e_z, e_x) puntúan √½ cada una ⇒ simproto = 0,707107.
func TestShrinkageL2c16Ranuras(t *testing.T) {
	var ps [][]int8
	for j := 0; j < 16; j++ {
		if j%2 == 0 {
			ps = append(ps, []int8{0, 1, 0})
		} else {
			ps = append(ps, []int8{0, 0, 1})
		}
	}
	e := conjProtos(16, 3, 1, ps...)
	S := [][]float32{{0, 1, 0}, {0, 0, 1}, {1, 0, 0}}
	dos := 2.0
	sop := &EntradaSopl1{Ids: []string{"a"}, K: []uint32{2}}
	got := SimprotoMezclado(e, sop, &dos, []string{"a"}, S, func(int) ([]byte, float32, bool) { return []byte{2, 0, 0}, 0.5, true })
	casi(t, "16 ranuras", got, []float64{math.Sqrt2 / 2})
	p := e.ProtosMezclados(0, []float32{1, 0, 0}, 0.5, nil)
	if len(p) != 48 {
		t.Fatalf("16×3 esperado, salió %d", len(p))
	}
	casi(t, "ranura 15", f64(p[45:]), []float64{math.Sqrt2 / 2, 0, math.Sqrt2 / 2})
}

// Sin κ, sin SOPL1, sin k o sin torre no se toca nada (nil: la cabeza usa el simproto de CONJ).
func TestSimprotoMezcladoSinCambios(t *testing.T) {
	e := conjProtos(1, 2, 1, []int8{1, 0})
	S := [][]float32{{1, 0}}
	tor := func(int) ([]byte, float32, bool) { return []byte{0, 1}, 1, true }
	sop := &EntradaSopl1{Ids: []string{"a"}, K: []uint32{2}}
	un, cero := 1.0, 0.0
	if SimprotoMezclado(e, sop, nil, []string{"a"}, S, tor) != nil || SimprotoMezclado(e, nil, &un, []string{"a"}, S, tor) != nil ||
		SimprotoMezclado(e, &EntradaSopl1{Ids: []string{"a"}, K: []uint32{0}}, &un, []string{"a"}, S, tor) != nil ||
		SimprotoMezclado(e, sop, &un, []string{"a"}, S, func(int) ([]byte, float32, bool) { return nil, 0, false }) != nil {
		t.Fatal("debería devolver nil")
	}
	// κ=0 coincide con el simproto de CONJ.
	casi(t, "κ=0", SimprotoMezclado(e, sop, &cero, []string{"a"}, S, tor), Simproto(e, S, []string{"a"}))
}

// SOPL1 v2: testdata/soporte-v2.chispa lo escribe Python (test_sopl1.py); mismos bytes que CodificarSopl1 y el lector sigue
// leyendo la v1.
func soplV2DePrueba() []EntradaSopl1 {
	e := soplDePrueba()
	e[0].Ranuras = 2
	e[0].Normas = []float32{float32(math.Sqrt(5) / 3), 1, 0, 0}
	return e
}

func TestSOPL1V2FicheroEscritoPorPython(t *testing.T) {
	f, err := Abrir(filepath.Join("testdata", "soporte-v2.chispa"))
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	want, err := CodificarSopl1(4, soplV2DePrueba())
	if err != nil {
		t.Fatal(err)
	}
	raw, err := f.Bytes(SOPL1)
	if err != nil || !bytes.Equal(raw, want) || raw[0] != 2 {
		t.Fatalf("bytes distintos: %x vs %x (%v)", raw, want, err)
	}
	s, err := DecodificarSopl1(raw)
	if err != nil {
		t.Fatal(err)
	}
	e, _ := s.Buscar(ClaveConj("¿p?", []string{"a", "b"}))
	if n := e.NormasDe("a"); len(n) != 2 || n[1] != 1 || e.NormasDe("z") != nil {
		t.Fatalf("normas %v", n)
	}
	// Sin normas, los bytes son los de la v1 (versión 1) y el lector no las inventa.
	v1, _ := CodificarSopl1(4, soplDePrueba())
	if v1[0] != 1 {
		t.Fatalf("versión %d, quería 1", v1[0])
	}
	s1, err := DecodificarSopl1(v1)
	if err != nil {
		t.Fatal(err)
	}
	e1, _ := s1.Buscar(ClaveConj("¿p?", []string{"a", "b"}))
	if e1.NormasDe("a") != nil {
		t.Fatal("la v1 no trae normas")
	}
	// Una v2 truncada o con una norma imposible se rechaza.
	if _, err := DecodificarSopl1(raw[:len(raw)-2]); !errors.Is(err, ErrContenido) {
		t.Errorf("v2 truncada: %v", err)
	}
	mal := soplV2DePrueba()
	mal[0].Normas[0] = 2
	if _, err := CodificarSopl1(4, mal); !errors.Is(err, ErrContenido) {
		t.Errorf("norma 2: %v", err)
	}
}

// Caso a mano, n=3 y normas distintas (d=2, K=2, h=(0,1), κ=3 ⇒ λ=0,5). Ranuras de los 3 ejemplos: ranura 0 = (1,0),(1,0),(0,1) ⇒ media
// (2/3,1/3), norma √5/3; ranura 1 = (1,0)×3 ⇒ media (1,0), norma 1. Con modelo.py: Q0=½h+½M0=(1/3,2/3) ⇒ P0=(1,2)/√5; Q1=(½,½) ⇒ P1=(1,1)/√2.
// Con la media ya normalizada (sin normas) saldría P0=(0,526, 0,851): el resultado de hoy, distinto.
func TestShrinkageNormasN3ReproduceModeloPy(t *testing.T) {
	e := &EntradaConj{K: 2, D: 2, Clases: []string{"a"}}
	for _, m := range [][]float32{{2 / float32(math.Sqrt(5)), 1 / float32(math.Sqrt(5))}, {1, 0}} {
		esc, q := CuantizarMedia(m)
		e.Escala = append(e.Escala, esc)
		for _, v := range q {
			e.Proto = append(e.Proto, byte(v))
		}
	}
	h := []float32{0, 1}
	norma := []float32{float32(math.Sqrt(5) / 3), 1}
	p := e.ProtosMezclados(0, h, 0.5, norma)
	casiTol(t, "P0 con normas", f64(p[:2]), []float64{1 / math.Sqrt(5), 2 / math.Sqrt(5)}, 2e-3)
	casiTol(t, "P1 con normas", f64(p[2:]), []float64{1 / math.Sqrt2, 1 / math.Sqrt2}, 2e-3)
	sin := e.ProtosMezclados(0, h, 0.5, nil)
	if math.Abs(float64(sin[0])-1/math.Sqrt(5)) < 0.05 {
		t.Fatalf("sin normas debería diferir de modelo.py: %v", sin[:2])
	}
	// Camino completo: κ=3, k=3 en SOPL1 v2, S = {(0,1), (1,0)}: simproto = (2/√5 + 1/√2)/2.
	S := [][]float32{{0, 1}, {1, 0}}
	tor := func(int) ([]byte, float32, bool) { return []byte{0, 127}, 1.0 / 127, true }
	tres := 3.0
	con := &EntradaSopl1{Ids: []string{"a"}, K: []uint32{3}, Ranuras: 2, Normas: norma}
	casiTol(t, "simproto", SimprotoMezclado(e, con, &tres, []string{"a"}, S, tor), []float64{(2/math.Sqrt(5) + 1/math.Sqrt2) / 2}, 2e-3)
	// Normas de otro K (CONJ y SOPL1 de ficheros distintos) se ignoran.
	raro := &EntradaSopl1{Ids: []string{"a"}, K: []uint32{3}, Ranuras: 3, Normas: []float32{1, 1, 1}}
	casi(t, "K distinto", SimprotoMezclado(e, raro, &tres, []string{"a"}, S, tor), SimprotoMezclado(e, &EntradaSopl1{Ids: []string{"a"}, K: []uint32{3}}, &tres, []string{"a"}, S, tor))
}

// κ=0 ⇒ solo ejemplos (simproto de CONJ, con o sin normas: la normalización las cancela); κ=∞ ⇒ solo descripción.
func TestSimprotoMezcladoLimites(t *testing.T) {
	e := conjProtos(2, 3, 1, []int8{0, 1, 0}, []int8{0, 0, 1})
	S := [][]float32{{1, 0, 0}, {0, 1, 0}}
	tor := func(int) ([]byte, float32, bool) { return []byte{127, 0, 0}, 1.0 / 127, true }
	sop := &EntradaSopl1{Ids: []string{"a"}, K: []uint32{2}, Ranuras: 2, Normas: []float32{0.5, 0.25}}
	cero, inf := 0.0, math.Inf(1)
	casi(t, "κ=0", SimprotoMezclado(e, sop, &cero, []string{"a"}, S, tor), Simproto(e, S, []string{"a"}))
	// κ=∞: P = h=(1,0,0) en las dos ranuras ⇒ simproto = mean(1, 0) = 0,5, sea cual sea la media.
	casi(t, "κ=∞", SimprotoMezclado(e, sop, &inf, []string{"a"}, S, tor), []float64{0.5})
	if LambdaClase(2, &inf) != 1 || PesoSoporte(2, &inf) != 0 || LambdaClase(2, &cero) != 0 || PesoSoporte(2, &cero) != 1 {
		t.Fatal("λ=∞ debe ser solo descripción y λ=0 solo ejemplos")
	}
}
