package tok

import (
	"fmt"
	"math"
	"slices"
)

// Estrategias de texto largo: qué hacer con un texto que pasa del truncado (max_len en e5, max_tokens en L1).
const (
	EstCabeza     = "cabeza"      // los primeros tokens (lo de siempre)
	EstCabezaCola = "cabeza_cola" // la mitad de los primeros y la mitad de los últimos
	EstTrozos     = "trozos"      // ventanas con solape; cada una se decide y se agregan las probabilidades
	AggMax        = "max"
	AggMedia      = "media"

	// MaxTrozosDefecto es el tope de trozos por petición cuando no se dice otro; TopeMaxTrozos, el máximo admitido.
	MaxTrozosDefecto = 8
	TopeMaxTrozos    = 64
)

// TextoLargo configura la estrategia para textos que superan el truncado. El valor cero es «cabeza»: el comportamiento de
// antes, bit a bit.
type TextoLargo struct {
	Estrategia string `json:"estrategia,omitempty"` // cabeza (defecto) | cabeza_cola | trozos
	Agregacion string `json:"agregacion,omitempty"` // max | media (defecto media); solo con trozos
	Solape     int    `json:"solape,omitempty"`     // tokens compartidos entre trozos contiguos (defecto 0)
	MaxTrozos  int    `json:"max_trozos,omitempty"` // tope de trozos por petición (0 = MaxTrozosDefecto)
	// VentanaL1: tokens de la ventana de L1 con cabeza_cola y trozos (0 = max_tokens del modelo). Con cabeza no tiene efecto.
	VentanaL1 int `json:"ventana_l1,omitempty"`
}

// Activa dice si la estrategia cambia algo respecto a la cabeza.
func (t TextoLargo) Activa() bool { return t.Estrategia == EstCabezaCola || t.Estrategia == EstTrozos }

// Validar rechaza valores desconocidos o fuera de rango.
func (t TextoLargo) Validar() error {
	switch t.Estrategia {
	case "", EstCabeza, EstCabezaCola, EstTrozos:
	default:
		return fmt.Errorf("texto_largo: estrategia %q desconocida (cabeza, cabeza_cola o trozos)", t.Estrategia)
	}
	switch t.Agregacion {
	case "", AggMax, AggMedia:
	default:
		return fmt.Errorf("texto_largo: agregacion %q desconocida (max o media)", t.Agregacion)
	}
	if t.Solape < 0 || t.VentanaL1 < 0 || t.MaxTrozos < 0 || t.MaxTrozos > TopeMaxTrozos {
		return fmt.Errorf("texto_largo: solape y ventana_l1 deben ser ≥ 0 y max_trozos estar en 0..%d", TopeMaxTrozos)
	}
	if t.VentanaL1 != 0 && t.VentanaL1 < 3 {
		return fmt.Errorf("texto_largo: ventana_l1 %d demasiado pequeña (≥ 3 o 0)", t.VentanaL1)
	}
	return nil
}

// Trozos es el tope de trozos efectivo.
func (t TextoLargo) Trozos() int {
	if t.MaxTrozos <= 0 {
		return MaxTrozosDefecto
	}
	return t.MaxTrozos
}

// Agg es la agregación efectiva (media si no se dice).
func (t TextoLargo) Agg() string {
	if t.Agregacion == AggMax {
		return AggMax
	}
	return AggMedia
}

// Trocear devuelve las ventanas de cuerpo (tokens sin especiales) de a lo sumo n tokens que decide la estrategia. Si el
// cuerpo cabe, o la estrategia no está activa, devuelve una sola ventana: cuerpo[:min(n, len)], como la cabeza de siempre.
//   - cabeza_cola: los n/2 primeros y los n−n/2 últimos tokens, en una ventana.
//   - trozos: ventanas de n tokens con paso n−solape (el solape se acota a n−1), a lo sumo MaxTrozos, la primera es la cabeza.
//
// Las ventanas no comparten memoria con cuerpo.
func Trocear(cuerpo []int32, n int, t TextoLargo) [][]int32 {
	n = max(n, 1)
	if len(cuerpo) <= n || !t.Activa() {
		return [][]int32{slices.Clone(cuerpo[:min(n, len(cuerpo))])}
	}
	if t.Estrategia == EstCabezaCola {
		c := n / 2
		v := append(slices.Clone(cuerpo[:c]), cuerpo[len(cuerpo)-(n-c):]...)
		return [][]int32{v}
	}
	paso := n - min(max(t.Solape, 0), n-1)
	var out [][]int32
	for ini := 0; len(out) < t.Trozos(); ini += paso {
		fin := min(ini+n, len(cuerpo))
		out = append(out, slices.Clone(cuerpo[ini:fin]))
		if fin == len(cuerpo) {
			break
		}
	}
	return out
}

// NecesitaTokens es cuántos tokens de cuerpo hay que leer como mucho para esa estrategia con ventana n (0 = todos): con
// trozos basta el tramo que cubren los trozos; la cabeza_cola necesita el final del texto.
func (t TextoLargo) NecesitaTokens(n int) int {
	if t.Estrategia != EstTrozos {
		return 0
	}
	paso := n - min(max(t.Solape, 0), n-1)
	return (t.Trozos()-1)*paso + n + 1 // +1: saber si aún queda texto
}

// Ventanas tokeniza prefijo+texto como TokenizarMax y devuelve los ids (con <s> y </s>) de cada ventana de la estrategia, y si
// el texto superaba maxLen. Con un texto que cabe, o con «cabeza», es una sola ventana idéntica a TokenizarMax. Con trozos, cada
// ventana empieza por los tokens del prefijo («query: ») para que e5 vea lo mismo que en la cabeza.
func (t *Tokenizador) Ventanas(prefijo, texto string, maxLen int, tl TextoLargo) ([][]int32, bool) {
	maxLen = min(max(maxLen, 3), TopeMaxLen)
	n := maxLen - 2
	if !tl.Activa() {
		cuerpo, truncado := t.m.TokenizarTruncado(prefijo + texto)
		return [][]int32{envolver(cuerpo[:min(len(cuerpo), n)])}, truncado || len(cuerpo) > n
	}
	var cuerpo []int32
	if need := tl.NecesitaTokens(n); need > 0 {
		// 16 caracteres por token como cota generosa del texto que hay que leer
		cuerpo = t.m.TokenizarSinTope(prefijo+texto, need*16)
	} else {
		cuerpo = t.m.TokenizarSinTope(prefijo+texto, 0)
	}
	if len(cuerpo) <= n {
		return [][]int32{envolver(cuerpo)}, false
	}
	if tl.Estrategia == EstCabezaCola {
		return [][]int32{envolver(Trocear(cuerpo, n, tl)[0])}, true
	}
	pre := t.m.TokenizarSinTope(prefijo, 0)
	if len(pre) == 0 || len(pre) >= n-1 || !slices.Equal(cuerpo[:len(pre)], pre) {
		pre = nil // el prefijo no se tokeniza aparte igual: trozos sin prefijo repetido
	}
	resto := Trocear(cuerpo[len(pre):], n-len(pre), tl)
	out := make([][]int32, len(resto))
	for i, v := range resto {
		out[i] = envolver(append(slices.Clone(pre), v...))
	}
	return out, true
}

func envolver(cuerpo []int32) []int32 {
	ids := make([]int32, 0, len(cuerpo)+2)
	ids = append(ids, idBOS)
	ids = append(ids, cuerpo...)
	return append(ids, idEOS)
}

// AgregarSims reúne las similitudes de varias ventanas en una por opción: máximo o media. Con una ventana devuelve esa misma.
func AgregarSims(sims [][]float64, agg string) []float64 {
	if len(sims) == 1 {
		return sims[0]
	}
	out := make([]float64, len(sims[0]))
	for i := range out {
		if agg == AggMax {
			out[i] = math.Inf(-1)
		}
		for _, s := range sims {
			if agg == AggMax {
				out[i] = math.Max(out[i], s[i])
			} else {
				out[i] += s[i] / float64(len(sims))
			}
		}
	}
	return out
}

// AgregarProbs reúne las probabilidades por opción de las ventanas de un texto largo (ps, una por ventana; ids es el orden de las
// opciones de la pregunta): máximo o media por opción; en choice y score se renormaliza a 1; en noul, true es el agregado,
// false = 1−true y theta decide. Devuelve la respuesta (la opción de mayor probabilidad; en score, la mediana de la
// distribución, como L1; en noul, true si p ≥ theta) y su confianza. ok=false si no hay nada que agregar (sin ventanas o masa 0).
// Servidor y chispamovil la comparten para que decidan igual. En multi no se usa: se agregan las similitudes (AgregarSims).
func AgregarProbs(kind string, ids []string, ps []map[string]float64, agg string, theta float64) (probs map[string]float64, answer string, conf float64, ok bool) {
	if len(ps) == 0 {
		return nil, "", 0, false
	}
	probs = make(map[string]float64, len(ids))
	for _, id := range ids {
		var v float64
		if agg == AggMax {
			v = math.Inf(-1)
		}
		for _, p := range ps {
			if agg == AggMax {
				v = math.Max(v, p[id])
			} else {
				v += p[id] / float64(len(ps))
			}
		}
		probs[id] = v
	}
	if kind == "noul" {
		pt := probs["true"]
		probs = map[string]float64{"true": pt, "false": 1 - pt}
		if pt >= theta {
			return probs, "true", pt, true
		}
		return probs, "false", 1 - pt, true
	}
	var z float64
	for _, v := range probs {
		z += v
	}
	if z <= 0 {
		return nil, "", 0, false
	}
	for id := range probs {
		probs[id] /= z
	}
	if kind == "score" {
		var acc float64
		for _, id := range ids {
			acc += probs[id]
			if acc >= 0.5 {
				return probs, id, probs[id], true
			}
		}
	}
	for _, id := range ids {
		if probs[id] > conf {
			conf, answer = probs[id], id
		}
	}
	return probs, answer, conf, true
}
