package l1

import (
	"encoding/binary"
	"errors"
	"strings"
	"unicode"
	"unicode/utf8"
)

// normalizador reproduce el normalizador de tokenizer.json de potion:
// Precompiled(charsmap de sentencepiece) → " {2,}"→" " → espaciar puntuación → \s+→" " → strip.
type normalizador struct {
	unidades []byte // array doble de darts-clone (u32 little endian)
	pool     []byte // cadenas normalizadas, terminadas en 0
	punt     map[rune]bool
}

func nuevoNormalizador(charsmap []byte, puntuacion string) (normalizador, error) {
	var n normalizador
	if len(charsmap) < 4 {
		return n, errors.New("l1: charsmap vacío")
	}
	t := int(binary.LittleEndian.Uint32(charsmap))
	if t%4 != 0 || t == 0 || 4+t > len(charsmap) {
		return n, errors.New("l1: charsmap corrupto")
	}
	n.unidades = charsmap[4 : 4+t]
	n.pool = charsmap[4+t:]
	n.punt = map[rune]bool{}
	for _, r := range puntuacion {
		n.punt[r] = true
	}
	return n, nil
}

func (n *normalizador) unidad(i uint32) uint32 {
	if int(i)*4+4 > len(n.unidades) {
		return 0
	}
	return binary.LittleEndian.Uint32(n.unidades[i*4:])
}

// prefijoMasLargo busca en el trie el prefijo más largo de s con entrada y devuelve su cadena normalizada.
func (n *normalizador) transformar(s string) (string, bool) {
	pos := uint32(0)
	u := n.unidad(pos)
	pos ^= (u >> 10) << ((u & (1 << 9)) >> 6)
	var res uint32
	hay := false
	for i := 0; i < len(s); i++ {
		c := s[i]
		if c == 0 {
			break
		}
		pos ^= uint32(c)
		u = n.unidad(pos)
		if u&(1<<31|0xFF) != uint32(c) {
			break
		}
		pos ^= (u >> 10) << ((u & (1 << 9)) >> 6)
		if (u>>8)&1 == 1 {
			res = n.unidad(pos) & (1<<31 - 1)
			hay = true
		}
	}
	if !hay {
		return "", false
	}
	if int(res) > len(n.pool) {
		return "", false
	}
	fin := int(res)
	for fin < len(n.pool) && n.pool[fin] != 0 {
		fin++
	}
	return string(n.pool[res:fin]), true
}

func esExtend(r rune) bool {
	return unicode.In(r, unicode.Mn, unicode.Me, unicode.Mc) || r == 0x200D || r == 0x200C ||
		(r >= 0x1F3FB && r <= 0x1F3FF) || (r >= 0xE0020 && r <= 0xE007F)
}

// graphemes parte s en clústeres de grafemas (aproximación de UAX #29 suficiente para el charsmap:
// solo importan los clústeres de <6 bytes).
func graphemes(s string, emit func(string)) {
	for i := 0; i < len(s); {
		r, w := utf8.DecodeRuneInString(s[i:])
		j := i + w
		switch {
		case r == '\r':
			if j < len(s) && s[j] == '\n' {
				j++
			}
		case r == '\n' || unicode.IsControl(r):
		default:
			for j < len(s) {
				r2, w2 := utf8.DecodeRuneInString(s[j:])
				if !esExtend(r2) && !hangulSigue(r, r2) {
					break
				}
				r = r2
				j += w2
			}
		}
		emit(s[i:j])
		i = j
	}
}

func hangulSigue(a, b rune) bool {
	l := func(r rune) bool { return r >= 0x1100 && r <= 0x115F }
	v := func(r rune) bool { return r >= 0x1160 && r <= 0x11A7 }
	t := func(r rune) bool { return r >= 0x11A8 && r <= 0x11FF }
	lv := func(r rune) bool { return r >= 0xAC00 && r <= 0xD7A3 && (r-0xAC00)%28 == 0 }
	lvt := func(r rune) bool { return r >= 0xAC00 && r <= 0xD7A3 && (r-0xAC00)%28 != 0 }
	switch {
	case l(a):
		return l(b) || v(b) || lv(b) || lvt(b)
	case v(a) || lv(a):
		return v(b) || t(b)
	case t(a) || lvt(a):
		return t(b)
	}
	return false
}

// charsmap aplica solo el Precompiled (charsmap de sentencepiece), grafema a grafema.
func (n *normalizador) charsmap(s string) string {
	s = strings.ToValidUTF8(s, "�")
	var sb strings.Builder
	sb.Grow(len(s))
	graphemes(s, func(g string) {
		if len(g) < 6 {
			if t, ok := n.transformar(g); ok {
				sb.WriteString(t)
				return
			}
		}
		for _, r := range g {
			c := string(r)
			if t, ok := n.transformar(c); ok {
				sb.WriteString(t)
			} else {
				sb.WriteString(c)
			}
		}
	})
	return sb.String()
}

func (n *normalizador) normalizar(s string) string {
	s = n.charsmap(s)
	// " {2,}" → " ", espaciar puntuación, \s+ → " ", strip: todo junto en una pasada equivalente.
	var out strings.Builder
	out.Grow(len(s) + 8)
	pendiente := false // hay espacio en blanco sin emitir
	hayTexto := false
	emitir := func(r rune) {
		if pendiente && hayTexto {
			out.WriteByte(' ')
		}
		pendiente = false
		hayTexto = true
		out.WriteRune(r)
	}
	for _, r := range s {
		switch {
		case unicode.Is(unicode.White_Space, r):
			pendiente = true
		case n.punt[r]:
			pendiente = true
			emitir(r)
			pendiente = true
		default:
			emitir(r)
		}
	}
	return out.String()
}
