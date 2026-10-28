// Paquete tok es el tokenizador de multilingual-e5-small (XLM-R, sentencepiece unigram) en Go puro.
// Reusa el motor de runtime/l1 (Viterbi, charsmap, tabla hash) con un vocabulario propio, `.chispa-tok`,
// que exporta exportar.py desde tokenizer.json. Reproduce el pipeline de transformers que usa model/l2/modelo.py.
package tok

import (
	"os"

	"chispa/runtime/l1"
)

const (
	// Prefijo de e5 para consultas.
	Prefijo = "query: "
	// MaxTok es el truncado de model/l2/modelo.py (incluye <s> y </s>).
	MaxTok = 128

	idBOS int32 = 0
	idEOS int32 = 2
)

// Tokenizador es seguro para uso concurrente.
type Tokenizador struct {
	m *l1.Modelo
}

// Desde interpreta un .chispa-tok; data debe seguir vivo mientras se use.
func Desde(data []byte) (*Tokenizador, error) {
	m, err := l1.DesdeTokenizador(data)
	if err != nil {
		return nil, err
	}
	return &Tokenizador{m}, nil
}

// Abrir lee un fichero .chispa-tok.
func Abrir(ruta string) (*Tokenizador, error) {
	b, err := os.ReadFile(ruta)
	if err != nil {
		return nil, err
	}
	return Desde(b)
}

// Tokenizar devuelve los ids de «query: »+texto con <s> y </s>, truncado a MaxTok como
// tokenizer(..., truncation=True, max_length=128).
func (t *Tokenizador) Tokenizar(texto string) []int32 {
	cuerpo := t.m.Tokenizar(Prefijo + texto)
	if len(cuerpo) > MaxTok-2 {
		cuerpo = cuerpo[:MaxTok-2]
	}
	ids := make([]int32, 0, len(cuerpo)+2)
	ids = append(ids, idBOS)
	ids = append(ids, cuerpo...)
	return append(ids, idEOS)
}
