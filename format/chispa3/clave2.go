package chispa3

import (
	"crypto/sha256"
	"sort"
)

// OpcionClave es una opción tal como entra en la clave v2: id y descripción.
type OpcionClave struct {
	ID          string
	Descripcion string
}

// HashEsquema2 es la clave de esquema de ESQUEMAS v2 y CONJ v2:
//
//	sha256(pregunta · 0x1f · kind · 0x1f · por cada opción ordenada por id (orden de bytes): id · 0x1e · descripción · 0x1d)
//
// truncado a los 16 primeros bytes. Sin prefijos de longitud: los separadores 0x1f/0x1e/0x1d son los de unidad,
// registro y grupo. No modifica ops.
func HashEsquema2(pregunta, kind string, ops []OpcionClave) [16]byte {
	s := append([]OpcionClave(nil), ops...)
	sort.SliceStable(s, func(i, j int) bool { return s[i].ID < s[j].ID })
	h := sha256.New()
	h.Write([]byte(pregunta))
	h.Write([]byte{0x1f})
	h.Write([]byte(kind))
	h.Write([]byte{0x1f})
	for _, o := range s {
		h.Write([]byte(o.ID))
		h.Write([]byte{0x1e})
		h.Write([]byte(o.Descripcion))
		h.Write([]byte{0x1d})
	}
	var sum [sha256.Size]byte
	h.Sum(sum[:0])
	return [16]byte(sum[:16])
}

// ClaveConj2 es la clave de CONJ v2: HashEsquema2 de la pregunta con todas sus opciones.
func ClaveConj2(pregunta, kind string, ops []OpcionClave) [16]byte {
	return HashEsquema2(pregunta, kind, ops)
}

// BuscarEsquema busca la torre de un esquema con la clave de la versión de la sección: HashEsquema(pregunta, ids en el
// orden dado) en v1 y HashEsquema2(pregunta, kind, ops) en v2. Es el único sitio donde el runtime elige la función de clave
// de ESQUEMAS.
func (e *Esquemas) BuscarEsquema(pregunta, kind string, ops []OpcionClave) (vec []byte, escala float32, ok bool) {
	if e.ver == 2 {
		return e.Buscar2(HashEsquema2(pregunta, kind, ops))
	}
	ids := make([]string, len(ops))
	for i, o := range ops {
		ids[i] = o.ID
	}
	return e.Buscar(HashEsquema(pregunta, ids))
}

// BuscarEsquema busca la cabeza de un esquema con la clave de la versión de la sección: ClaveConj(pregunta, ids) en v1 y
// ClaveConj2(pregunta, kind, ops) en v2.
func (c *Conj) BuscarEsquema(pregunta, kind string, ops []OpcionClave) (*EntradaConj, bool) {
	if c.ver == ConjVersion2 {
		return c.Buscar2(ClaveConj2(pregunta, kind, ops))
	}
	ids := make([]string, len(ops))
	for i, o := range ops {
		ids[i] = o.ID
	}
	return c.Buscar(ClaveConj(pregunta, ids))
}
