package decide

import (
	"container/list"
	"sync"
	"sync/atomic"
)

// LRU es una caché con tamaño máximo, segura para uso concurrente. Reparte las
// claves en fragmentos con su propio cerrojo para no serializar las lecturas;
// el tamaño máximo vale por fragmento (max/fragmentos, redondeado hacia arriba),
// así que con claves muy sesgadas puede expulsar antes de llegar a max.
//
// Puede acotarse además (o solo) por bytes: con función de coste (NewLRUBytes) cada entrada
// pesa coste(v) + len(clave) + sobreEntrada y se expulsa por el final hasta que el fragmento
// cabe. Una entrada que sola no cabe en su fragmento no se guarda.
type LRU[V any] struct {
	frag [fragmentos]*lruFrag[V]
}

const fragmentos = 16

// sobreEntrada es lo que cuesta una entrada además de su valor y su clave: elemento de lista, entrada de mapa y cabeceras.
const sobreEntrada = 128

// Presupuestos por defecto en bytes, calculados para caber con holgura en GOMEMLIMIT = 400 MiB:
// L1 64 + nonces 48 + torres 16 = 128 MiB (32 %); el resto (≈270 MiB) es para los modelos (e5 int8 y su torre), el
// montón vivo de las peticiones en curso y el margen del GC (con GOMEMLIMIT el GC trabaja más cuando el montón se
// acerca al límite, así que las cachés no deben pasar de un tercio).
const (
	BytesCacheL1Defecto     = 64 << 20
	BytesCacheNoncesDefecto = 48 << 20
	BytesCacheTorresDefecto = 16 << 20
)

// NewLRU acota por número de entradas. Si V es []byte (la caché de nonces, que guarda cuerpos de respuesta de tamaño
// muy variable) acota además por BytesCacheNoncesDefecto.
func NewLRU[V any](max int) *LRU[V] {
	var z V
	if _, ok := any(z).([]byte); ok {
		c := newLRU[V](max, BytesCacheNoncesDefecto, func(v V) int { return len(any(v).([]byte)) })
		registraNonces(any(c).(*LRU[[]byte]))
		return c
	}
	return newLRU[V](max, 0, nil)
}

// NewLRUBytes acota por bytes: maxBytes en total (repartido por fragmentos) y coste(v) el tamaño de un valor.
func NewLRUBytes[V any](maxBytes int, coste func(V) int) *LRU[V] {
	return newLRU[V](0, maxBytes, coste)
}

func newLRU[V any](max, maxBytes int, coste func(V) int) *LRU[V] {
	c := &LRU[V]{}
	pf := 0
	if maxBytes > 0 {
		pf = (maxBytes + fragmentos - 1) / fragmentos
	}
	mf := 0
	if max > 0 {
		mf = (max + fragmentos - 1) / fragmentos
	}
	for i := range c.frag {
		c.frag[i] = newFragB[V](mf, pf, coste)
	}
	return c
}

func (c *LRU[V]) f(k string) *lruFrag[V] {
	var h uint32 = 2166136261
	for i := 0; i < len(k); i++ {
		h = (h ^ uint32(k[i])) * 16777619
	}
	return c.frag[h%fragmentos]
}

func (c *LRU[V]) Get(k string) (V, bool) { return c.f(k).Get(k) }
func (c *LRU[V]) Put(k string, v V)      { c.f(k).Put(k, v) }
func (c *LRU[V]) Len() (n int) {
	for _, f := range c.frag {
		n += f.Len()
	}
	return
}

// Bytes es el coste actual de las entradas (0 si la caché no tiene función de coste).
func (c *LRU[V]) Bytes() (n int64) {
	for _, f := range c.frag {
		n += f.Bytes()
	}
	return
}

var noncesActual atomic.Pointer[LRU[[]byte]]

// registraNonces apunta la caché de nonces más reciente (la del modelo en servicio: cada recarga crea una) para el gauge de /metrics.
func registraNonces(c *LRU[[]byte]) { noncesActual.Store(c) }

type lruFrag[V any] struct {
	mu       sync.Mutex
	max      int // entradas; 0 = sin tope
	maxBytes int // bytes; 0 = sin tope
	coste    func(V) int
	bytes    int
	ll       *list.List
	m        map[string]*list.Element
}

type entrada[V any] struct {
	k string
	v V
	n int
}

func newFrag[V any](max int) *lruFrag[V] { return newFragB[V](max, 0, nil) }

func newFragB[V any](max, maxBytes int, coste func(V) int) *lruFrag[V] {
	if max < 1 && maxBytes < 1 {
		max = 1
	}
	return &lruFrag[V]{max: max, maxBytes: maxBytes, coste: coste, ll: list.New(), m: map[string]*list.Element{}}
}

func (c *lruFrag[V]) Get(k string) (v V, ok bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if e, hit := c.m[k]; hit {
		c.ll.MoveToFront(e)
		return e.Value.(*entrada[V]).v, true
	}
	return v, false
}

func (c *lruFrag[V]) quita(e *list.Element) {
	en := e.Value.(*entrada[V])
	c.ll.Remove(e)
	delete(c.m, en.k)
	c.bytes -= en.n
}

func (c *lruFrag[V]) Put(k string, v V) {
	n := 0
	if c.coste != nil {
		n = c.coste(v) + len(k) + sobreEntrada
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	if e, ok := c.m[k]; ok {
		c.quita(e) // se reinserta con su coste nuevo
	}
	if c.maxBytes > 0 && n > c.maxBytes {
		return // no cabe ni sola: no se guarda (y no expulsa a las demás)
	}
	c.m[k] = c.ll.PushFront(&entrada[V]{k, v, n})
	c.bytes += n
	for c.ll.Len() > 1 && ((c.max > 0 && c.ll.Len() > c.max) || (c.maxBytes > 0 && c.bytes > c.maxBytes)) {
		c.quita(c.ll.Back())
	}
}

func (c *lruFrag[V]) Len() int {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.ll.Len()
}

func (c *lruFrag[V]) Bytes() int64 {
	c.mu.Lock()
	defer c.mu.Unlock()
	return int64(c.bytes)
}
