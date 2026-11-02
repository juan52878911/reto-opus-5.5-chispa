package chispamovil

import (
	"encoding/binary"
	"encoding/json"
	"hash/fnv"
	"math"
	"slices"
	"testing"

	"chispa/format/chispa3"
)

// R20 #2: instalar p2 (misma pregunta, «a» con otro texto efectivo por la regla de descripciones repetidas de v2) no pisa las
// torres de p1: TorresL2(p1) sigue siendo verdadero con sus torres y, si se perdieran, TextosTorreL2 las pediría de nuevo.
func TestR20TorresInstaladasNoSePisanEntrePreguntas(t *testing.T) {
	c, err := abrirConMetaYTorr(t, `{"version":1}`, chispa3.TextoTorreV2SinID)
	if err != nil {
		t.Fatal(err)
	}
	defer c.Cerrar()
	p1 := `{"kind":"choice","question":"¿nuevo?","options":[{"id":"a","description":"pago"},{"id":"b","description":"cobro"}]}`
	p2 := `{"kind":"choice","question":"¿nuevo?","options":[{"id":"a","description":"pago"},{"id":"c","description":"pago"}]}`
	textos := func(q string) []string {
		var ts []string
		if err := json.Unmarshal([]byte(c.TextosTorreL2(q)), &ts); err != nil {
			t.Fatal(err)
		}
		return ts
	}
	t1, t2 := textos(p1), textos(p2)
	if len(t1) != 2 || len(t2) != 2 || t1[0] == t2[0] {
		t.Fatalf("p1 %q, p2 %q: «a» debe tener textos distintos", t1, t2)
	}
	if !c.InstalarTorresL2(p1, torres256(t1), len(t1)) || !c.InstalarTorresL2(p2, torres256(t2), len(t2)) {
		t.Fatal("no instala")
	}
	for i, q := range []string{p1, p2} {
		if !c.TorresL2(q) {
			t.Errorf("p%d: TorresL2 debía ser true", i+1)
		}
		ts, err := c.torresNuevas(mustPregunta(t, q))
		if err != nil {
			t.Fatalf("p%d: %v", i+1, err)
		}
		want := [][]string{t1, t2}[i]
		for j, x := range want {
			if q, e := cuantizarTorre(h256(x)).v, cuantizarTorre(h256(x)).e; !slices.Equal(ts[j].v, q) || ts[j].e != e {
				t.Errorf("p%d opción %d: la torre instalada no es la de su texto %q", i+1, j, x)
			}
		}
	}
	// cuatro torres distintas: a (v2), b, a (v1, con id) y c (v1, con id).
	if len(c.dyn) != 4 {
		t.Fatalf("esperaba 4 torres distintas (a v2, b, a v1, c v1), hay %d", len(c.dyn))
	}
}

func mustPregunta(t *testing.T, q string) pregunta {
	t.Helper()
	p, err := leerPregunta(q)
	if err != nil {
		t.Fatal(err)
	}
	return p
}

// h256 es una torre determinista por texto de la dimensión de TORR de estos ficheros (256).
func h256(texto string) []float32 {
	h := fnv.New64a()
	h.Write([]byte(texto))
	s := h.Sum64()
	v := make([]float32, 256)
	for i := range v {
		v[i] = float32(int64((s>>(8*(i%8)))&0xff)-128+int64(i%7)) / 64
	}
	return v
}

func torres256(textos []string) []byte {
	var b []byte
	for _, t := range textos {
		for _, x := range h256(t) {
			b = binary.LittleEndian.AppendUint32(b, math.Float32bits(x))
		}
	}
	return b
}
