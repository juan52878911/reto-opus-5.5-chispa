package decide

import "chispa/runtime/tok"

// TokenizadorE5 adapta runtime/tok a Tokenizador y TokenizadorPasaje (ids int64 para el ONNX). Los truncados salen de los
// metadatos del .chispa (ArmarDesde llama a ConMaxLen con `chispa.consulta.max_len` del ONNX de L2 y `max_len` de TORR);
// sin ellos, tok.MaxTok (128).
type TokenizadorE5 struct {
	t                *tok.Tokenizador
	consulta, pasaje int // 0 = tok.MaxTok
}

func NuevoTokenizadorE5(t *tok.Tokenizador) TokenizadorE5 { return TokenizadorE5{t: t} }

// ConMaxLen implementa TokenizadorMaxLen: una copia con otros truncados.
func (e TokenizadorE5) ConMaxLen(consulta, pasaje int) Tokenizador {
	e.consulta, e.pasaje = consulta, pasaje
	return e
}

func maxOPorDefecto(n int) int {
	if n <= 0 {
		return tok.MaxTok
	}
	return n
}

func aInt64(ids []int32) []int64 {
	out := make([]int64, len(ids))
	for i, v := range ids {
		out[i] = int64(v)
	}
	return out
}

// IDs: «query: »+texto con <s> y </s>, a lo sumo max_len de la consulta.
func (e TokenizadorE5) IDs(texto string) []int64 {
	return aInt64(e.t.TokenizarMax(tok.Prefijo, texto, maxOPorDefecto(e.consulta)))
}

// IDsPasaje: «passage: »+texto (la torre de esquemas), a lo sumo max_len de TORR.
func (e TokenizadorE5) IDsPasaje(texto string) []int64 {
	return aInt64(e.t.TokenizarMax(tok.PrefijoPasaje, texto, maxOPorDefecto(e.pasaje)))
}

// Trozos implementa TokenizadorTrozos: las ventanas de la consulta según la estrategia (max_len de la consulta) y si el texto
// la superaba. Con «cabeza» es una ventana igual que IDs.
func (e TokenizadorE5) Trozos(texto string, tl TextoLargo) ([][]int64, bool) {
	v, largo := e.t.Ventanas(tok.Prefijo, texto, maxOPorDefecto(e.consulta), tl)
	out := make([][]int64, len(v))
	for i, w := range v {
		out[i] = aInt64(w)
	}
	return out, largo
}
