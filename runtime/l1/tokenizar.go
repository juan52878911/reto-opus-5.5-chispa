package l1

import (
	"encoding/binary"
	"strings"
	"unicode/utf8"
)

const (
	fnvOffset = 0xCBF29CE484222325
	fnvPrimo  = 0x100000001B3
)

// buscar devuelve el id de la pieza cuyo hash FNV-1a es h y cuyo texto es clave, o -1.
func (m *Modelo) buscar(h uint64, clave string) int32 {
	tabla := m.sec[secHash]
	mask := uint64(1)<<m.tablaB - 1
	offs := m.sec[secOffsets]
	piezas := m.sec[secPiezas]
	for s, n := h&mask, uint64(0); n <= mask; s, n = (s+1)&mask, n+1 {
		v := binary.LittleEndian.Uint32(tabla[4*s:])
		if v == 0 {
			return -1
		}
		id := int(v - 1)
		a := binary.LittleEndian.Uint32(offs[4*id:])
		b := binary.LittleEndian.Uint32(offs[4*id+4:])
		if string(piezas[a:b]) == clave {
			return int32(id)
		}
	}
	return -1
}

// Tokenizar devuelve los ids del texto tal como los daría tokenizers (add_special_tokens=False,
// truncado a 512 tokens y con el recorte de texto de model2vec), sin quitar [UNK].
func (m *Modelo) Tokenizar(texto string) []int32 {
	texto = strings.ToValidUTF8(texto, "�")
	if r := []rune(texto); len(r) > m.p.RecorteTexto {
		texto = string(r[:m.p.RecorteTexto])
	}
	var ids []int32
	resto := texto
	for {
		// siguiente token añadido (literal, sin normalizar) más temprano; a igual posición, el más largo
		pos, mejor := -1, anadido{}
		for _, a := range m.anadidos {
			if i := strings.Index(resto, a.texto); i >= 0 && (pos < 0 || i < pos || (i == pos && len(a.texto) > len(mejor.texto))) {
				pos, mejor = i, a
			}
		}
		if pos < 0 {
			ids = m.tokenizarTrozo(resto, ids)
			break
		}
		ids = m.tokenizarTrozo(resto[:pos], ids)
		ids = append(ids, mejor.id)
		resto = resto[pos+len(mejor.texto):]
	}
	if len(ids) > m.p.MaxTokens {
		ids = ids[:m.p.MaxTokens]
	}
	return ids
}

// tokenizarTrozo normaliza, aplica Metaspace y corre Viterbi sobre el unigram.
func (m *Modelo) tokenizarTrozo(s string, ids []int32) []int32 {
	if m.p.Modo == modoXLMR {
		return m.trozoXLMR(s, ids)
	}
	s = m.norm.normalizar(s)
	if s == "" {
		return ids
	}
	ms := m.p.Metaspace
	s = ms + strings.ReplaceAll(s, " ", ms)
	return m.viterbi(s, ids)
}

// viterbi segmenta s (ya normalizada y con Metaspace) en piezas del unigram y las añade a ids.
func (m *Modelo) viterbi(s string, ids []int32) []int32 {
	// posiciones de byte de cada carácter
	pos := make([]int, 0, len(s)+1)
	for i := range s {
		pos = append(pos, i)
	}
	n := len(pos)
	pos = append(pos, len(s))
	const menosInf = -1e300
	mejor := make([]float64, n+1)
	desde := make([]int32, n+1) // inicio (en caracteres) de la pieza que llega aquí
	idp := make([]int32, n+1)
	for i := 1; i <= n; i++ {
		mejor[i] = menosInf
	}
	for ini := 0; ini < n; ini++ {
		base := mejor[ini]
		h := uint64(fnvOffset)
		unSolo := false
		fin := ini + m.p.MaxPiezaCar
		if fin > n {
			fin = n
		}
		for j := ini; j < fin; j++ {
			for k := pos[j]; k < pos[j+1]; k++ {
				h = (h ^ uint64(s[k])) * fnvPrimo
			}
			b := h >> (64 - m.prefB)
			if m.sec[secPrefijos][b>>3]&(1<<(b&7)) == 0 {
				break // ya no es prefijo de ninguna pieza
			}
			id := m.buscar(h, s[pos[ini]:pos[j+1]])
			if id < 0 {
				continue
			}
			if j == ini {
				unSolo = true
			}
			if c := base + m.score(id); c > mejor[j+1] {
				mejor[j+1], desde[j+1], idp[j+1] = c, int32(ini), id
			}
		}
		if !unSolo {
			if c := base + m.unkScore; c > mejor[ini+1] {
				mejor[ini+1], desde[ini+1], idp[ini+1] = c, int32(ini), int32(m.p.UnkID)
			}
		}
	}
	ini := len(ids)
	for f := n; f > 0; f = int(desde[f]) {
		ids = append(ids, idp[f])
	}
	for a, b := ini, len(ids)-1; a < b; a, b = a+1, b-1 {
		ids[a], ids[b] = ids[b], ids[a]
	}
	// fuse_unk: los [UNK] consecutivos se funden en uno
	w := ini
	for i := ini; i < len(ids); i++ {
		if ids[i] == int32(m.p.UnkID) && w > ini && ids[w-1] == ids[i] {
			continue
		}
		ids[w] = ids[i]
		w++
	}
	return ids[:w]
}

var _ = utf8.RuneError
