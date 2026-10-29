package decide

import (
	"chispa/format/chispa3"
	"fmt"
	"strings"
	"testing"
)

// Hallazgo 7: el LRU acotado por bytes expulsa por el final y nunca pasa de su tope.
func TestLRUBytesExpulsa(t *testing.T) {
	const tope = 16 * 4096
	c := NewLRUBytes[[]byte](tope, func(v []byte) int { return len(v) })
	for i := 0; i < 1000; i++ {
		c.Put(fmt.Sprintf("k%d", i), make([]byte, 1000))
		if b := c.Bytes(); b > tope {
			t.Fatalf("tras %d puts: %d bytes > tope %d", i, b, tope)
		}
	}
	if c.Len() == 0 || c.Len() >= 1000 {
		t.Fatalf("len %d: debía expulsar sin vaciarse", c.Len())
	}
	if _, ok := c.Get("k999"); !ok {
		t.Fatal("la última entrada debía estar")
	}
	if _, ok := c.Get("k0"); ok {
		t.Fatal("la primera debía haberse expulsado")
	}
}

func TestLRUBytesEntradaMayorQueElTopeNoSeGuardaNiExpulsa(t *testing.T) {
	c := NewLRUBytes[[]byte](16*1024, func(v []byte) int { return len(v) })
	c.Put("a", make([]byte, 100))
	c.Put("enorme", make([]byte, 1<<20))
	if _, ok := c.Get("enorme"); ok {
		t.Fatal("no debía guardarse")
	}
	if _, ok := c.Get("a"); !ok {
		t.Fatal("no debía expulsar a las demás")
	}
}

func TestLRUBytesReemplazoActualizaCoste(t *testing.T) {
	c := NewLRUBytes[[]byte](16*8192, func(v []byte) int { return len(v) })
	c.Put("k", make([]byte, 5000))
	c.Put("k", make([]byte, 10))
	if b := c.Bytes(); b > 10+1+sobreEntrada {
		t.Fatalf("coste no actualizado: %d", b)
	}
	if c.Len() != 1 {
		t.Fatalf("len %d", c.Len())
	}
}

// Hallazgo 7, nonces: 4096 entradas de ~70 KB (probs de 256 ids) eran ~290 MB; ahora NewLRU[[]byte] se acota por bytes.
func TestNoncesAcotadasPorBytes(t *testing.T) {
	c := NewLRU[[]byte](4096)
	for i := 0; i < 2000; i++ {
		c.Put(fmt.Sprintf("nonce-%d", i), make([]byte, 70<<10))
	}
	if b := c.Bytes(); b > BytesCacheNoncesDefecto || b == 0 {
		t.Fatalf("nonces ocupan %d bytes, tope %d", b, BytesCacheNoncesDefecto)
	}
}

// Hallazgo 7, L1: 1024 esquemas × 256 opciones × dim 256 float32 eran ~256 MB; ahora la caché de L1 se acota por bytes.
func TestL1CacheAcotadaPorBytes(t *testing.T) {
	l := NuevoL1Modelo(nil, chispa3.Calib{}, 1024)
	for i := 0; i < 1024; i++ {
		v := make(map[string][]float32, 256)
		for j := 0; j < 256; j++ {
			v[fmt.Sprintf("op%d", j)] = make([]float32, 256)
		}
		l.cache.Put(fmt.Sprintf("esquema-%d", i), v)
	}
	if b := l.cache.Bytes(); b > BytesCacheL1Defecto || b == 0 {
		t.Fatalf("L1 ocupa %d bytes, tope %d", b, BytesCacheL1Defecto)
	}
}

// Presupuesto por defecto: las tres cachés caben con holgura (≤ 1/3) en GOMEMLIMIT 400 MiB.
func TestPresupuestoCachesCabeEnGOMEMLIMIT(t *testing.T) {
	if tot := BytesCacheL1Defecto + BytesCacheNoncesDefecto + BytesCacheTorresDefecto; tot > (400<<20)/3 {
		t.Fatalf("cachés %d MiB > 1/3 de 400 MiB", tot>>20)
	}
}

func TestMetricasCacheBytes(t *testing.T) {
	m := NuevasMetricas()
	l := NuevoL1Modelo(nil, chispa3.Calib{}, 8)
	l.UsaMetricas(m)
	l.cache.Put("e", map[string][]float32{"a": make([]float32, 100)})
	n := NewLRU[[]byte](8)
	n.Put("x", make([]byte, 1000))
	l2, _ := l2Met(t, &codificadorContador{})
	l2.UsaMetricas(m)
	txt := metricasTexto(m)
	for _, c := range []string{"l1", "nonces", "torres"} {
		if !strings.Contains(txt, `chispa_cache_bytes{cache="`+c+`"} `) {
			t.Fatalf("falta gauge %s:\n%s", c, txt)
		}
	}
	if strings.Contains(txt, `chispa_cache_bytes{cache="l1"} 0`) || strings.Contains(txt, `chispa_cache_bytes{cache="nonces"} 0`) {
		t.Fatalf("gauges a cero:\n%s", txt)
	}
}
