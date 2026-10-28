package l1

import (
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"unicode"
)

// modoXLMR es el pipeline de transformers para XLM-R/e5: Precompiled → WhitespaceSplit →
// Metaspace(always, split) → Unigram, palabra a palabra. Solo lo usa DesdeTokenizador.
const modoXLMR = "xlmr"

var magiaTok = [8]byte{'C', 'H', 'T', 'K'}

// DesdeTokenizador interpreta un .chispa-tok: la misma cabecera y secciones que el .chispa-l1 pero con magia
// CHTK y sin pesos ni escalas (secciones vacías). Solo sirve para Tokenizar.
func DesdeTokenizador(data []byte) (*Modelo, error) {
	if len(data) < tamCabecera || [8]byte(data[:8]) != magiaTok {
		return nil, errors.New("l1: no es un .chispa-tok")
	}
	le := binary.LittleEndian
	if v := le.Uint32(data[8:]); v != versionFormato {
		return nil, fmt.Errorf("l1: versión %d no soportada", v)
	}
	m := &Modelo{data: data}
	m.vocab = int(le.Uint32(data[16:]))
	m.tablaB = uint(le.Uint32(data[28:]))
	m.prefB = uint(le.Uint32(data[32:]))
	for i := 0; i < numSecciones; i++ {
		o := le.Uint64(data[36+16*i:])
		l := le.Uint64(data[44+16*i:])
		if o > uint64(len(data)) || l > uint64(len(data))-o {
			return nil, fmt.Errorf("l1: sección %d fuera de rango", i)
		}
		m.sec[i] = data[o : o+l : o+l]
	}
	copy(m.hashSHA[:], data[36+16*numSecciones:])
	if err := json.Unmarshal(m.sec[secParams], &m.p); err != nil {
		return nil, fmt.Errorf("l1: params: %w", err)
	}
	v := m.vocab
	switch {
	case m.p.Modo != modoXLMR || m.p.Metaspace == "":
		return nil, errors.New("l1: parámetros incoherentes")
	case m.tablaB < 4 || m.tablaB > 30 || m.prefB < 4 || m.prefB > 40:
		return nil, errors.New("l1: tamaños de tabla incoherentes")
	case len(m.sec[secScores]) != 8*v, len(m.sec[secOffsets]) != 4*(v+1),
		len(m.sec[secHash]) != 4<<m.tablaB, len(m.sec[secPrefijos]) != 1<<(m.prefB-3):
		return nil, errors.New("l1: tamaños de sección incoherentes")
	}
	if int(le.Uint32(m.sec[secOffsets][4*v:])) != len(m.sec[secPiezas]) {
		return nil, errors.New("l1: offsets de piezas incoherentes")
	}
	m.unkScore = m.p.MinScore - m.p.UnkPenaliz
	n, err := nuevoNormalizador(m.sec[secCharsmap], "")
	if err != nil {
		return nil, err
	}
	m.norm = n
	for t, id := range m.p.Anadidos {
		m.anadidos = append(m.anadidos, anadido{t, int32(id)})
	}
	return m, nil
}

// trozoXLMR tokeniza un trozo de texto sin tokens añadidos.
func (m *Modelo) trozoXLMR(s string, ids []int32) []int32 {
	s = m.norm.charsmap(s)
	ms := m.p.Metaspace
	for _, w := range strings.FieldsFunc(s, func(r rune) bool { return unicode.Is(unicode.White_Space, r) }) {
		// Metaspace: prepend siempre y partir antes de cada ▁ (MergedWithNext)
		w = ms + w
		ini := 0
		for i := len(ms); i < len(w); {
			if strings.HasPrefix(w[i:], ms) {
				ids = m.viterbi(w[ini:i], ids)
				ini = i
				i += len(ms)
			} else {
				i++
			}
		}
		ids = m.viterbi(w[ini:], ids)
	}
	return ids
}
