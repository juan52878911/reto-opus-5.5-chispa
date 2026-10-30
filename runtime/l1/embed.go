package l1

import (
	"encoding/binary"
	"math"
)

// Embed escribe en out (len ≥ Dim) el embedding normalizado de texto. Devuelve false si no hubo tokens
// (out queda a cero).
//
// Aritmética: cada fila lleva q int8 y una escala float32 s; el multiplicador entero de la fila es
// M = round(s·2^32) (exacto en float64), y se acumula acc_j = Σ q_ij·M_i en int64. La media se cancela
// al normalizar. La norma es la raíz de Σ acc_j² en float64, sumada en orden fijo y con conversiones
// explícitas para que ningún compilador funda multiplicación y suma (FMA en arm64); luego
// out_j = float32(acc_j / norma), con una sola división por elemento.
func (m *Modelo) Embed(texto string, out []float32) bool {
	return m.EmbedIDs(m.Tokenizar(texto), out)
}

// MaxTokens es el tope de tokens de un texto (el de la cabeza).
func (m *Modelo) MaxTokens() int { return m.p.MaxTokens }

// EmbedIDs es Embed sobre ids ya tokenizados (Embed(t) == EmbedIDs(Tokenizar(t))).
func (m *Modelo) EmbedIDs(ids []int32, out []float32) bool {
	clear(out[:m.dim])
	acc := make([]int64, m.dim)
	n := 0
	pesos := m.sec[secPesos]
	esc := m.sec[secEscalas]
	for _, id := range ids {
		if int(id) == m.p.UnkID {
			continue
		}
		n++
		s := math.Float32frombits(binary.LittleEndian.Uint32(esc[4*id:]))
		M := int64(math.RoundToEven(float64(s) * (1 << escalaBits)))
		fila := pesos[int(id)*m.dim : int(id+1)*m.dim]
		for j, q := range fila {
			acc[j] += int64(int8(q)) * M
		}
	}
	if n == 0 {
		return false
	}
	var ss float64
	for _, a := range acc {
		f := float64(a)
		ss += float64(f * f)
	}
	if ss == 0 {
		return false
	}
	norma := math.Sqrt(ss)
	for j, a := range acc {
		out[j] = float32(float64(a) / norma)
	}
	return true
}
