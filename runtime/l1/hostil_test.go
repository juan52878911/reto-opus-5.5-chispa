package l1

import (
	"crypto/sha256"
	"encoding/binary"
	"encoding/json"
	"math"
	"testing"
	"time"
)

const (
	tinyDim    = 8
	tinyTablaB = 6
	tinyPrefB  = 12
)

func fnvBytes(b []byte) uint64 {
	h := uint64(fnvOffset)
	for _, c := range b {
		h = (h ^ uint64(c)) * fnvPrimo
	}
	return h
}

// tinyModelo construye un .chispa-l1 mínimo y válido; mut puede corromper secciones y parámetros
// antes de ensamblarlo (el sha256 se recalcula, como haría quien fabrica el fichero).
func tinyModelo(mut func(sec *[numSecciones][]byte, p map[string]any)) []byte {
	piezas := [][]byte{[]byte("[PAD]"), []byte("[UNK]"), []byte("▁reembolso"), []byte("▁del"), []byte("▁cobro")}
	n := len(piezas)
	var blob []byte
	offs := make([]byte, 4*(n+1))
	scores := make([]byte, 8*n)
	pesos := make([]byte, n*tinyDim)
	escalas := make([]byte, 4*n)
	maxCar := 0
	for i, p := range piezas {
		binary.LittleEndian.PutUint32(offs[4*i:], uint32(len(blob)))
		blob = append(blob, p...)
		binary.LittleEndian.PutUint64(scores[8*i:], math.Float64bits(-5))
		if c := len([]rune(string(p))); c > maxCar {
			maxCar = c
		}
		for j := 0; j < tinyDim; j++ {
			pesos[i*tinyDim+j] = byte(int8((i+1)*(j+3)%251 - 120))
		}
		binary.LittleEndian.PutUint32(escalas[4*i:], math.Float32bits(0.01))
	}
	binary.LittleEndian.PutUint32(offs[4*n:], uint32(len(blob)))
	tabla := make([]byte, 4<<tinyTablaB)
	for i, p := range piezas {
		s := fnvBytes(p) & (1<<tinyTablaB - 1)
		for binary.LittleEndian.Uint32(tabla[4*s:]) != 0 {
			s = (s + 1) & (1<<tinyTablaB - 1)
		}
		binary.LittleEndian.PutUint32(tabla[4*s:], uint32(i+1))
	}
	filtro := make([]byte, 1<<(tinyPrefB-3))
	for _, p := range piezas {
		h := uint64(fnvOffset)
		for k, c := range p {
			h = (h ^ uint64(c)) * fnvPrimo
			if k+1 == len(p) || p[k+1]&0xC0 != 0x80 {
				b := h >> (64 - tinyPrefB)
				filtro[b>>3] |= 1 << (b & 7)
			}
		}
	}
	p := map[string]any{
		"max_tokens": 512, "mediana_pieza": 6, "recorte_texto": 512 * 6, "max_pieza_car": maxCar, "unk_id": 1,
		"unk_penalizacion": 10.0, "min_score": -5.0, "metaspace": "▁", "prepend": "always",
		"anadidos": map[string]int{"[PAD]": 0, "[UNK]": 1}, "puntuacion": "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~",
		"normalize": true, "escala_bits": 32, "dim": tinyDim,
	}
	charsmap := []byte{4, 0, 0, 0, 0, 0, 0, 0}
	sec := [numSecciones][]byte{nil, charsmap, blob, offs, scores, tabla, pesos, escalas, filtro}
	if mut != nil {
		mut(&sec, p)
	}
	sec[secParams], _ = json.Marshal(p)
	cab := make([]byte, tamCabecera)
	copy(cab, "CHL1")
	le := binary.LittleEndian
	for i, v := range []uint32{1, tinyDim, uint32(n), 0, uint32(maxCar), tinyTablaB, tinyPrefB} {
		le.PutUint32(cab[8+4*i:], v)
	}
	var resto []byte
	pos := tamCabecera
	for i, b := range sec {
		pad := (16 - pos%16) % 16
		resto = append(resto, make([]byte, pad)...)
		pos += pad
		le.PutUint64(cab[36+16*i:], uint64(pos))
		le.PutUint64(cab[44+16*i:], uint64(len(b)))
		resto = append(resto, b...)
		pos += len(b)
	}
	h := sha256.Sum256(resto)
	copy(cab[36+16*numSecciones:], h[:])
	return append(cab, resto...)
}

// embedAcotado corre Embed con un plazo y convierte pánico o cuelgue en error de test.
func embedAcotado(t *testing.T, m *Modelo, txt string) {
	t.Helper()
	fin := make(chan any, 1)
	go func() {
		defer func() { fin <- recover() }()
		m.Embed(txt, make([]float32, tinyDim))
	}()
	select {
	case r := <-fin:
		if r != nil {
			t.Fatalf("PANIC: %v", r)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("Embed CUELGA (>2 s)")
	}
}

func TestTinyValido(t *testing.T) {
	m, err := Desde(tinyModelo(nil))
	if err != nil {
		t.Fatal(err)
	}
	if err := m.Verificar(); err != nil {
		t.Fatal(err)
	}
	if got := m.Tokenizar("reembolso del cobro"); len(got) != 3 || got[0] != 2 || got[1] != 3 || got[2] != 4 {
		t.Fatalf("ids %v", got)
	}
	embedAcotado(t, m, "reembolso del cobro")
}

func TestHostil(t *testing.T) {
	llena := func(v uint32) func(*[numSecciones][]byte, map[string]any) {
		return func(s *[numSecciones][]byte, _ map[string]any) {
			for i := 0; i+4 <= len(s[secHash]); i += 4 {
				binary.LittleEndian.PutUint32(s[secHash][i:], v)
			}
		}
	}
	casos := []struct {
		nombre string
		mut    func(*[numSecciones][]byte, map[string]any)
	}{
		{"tabla llena de 1 (bucle infinito)", llena(1)},
		{"tabla llena de 0xFFFFFFF0", llena(0xFFFFFFF0)},
		{"una entrada fuera de rango", func(s *[numSecciones][]byte, _ map[string]any) {
			binary.LittleEndian.PutUint32(s[secHash][4*(fnvBytes([]byte("▁del"))&(1<<tinyTablaB-1)):], 0xFFFFFFF0)
		}},
		{"offsets decrecientes", func(s *[numSecciones][]byte, _ map[string]any) {
			binary.LittleEndian.PutUint32(s[secOffsets][4*3:], 0xFFFFFF)
		}},
		{"offset fuera de piezas", func(s *[numSecciones][]byte, _ map[string]any) {
			binary.LittleEndian.PutUint32(s[secOffsets][4*2:], uint32(len(s[secPiezas])+9))
		}},
		{"unk_id fuera de rango", func(_ *[numSecciones][]byte, p map[string]any) { p["unk_id"] = 1 << 30 }},
		{"unk_id negativo", func(_ *[numSecciones][]byte, p map[string]any) { p["unk_id"] = -1 }},
		{"añadido fuera de rango", func(_ *[numSecciones][]byte, p map[string]any) {
			p["anadidos"] = map[string]int{"[UNK]": 1 << 30}
		}},
		{"añadido vacío (bucle infinito)", func(_ *[numSecciones][]byte, p map[string]any) {
			p["anadidos"] = map[string]int{"": 1}
		}},
		{"recorte_texto negativo", func(_ *[numSecciones][]byte, p map[string]any) { p["recorte_texto"] = -1 }},
		{"max_tokens negativo", func(_ *[numSecciones][]byte, p map[string]any) { p["max_tokens"] = -1 }},
		{"max_pieza_car enorme", func(_ *[numSecciones][]byte, p map[string]any) { p["max_pieza_car"] = 1 << 40 }},
	}
	for _, c := range casos {
		t.Run(c.nombre, func(t *testing.T) {
			var m *Modelo
			var err error
			func() {
				defer func() {
					if r := recover(); r != nil {
						t.Fatalf("Desde: PANIC %v", r)
					}
				}()
				m, err = Desde(tinyModelo(c.mut))
			}()
			if err != nil {
				return // rechazado al cargar: correcto
			}
			// si se acepta, usarlo no puede colgar ni caer
			embedAcotado(t, m, "reembolso del cobro")
			embedAcotado(t, m, "zzz qqq [UNK] ñandú")
		})
	}
}

func TestCabeceraHostil(t *testing.T) {
	base := tinyModelo(nil)
	for _, off := range []int{12, 16, 28, 32} { // dim, vocab, tablaB, prefB
		for _, v := range []uint32{0, 1, 3, 31, 33, 41, 1 << 31, 0xFFFFFFFF} {
			b := append([]byte(nil), base...)
			binary.LittleEndian.PutUint32(b[off:], v)
			func() {
				defer func() {
					if r := recover(); r != nil {
						t.Fatalf("off %d val %d: PANIC %v", off, v, r)
					}
				}()
				Desde(b)
				DesdeTokenizador(b)
			}()
		}
	}
}

func FuzzDesde(f *testing.F) {
	f.Add(tinyModelo(nil))
	f.Add(tinyModelo(nil)[:tamCabecera])
	f.Fuzz(func(t *testing.T, data []byte) {
		m, err := Desde(data)
		if err != nil {
			return
		}
		done := make(chan struct{})
		go func() {
			defer close(done)
			m.Embed("reembolso del cobro [UNK] ñandú", make([]float32, m.Dim()))
		}()
		select {
		case <-done:
		case <-time.After(5 * time.Second):
			t.Fatal("Embed cuelga")
		}
	})
}
