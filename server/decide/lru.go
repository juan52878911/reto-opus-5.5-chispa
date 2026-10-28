package decide

import (
	"container/list"
	"sync"
)

// LRU es una caché con tamaño máximo, segura para uso concurrente. Reparte las
// claves en fragmentos con su propio cerrojo para no serializar las lecturas;
// el tamaño máximo vale por fragmento (max/fragmentos, redondeado hacia arriba),
// así que con claves muy sesgadas puede expulsar antes de llegar a max.
type LRU[V any] struct {
	frag [fragmentos]*lruFrag[V]
}

const fragmentos = 16

func NewLRU[V any](max int) *LRU[V] {
	c := &LRU[V]{}
	for i := range c.frag {
		c.frag[i] = newFrag[V]((max + fragmentos - 1) / fragmentos)
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

type lruFrag[V any] struct {
	mu  sync.Mutex
	max int
	ll  *list.List
	m   map[string]*list.Element
}

type entrada[V any] struct {
	k string
	v V
}

func newFrag[V any](max int) *lruFrag[V] {
	if max < 1 {
		max = 1
	}
	return &lruFrag[V]{max: max, ll: list.New(), m: map[string]*list.Element{}}
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

func (c *lruFrag[V]) Put(k string, v V) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if e, ok := c.m[k]; ok {
		e.Value.(*entrada[V]).v = v
		c.ll.MoveToFront(e)
		return
	}
	c.m[k] = c.ll.PushFront(&entrada[V]{k, v})
	for c.ll.Len() > c.max {
		last := c.ll.Back()
		c.ll.Remove(last)
		delete(c.m, last.Value.(*entrada[V]).k)
	}
}

func (c *lruFrag[V]) Len() int {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.ll.Len()
}
