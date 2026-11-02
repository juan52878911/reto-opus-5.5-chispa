package decide

import "chispa/runtime/tok"

// TextoLargo es la estrategia para textos que pasan del truncado de L1 y L2 (config `texto_largo`); el valor cero es «cabeza».
type TextoLargo = tok.TextoLargo

// TokenizadorTrozos lo implementa el tokenizador que sabe trocear: las ventanas de ids de la estrategia y si el texto superaba
// max_len. Con «cabeza» es una sola ventana igual que IDs. L2 lo usa si el tokenizador lo implementa; si no, IDs.
type TokenizadorTrozos interface {
	Trozos(texto string, tl TextoLargo) (ventanas [][]int64, largo bool)
}

// agregarSims reúne las similitudes de varias ventanas en una por opción: máximo o media (tok.AgregarSims).
func agregarSims(sims [][]float64, agg string) []float64 { return tok.AgregarSims(sims, agg) }

// agregarRespuestas reúne las respuestas de las ventanas de un texto largo agregando las probabilidades por opción (tok.AgregarProbs,
// compartida con chispamovil). Una sola ventana, o una sin opinión (Conf 0), devuelve la primera tal cual. En multi no se usa:
// se agregan las similitudes.
func agregarRespuestas(p Pregunta, rs []Respuesta, agg string, theta float64) Respuesta {
	if !scoreValido(p) {
		return Respuesta{} // score con ids que no son 1..K: sin escala, no opina
	}
	if len(rs) == 1 || rs[0].Conf == 0 || rs[0].Probs == nil {
		return rs[0]
	}
	ids := make([]string, len(p.Opciones))
	for i, o := range p.Opciones {
		ids[i] = o.ID
	}
	ps := make([]map[string]float64, len(rs))
	for i, r := range rs {
		ps[i] = r.Probs
	}
	probs, ans, conf, ok := tok.AgregarProbs(p.Kind, ids, ps, agg, theta)
	if !ok {
		return rs[0]
	}
	return Respuesta{Probs: probs, Answer: ans, Conf: conf}
}
