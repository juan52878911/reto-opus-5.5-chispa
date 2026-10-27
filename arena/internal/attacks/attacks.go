// Package attacks implements meaning-preserving text mutation operators and a
// probability-guided insertion search against the arena's detectors.
package attacks

import (
	"context"
	"math/rand/v2"
	"strings"
	"unicode"

	"github.com/juan52878911/chispa/contracts"
)

// Op is one composable mutation operator.
type Op struct {
	Name  string
	Apply func(r *rand.Rand, text string) (string, map[string]any)
}

// BenignPool is set by the caller with innocent fragments for benign_pad.
var BenignPool []string

var defaultBenign = []string{
	"hola buenas tardes", "gracias por todo", "jajaja", "como estas?", "bendiciones",
	"saludos a la familia", "nos vemos mañana", "feliz día", "ok listo",
}

var emojis = []string{"😊", "🙏", "👍", "😂", "🎉", "❤️", "🔥", "✅", "😅", "🇨🇴"}

var lookalikes = map[rune]rune{
	'a': 'а', 'e': 'е', 'o': 'о', 'p': 'р', 'c': 'с', 'x': 'х', 'i': 'і', 'y': 'у', 's': 'ѕ',
	'A': 'А', 'E': 'Е', 'O': 'О', 'P': 'Р', 'C': 'С', 'X': 'Х', 'I': 'І', 'Y': 'У', 'S': 'Ѕ',
	'j': 'ј', 'h': 'һ', 'B': 'В', 'H': 'Н', 'M': 'М', 'T': 'Т',
}

var swaps = map[string][]string{
	"que": {"q", "k"}, "porque": {"xq", "pq"}, "por favor": {"porfa", "pls"},
	"dinero": {"money", "plata"}, "gratis": {"free"}, "urgente": {"asap"},
	"ahora": {"now"}, "cuenta": {"account"}, "ganar": {"win"}, "premio": {"prize"},
	"clic": {"click"}, "click": {"clic"}, "link": {"enlace"}, "ya": {"now"},
}

// Ops returns all operators.
func Ops() []Op {
	return []Op{
		{"homoglyph", homoglyph},
		{"char_noise", charNoise},
		{"emoji_inject", emojiInject},
		{"benign_pad", benignPad},
		{"code_switch", codeSwitch},
		{"format", format},
	}
}

// Mutate applies n distinct random operators in sequence.
func Mutate(r *rand.Rand, text string, n int) (string, []contracts.Operator) {
	ops := Ops()
	if n > len(ops) {
		n = len(ops)
	}
	r.Shuffle(len(ops), func(i, j int) { ops[i], ops[j] = ops[j], ops[i] })
	var used []contracts.Operator
	for _, op := range ops[:n] {
		var p map[string]any
		text, p = op.Apply(r, text)
		used = append(used, contracts.Operator{Name: op.Name, Params: p})
	}
	return text, used
}

func homoglyph(r *rand.Rand, text string) (string, map[string]any) {
	rate := 0.05 + r.Float64()*0.25
	rs := []rune(text)
	n := 0
	for i, c := range rs {
		if l, ok := lookalikes[c]; ok && r.Float64() < rate {
			rs[i] = l
			n++
		}
	}
	return string(rs), map[string]any{"rate": rate, "replaced": n}
}

func charNoise(r *rand.Rand, text string) (string, map[string]any) {
	mode := []string{"zwsp", "shy", "dup"}[r.IntN(3)]
	rate := 0.1 + r.Float64()*0.3
	var b strings.Builder
	rs := []rune(text)
	n := 0
	for i, c := range rs {
		b.WriteRune(c)
		if !unicode.IsLetter(c) || r.Float64() >= rate {
			continue
		}
		switch mode {
		case "dup":
			b.WriteRune(c)
			if r.IntN(2) == 0 {
				b.WriteRune(c)
			}
			n++
		default:
			if i+1 < len(rs) && unicode.IsLetter(rs[i+1]) {
				if mode == "zwsp" {
					b.WriteRune('​')
				} else {
					b.WriteRune('­')
				}
				n++
			}
		}
	}
	return b.String(), map[string]any{"mode": mode, "rate": rate, "inserted": n}
}

// wordEnds returns byte offsets just after each non-space run.
func wordEnds(text string) []int {
	var ends []int
	in := false
	for i, c := range text {
		sp := unicode.IsSpace(c)
		if sp && in {
			ends = append(ends, i)
		}
		in = !sp
	}
	if in {
		ends = append(ends, len(text))
	}
	return ends
}

// insertAt inserts frag at boundary index pos (0 = start, k = after k-th word).
func insertAt(text, frag string, pos int) string {
	if pos <= 0 {
		return frag + " " + text
	}
	ends := wordEnds(text)
	if pos > len(ends) {
		pos = len(ends)
	}
	if pos == 0 {
		return frag + " " + text
	}
	o := ends[pos-1]
	return text[:o] + " " + frag + text[o:]
}

func emojiInject(r *rand.Rand, text string) (string, map[string]any) {
	k := 1 + r.IntN(3)
	var used []string
	for i := 0; i < k; i++ {
		e := emojis[r.IntN(len(emojis))]
		pos := r.IntN(len(wordEnds(text)) + 1)
		text = insertAt(text, e, pos)
		used = append(used, e)
	}
	return text, map[string]any{"emojis": used}
}

func benignPad(r *rand.Rand, text string) (string, map[string]any) {
	pool := BenignPool
	if len(pool) == 0 {
		pool = defaultBenign
	}
	where := r.IntN(3) // 0 prepend, 1 append, 2 both
	p := map[string]any{}
	if where != 1 {
		f := pool[r.IntN(len(pool))]
		text = f + " " + text
		p["prefix"] = f
	}
	if where != 0 {
		f := pool[r.IntN(len(pool))]
		text = text + " " + f
		p["suffix"] = f
	}
	return text, p
}

func codeSwitch(r *rand.Rand, text string) (string, map[string]any) {
	var swapped []string
	// two-word phrase first
	for from, tos := range swaps {
		if !strings.Contains(from, " ") {
			continue
		}
		if i := indexFold(text, from); i >= 0 {
			to := tos[r.IntN(len(tos))]
			text = text[:i] + to + text[i+len(from):]
			swapped = append(swapped, from+"->"+to)
		}
	}
	fields := strings.Split(text, " ")
	for i, f := range fields {
		core := strings.TrimFunc(f, func(c rune) bool { return !unicode.IsLetter(c) && !unicode.IsDigit(c) })
		if core == "" {
			continue
		}
		tos, ok := swaps[strings.ToLower(core)]
		if !ok || r.Float64() < 0.2 {
			continue
		}
		to := tos[r.IntN(len(tos))]
		fields[i] = strings.Replace(f, core, to, 1)
		swapped = append(swapped, strings.ToLower(core)+"->"+to)
	}
	return strings.Join(fields, " "), map[string]any{"swapped": swapped}
}

func indexFold(s, sub string) int {
	return strings.Index(strings.ToLower(s), sub) // ASCII sub; lowercase keeps byte length for ASCII text
}

func format(r *rand.Rand, text string) (string, map[string]any) {
	mode := []string{"linebreak", "randcase", "spaces", "spaced"}[r.IntN(4)]
	fields := strings.Fields(text)
	if len(fields) == 0 {
		return text, map[string]any{"mode": mode}
	}
	switch mode {
	case "linebreak":
		var b strings.Builder
		for i, f := range fields {
			if i > 0 {
				if r.Float64() < 0.4 {
					b.WriteString("\n")
				} else {
					b.WriteString(" ")
				}
			}
			b.WriteString(f)
		}
		return b.String(), map[string]any{"mode": mode}
	case "randcase":
		rs := []rune(text)
		for i, c := range rs {
			if r.IntN(2) == 0 {
				rs[i] = unicode.ToUpper(c)
			} else {
				rs[i] = unicode.ToLower(c)
			}
		}
		return string(rs), map[string]any{"mode": mode}
	case "spaces":
		var b strings.Builder
		for i, f := range fields {
			if i > 0 {
				b.WriteString(strings.Repeat(" ", 1+r.IntN(3)))
			}
			b.WriteString(f)
		}
		return b.String(), map[string]any{"mode": mode}
	}
	idx := r.IntN(len(fields))
	for t := 0; t < len(fields) && len([]rune(fields[idx])) < 3; t++ {
		idx = (idx + 1) % len(fields)
	}
	parts := strings.Split(string(fields[idx]), "")
	fields[idx] = strings.Join(parts, " ")
	return strings.Join(fields, " "), map[string]any{"mode": mode, "word_index": idx}
}

// Scorer returns the defenders' probability of the TRUE label per text.
type Scorer func(ctx context.Context, texts []string) ([]float64, error)

// Search is a probability-guided greedy insertion search.
func Search(ctx context.Context, r *rand.Rand, text string, pool []string, budget, width int, score Scorer) (string, []contracts.Operator, int, float64, error) {
	var ops []contracts.Operator
	if len(pool) == 0 || width < 1 {
		s, err := score(ctx, []string{text})
		if err != nil || len(s) == 0 {
			return text, ops, 0, 1, err
		}
		return text, ops, 0, s[0], nil
	}
	s0, err := score(ctx, []string{text})
	if err != nil {
		return text, ops, 0, 1, err
	}
	cur := 1.0
	if len(s0) > 0 {
		cur = s0[0]
	}
	iters := 0
	for iters < budget && cur >= 0.5 {
		if err := ctx.Err(); err != nil {
			return text, ops, iters, cur, err
		}
		iters++
		nb := len(wordEnds(text)) + 1
		cands := make([]string, width)
		frags := make([]string, width)
		poss := make([]int, width)
		for i := range cands {
			frags[i] = pool[r.IntN(len(pool))]
			poss[i] = r.IntN(nb)
			cands[i] = insertAt(text, frags[i], poss[i])
		}
		sc, err := score(ctx, cands)
		if err != nil {
			return text, ops, iters, cur, err
		}
		best := -1
		for i, v := range sc {
			if i < width && v < cur && (best < 0 || v < sc[best]) {
				best = i
			}
		}
		if best < 0 {
			continue
		}
		text, cur = cands[best], sc[best]
		ops = append(ops, contracts.Operator{Name: "search_insert", Params: map[string]any{"fragment": frags[best], "pos": poss[best]}})
	}
	return text, ops, iters, cur, nil
}
