package chispa3

import (
	"bytes"
	"encoding/binary"
	"errors"
	"hash/crc32"
	"math"
	"os"
	"path/filepath"
	"testing"
)

// l1Falso construye un .chispa-l1 mínimo con cabecera válida y 9 secciones de 16 bytes.
func l1Falso() []byte {
	b := make([]byte, l1Cabecera+9*16)
	copy(b, l1Magia)
	le := binary.LittleEndian
	le.PutUint32(b[8:], 1)
	le.PutUint32(b[12:], 4)
	le.PutUint32(b[16:], 2)
	for i := 0; i < 9; i++ {
		le.PutUint64(b[36+16*i:], uint64(l1Cabecera+16*i))
		le.PutUint64(b[44+16*i:], 16)
	}
	return b
}

func seccionesDePrueba(t testing.TB) []Seccion {
	t.Helper()
	meta, err := Meta{Version: 1, Tareas: []string{"urgencia"}, Licencias: map[string]string{"x": "MIT"},
		Dorado: "01fe1e57dc1bb1917757723e35264b146c25c4d81a3950a8ec7bb0f6a4ba8808"}.Codificar()
	if err != nil {
		t.Fatal(err)
	}
	calib, err := Calib{TauEscalate: 0.4, Tipos: map[string]ParamsTipo{"urgencia": {T: 1.3, A: 1, B: 0, Theta: 0.5}}}.Codificar()
	if err != nil {
		t.Fatal(err)
	}
	esq, err := CodificarEsquemas(3, []EntradaEsquema{
		{Hash: HashEsquema("¿p?", []string{"a", "b"}), Escala: 0.5, Vec: []int8{1, -2, 127}},
		{Hash: HashEsquema("q", nil), Escala: 2, Vec: []int8{-128, 0, 5}},
	})
	if err != nil {
		t.Fatal(err)
	}
	l0, _ := os.ReadFile("testdata/urgencia.chispa")
	return []Seccion{{META, meta}, {L0, l0}, {L1, l1Falso()}, {L2, []byte("ONNX-int8-falso")}, {ESQUEMAS, esq}, {CALIB, calib}}
}

func construir(t testing.TB, s []Seccion) []byte {
	t.Helper()
	var buf bytes.Buffer
	if err := Escribir(&buf, s); err != nil {
		t.Fatal(err)
	}
	return buf.Bytes()
}

// recrc recalcula el CRC de cabecera+tabla tras parchear bytes de la tabla a mano.
func recrc(b []byte) []byte {
	n := binary.LittleEndian.Uint32(b[12:])
	cab := append([]byte(nil), b[:tamCabecera]...)
	binary.LittleEndian.PutUint32(cab[24:], 0)
	c := crc32.Update(crc32.Checksum(cab, crcTabla), crcTabla, b[tamCabecera:tamCabecera+int(n)*tamEntrada])
	binary.LittleEndian.PutUint32(b[24:], c)
	return b
}

func TestIdaYVuelta(t *testing.T) {
	secs := seccionesDePrueba(t)
	ruta := filepath.Join(t.TempDir(), "x.chispa")
	if err := os.WriteFile(ruta, construir(t, secs), 0o644); err != nil {
		t.Fatal(err)
	}
	f, err := Abrir(ruta)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	if f.Compat() || len(f.Tipos()) != 6 {
		t.Fatalf("tipos %v", f.Tipos())
	}
	for _, s := range secs {
		got, err := f.Bytes(s.Tipo)
		if err != nil || !bytes.Equal(got, s.Datos) {
			t.Fatalf("%v: %v", s.Tipo, err)
		}
	}
	if err := f.Verificar(); err != nil {
		t.Fatal(err)
	}
	m, err := f.Meta()
	if err != nil || m.Tareas[0] != "urgencia" {
		t.Fatal(m, err)
	}
	c, err := f.Calib()
	if err != nil || c.Tipos["urgencia"].T != 1.3 {
		t.Fatal(c, err)
	}
	e, err := f.Esquemas()
	if err != nil || e.Len() != 2 || e.Dim() != 3 {
		t.Fatal(e, err)
	}
	v, esc, ok := e.Buscar(HashEsquema("¿p?", []string{"a", "b"}))
	if !ok || esc != 0.5 || int8(v[2]) != 127 || int8(v[1]) != -2 {
		t.Fatal(v, esc, ok)
	}
	if _, _, ok := e.Buscar(HashEsquema("¿p?", []string{"b", "a"})); ok {
		t.Fatal("hash distinto encontrado")
	}
	if _, err := f.L1(); err != nil {
		t.Fatal(err)
	}
	if _, err := f.L0Modelo(); err != nil {
		t.Fatal(err)
	}
	if _, err := f.L2(); err != nil {
		t.Fatal(err)
	}
	f.Close()
	if _, err := f.Bytes(META); !errors.Is(err, ErrCerrado) {
		t.Fatal(err)
	}
}

func TestDeterminista(t *testing.T) {
	s := seccionesDePrueba(t)
	r := []Seccion{s[5], s[4], s[3], s[2], s[1], s[0]}
	if !bytes.Equal(construir(t, s), construir(t, r)) {
		t.Fatal("el orden de entrada cambia la salida")
	}
}

func TestSubconjunto(t *testing.T) {
	b := construir(t, []Seccion{{L2, nil}})
	f, err := Desde(b, Limites{})
	if err != nil {
		t.Fatal(err)
	}
	if d, err := f.Bytes(L2); err != nil || len(d) != 0 {
		t.Fatal(d, err)
	}
	if _, err := f.Bytes(META); !errors.Is(err, ErrNoHay) {
		t.Fatal(err)
	}
}

func TestErroresDeEscritura(t *testing.T) {
	var w bytes.Buffer
	if err := Escribir(&w, nil); !errors.Is(err, ErrTabla) {
		t.Fatal(err)
	}
	if err := Escribir(&w, []Seccion{{Tipo(99), nil}}); !errors.Is(err, ErrTipo) {
		t.Fatal(err)
	}
	if err := Escribir(&w, []Seccion{{L0, nil}, {L0, nil}}); !errors.Is(err, ErrDuplicado) {
		t.Fatal(err)
	}
}

func TestErroresDeValidacion(t *testing.T) {
	base := construir(t, seccionesDePrueba(t))
	ent := func(i int) int { return tamCabecera + i*tamEntrada }
	le := binary.LittleEndian
	casos := []struct {
		nombre string
		muta   func(b []byte) []byte
		lim    Limites
		quiere error
	}{
		{"vacío", func(b []byte) []byte { return nil }, Limites{}, ErrMagia},
		{"magia", func(b []byte) []byte { b[1] = 'X'; return b }, Limites{}, ErrMagia},
		{"solo magia", func(b []byte) []byte { return b[:8] }, Limites{}, ErrTruncado},
		{"versión", func(b []byte) []byte { le.PutUint16(b[8:], 7); return b }, Limites{}, ErrVersion},
		{"banderas", func(b []byte) []byte { le.PutUint16(b[10:], 1); return b }, Limites{}, ErrCabecera},
		{"reservado cabecera", func(b []byte) []byte { b[30] = 1; return b }, Limites{}, ErrCabecera},
		{"cero secciones", func(b []byte) []byte { le.PutUint32(b[12:], 0); return b }, Limites{}, ErrTabla},
		{"demasiadas secciones", func(b []byte) []byte { le.PutUint32(b[12:], 0xffffffff); return b }, Limites{}, ErrTabla},
		{"tope de secciones", func(b []byte) []byte { return b }, Limites{MaxSecciones: 2}, ErrTabla},
		{"tabla no cabe", func(b []byte) []byte { return b[:tamCabecera+10] }, Limites{}, ErrTruncado},
		{"truncado", func(b []byte) []byte { return b[:len(b)-1] }, Limites{}, ErrTruncado},
		{"sobrante", func(b []byte) []byte { return append(b, 0) }, Limites{}, ErrCabecera},
		{"crc", func(b []byte) []byte { b[ent(0)+30] ^= 1; return b }, Limites{}, ErrCRC},
		{"tipo cero", func(b []byte) []byte { le.PutUint32(b[ent(0):], 0); return recrc(b) }, Limites{}, ErrTipo},
		{"tipo desconocido", func(b []byte) []byte { le.PutUint32(b[ent(0):], 77); return recrc(b) }, Limites{}, ErrTipo},
		{"tipo repetido", func(b []byte) []byte { le.PutUint32(b[ent(1):], le.Uint32(b[ent(0):])); return recrc(b) }, Limites{}, ErrDuplicado},
		{"reservado entrada", func(b []byte) []byte { b[ent(0)+4] = 1; return recrc(b) }, Limites{}, ErrTabla},
		{"solape", func(b []byte) []byte { le.PutUint64(b[ent(1)+8:], le.Uint64(b[ent(1)+8:])-16); return recrc(b) }, Limites{}, ErrSolape},
		{"hueco", func(b []byte) []byte { le.PutUint64(b[ent(1)+8:], le.Uint64(b[ent(1)+8:])+16); return recrc(b) }, Limites{}, ErrHueco},
		{"fuera por offset", func(b []byte) []byte { le.PutUint64(b[ent(5)+8:], 1<<40); return recrc(b) }, Limites{}, ErrFuera},
		{"fuera por longitud", func(b []byte) []byte { le.PutUint64(b[ent(5)+16:], 1<<40); return recrc(b) }, Limites{}, ErrFuera},
		{"desborde u64", func(b []byte) []byte {
			le.PutUint64(b[ent(5)+8:], 100)
			le.PutUint64(b[ent(5)+16:], math.MaxUint64-50)
			return recrc(b)
		}, Limites{}, ErrDesborde},
		{"offset > MaxInt64", func(b []byte) []byte { le.PutUint64(b[ent(2)+8:], 1<<63); return recrc(b) }, Limites{}, ErrDesborde},
		{"relleno", func(b []byte) []byte {
			// L0 acaba sin alinear a 16 en el fichero de prueba: hay relleno tras la sección 1.
			inicio := tamCabecera + 6*tamEntrada
			fin := inicio + int(le.Uint64(b[ent(1)+8:])+le.Uint64(b[ent(1)+16:]))
			if int(le.Uint64(b[ent(2)+8:]))+inicio == fin {
				t.Skip("sin relleno en el fichero de prueba")
			}
			b[fin] = 9
			return b
		}, Limites{}, ErrRelleno},
		{"tope de fichero", func(b []byte) []byte { return b }, Limites{MaxFichero: 100}, ErrTamano},
		{"tope por tipo", func(b []byte) []byte { return b }, Limites{PorTipo: map[Tipo]int64{L2: 3}}, ErrTamano},
		{"tope de sección", func(b []byte) []byte { return b }, Limites{MaxSeccion: 8}, ErrTamano},
	}
	for _, c := range casos {
		t.Run(c.nombre, func(t *testing.T) {
			b := c.muta(append([]byte(nil), base...))
			_, err := Desde(b, c.lim)
			if !errors.Is(err, c.quiere) {
				t.Fatalf("quería %v, salió %v", c.quiere, err)
			}
		})
	}
}

func TestSHAPerezoso(t *testing.T) {
	base := construir(t, seccionesDePrueba(t))
	// Tipos en orden: META..CALIB; corrompe un byte del contenido de L2 (índice 3 de la tabla).
	le := binary.LittleEndian
	ini := tamCabecera + 6*tamEntrada
	b := append([]byte(nil), base...)
	b[ini+int(le.Uint64(b[tamCabecera+3*tamEntrada+8:]))] ^= 0xff
	f, err := Desde(b, Limites{})
	if err != nil {
		t.Fatalf("la estructura es válida y abrir no debe leer los datos: %v", err)
	}
	if _, err := f.Bytes(META); err != nil {
		t.Fatalf("otra sección sigue bien: %v", err)
	}
	for i := 0; i < 2; i++ { // el error es persistente
		if d, err := f.Bytes(L2); !errors.Is(err, ErrHash) || d != nil {
			t.Fatalf("%v %v", d, err)
		}
	}
	if err := f.Verificar(); !errors.Is(err, ErrHash) {
		t.Fatal(err)
	}
}

func TestContenidos(t *testing.T) {
	malos := map[string]error{}
	_, malos["meta json"] = DecodificarMeta([]byte(`{"version":1,"x":2}`))
	_, malos["meta versión"] = DecodificarMeta([]byte(`{"version":0}`))
	_, malos["meta dorado"] = DecodificarMeta([]byte(`{"version":1,"dorado":"zz"}`))
	_, malos["meta cola"] = DecodificarMeta([]byte(`{"version":1} {}`))
	_, malos["calib tau"] = DecodificarCalib([]byte(`{"tau_escalate":2}`))
	_, malos["calib T"] = DecodificarCalib([]byte(`{"tipos":{"a":{"T":0}}}`))
	_, malos["calib inf"] = DecodificarCalib([]byte(`{"tipos":{"a":{"T":1e999}}}`))
	_, malos["esq corto"] = DecodificarEsquemas([]byte{1, 0})
	_, malos["esq dim 0"] = DecodificarEsquemas(make([]byte, 8))
	_, malos["esq n enorme"] = DecodificarEsquemas([]byte{1, 0, 0, 0, 255, 255, 255, 255})
	_, malos["esq tamaño"] = DecodificarEsquemas([]byte{1, 0, 0, 0, 1, 0, 0, 0, 0})
	malos["l1 corto"] = ValidarL1(nil)
	l1 := l1Falso()
	l1[8] = 2
	malos["l1 versión"] = ValidarL1(l1)
	l1 = l1Falso()
	binary.LittleEndian.PutUint64(l1[44:], 1<<62)
	malos["l1 sección"] = ValidarL1(l1)
	for k, err := range malos {
		if !errors.Is(err, ErrContenido) {
			t.Errorf("%s: %v", k, err)
		}
	}
	// Esquemas: hashes repetidos / desordenados.
	e, _ := CodificarEsquemas(1, []EntradaEsquema{{Hash: [32]byte{1}, Vec: []int8{1}}, {Hash: [32]byte{2}, Vec: []int8{1}}})
	copy(e[8:], e[40:72]) // primer hash = segundo
	if _, err := DecodificarEsquemas(e); !errors.Is(err, ErrContenido) {
		t.Error(err)
	}
	if _, err := CodificarEsquemas(1, []EntradaEsquema{{Vec: []int8{1}}, {Vec: []int8{2}}}); !errors.Is(err, ErrContenido) {
		t.Error(err)
	}
	if _, err := CodificarEsquemas(2, []EntradaEsquema{{Vec: []int8{1}}}); !errors.Is(err, ErrContenido) {
		t.Error(err)
	}
}

func TestHashEsquemaSinAmbiguedad(t *testing.T) {
	if HashEsquema("ab", []string{"c"}) == HashEsquema("a", []string{"bc"}) ||
		HashEsquema("a", []string{"b", "c"}) == HashEsquema("a", []string{"bc"}) {
		t.Fatal("colisión por concatenación")
	}
}

// Compatibilidad con .chispa v2 reales entrenados por la Arena (copiados de server/testdata).
func TestCompatLegado(t *testing.T) {
	for _, n := range []string{"urgencia", "injection"} {
		ruta := "testdata/" + n + ".chispa"
		crudo, err := os.ReadFile(ruta)
		if err != nil {
			t.Fatal(err)
		}
		f, err := Abrir(ruta)
		if err != nil {
			t.Fatalf("%s: %v", n, err)
		}
		if !f.Compat() || len(f.Tipos()) != 1 || f.Tipos()[0] != L0 || f.Tiene(META) {
			t.Fatalf("%s: tipos %v", n, f.Tipos())
		}
		b, err := f.L0()
		if err != nil || !bytes.Equal(b, crudo) {
			t.Fatalf("%s: L0 distinto del original (%v)", n, err)
		}
		m, err := f.L0Modelo()
		if err != nil || len(m.Labels) < 2 {
			t.Fatalf("%s: %v", n, err)
		}
		f.Close()
	}
}

func TestLegadoRoto(t *testing.T) {
	crudo, _ := os.ReadFile("testdata/urgencia.chispa")
	b := append([]byte(nil), crudo...)
	b[100] ^= 1
	if _, err := Desde(b, Limites{}); !errors.Is(err, ErrCRC) {
		t.Fatal(err)
	}
	if _, err := Desde(crudo[:12], Limites{}); !errors.Is(err, ErrTruncado) {
		t.Fatal(err)
	}
	if _, err := Desde(crudo, Limites{PorTipo: map[Tipo]int64{L0: 10}}); !errors.Is(err, ErrTamano) {
		t.Fatal(err)
	}
	v1 := append([]byte(nil), crudo...)
	v1[8] = 1
	if _, err := Desde(v1, Limites{}); !errors.Is(err, ErrVersion) {
		t.Fatal(err)
	}
}

func TestAbrirRutas(t *testing.T) {
	d := t.TempDir()
	if _, err := Abrir(filepath.Join(d, "no")); err == nil {
		t.Fatal("ruta inexistente")
	}
	if _, err := Abrir(d); err == nil {
		t.Fatal("directorio")
	}
	vacio := filepath.Join(d, "v")
	os.WriteFile(vacio, nil, 0o644)
	if _, err := Abrir(vacio); !errors.Is(err, ErrTruncado) {
		t.Fatal(err)
	}
	if _, err := AbrirCon("testdata/urgencia.chispa", Limites{MaxFichero: 10}); !errors.Is(err, ErrTamano) {
		t.Fatal(err)
	}
}

func FuzzAbrir(f *testing.F) {
	s := seccionesDePrueba(f)
	f.Add(construir(f, s))
	f.Add(construir(f, s[:1]))
	f.Add(construir(f, s[3:4]))
	f.Add(construir(f, s[4:]))
	f.Add(construir(f, append(append([]Seccion(nil), s...), Seccion{CONJ, conjDePrueba(f)})))
	for _, n := range []string{"urgencia", "injection"} {
		b, _ := os.ReadFile("testdata/" + n + ".chispa")
		f.Add(b)
	}
	f.Add([]byte{})
	f.Add(magia[:])
	f.Add(append(append([]byte(nil), magia[:]...), 3, 0))
	lim := Limites{MaxFichero: 1 << 22, MaxSeccion: 1 << 22}
	f.Fuzz(func(t *testing.T, data []byte) {
		// Los decodificadores de contenido son puros: se ejercitan también sobre bytes crudos,
		// porque dentro de un fichero mutado casi siempre fallaría antes el sha256.
		DecodificarMeta(data)
		DecodificarCalib(data)
		DecodificarConj(data)
		ValidarL1(data)
		if e, err := DecodificarEsquemas(data); err == nil {
			for i := 0; i < e.Len(); i++ {
				if v, _, ok := e.Buscar([32]byte(e.hash(i))); !ok || len(v) != e.Dim() {
					t.Fatal("Buscar no encuentra una entrada válida")
				}
			}
		}
		fi, err := Desde(data, lim)
		if err != nil {
			return
		}
		for _, tp := range fi.Tipos() {
			b, err := fi.Bytes(tp)
			if err != nil {
				continue // sha incorrecto: es un error válido
			}
			switch tp {
			case META:
				DecodificarMeta(b)
			case CALIB:
				DecodificarCalib(b)
			case ESQUEMAS:
				if e, err := DecodificarEsquemas(b); err == nil {
					for i := 0; i < e.Len(); i++ {
						if v, _, ok := e.Buscar([32]byte(e.hash(i))); !ok || len(v) != e.Dim() {
							t.Fatal("Buscar no encuentra una entrada válida")
						}
					}
				}
			case CONJ:
				DecodificarConj(b)
			case L1:
				ValidarL1(b)
			case L0:
				if fi.Compat() {
					fi.L0Modelo()
				}
			}
		}
	})
}
