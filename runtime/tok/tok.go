// Paquete tok es el tokenizador de multilingual-e5-small (XLM-R, sentencepiece unigram) en Go puro.
// Reusa el motor de runtime/l1 (Viterbi, charsmap, tabla hash) con un vocabulario propio, `.chispa-tok`,
// que exporta exportar.py desde tokenizer.json. Reproduce el pipeline de transformers que usa model/l2/modelo.py.
package tok

import (
	"fmt"
	"os"

	"chispa/runtime/l1"
)

const (
	// Prefijo de e5 para consultas.
	Prefijo = "query: "
	// PrefijoPasaje es el de e5 para pasajes: lo usa la torre de esquemas de L2 (model/l2/contrato-torre.md).
	PrefijoPasaje = "passage: "
	// MaxTok es el truncado por defecto (el de model/l2/modelo.py hasta G.7; incluye <s> y </s>). El truncado real sale de
	// los metadatos del modelo (`chispa.consulta.max_len` en el ONNX de L2 para la consulta, `max_len` de TORR para el
	// pasaje): ver TokenizarMax. MaxTok solo vale cuando no viene ninguno.
	MaxTok = 128
	// TopeMaxLen es el máximo duro del truncado (e5-small admite 512 posiciones).
	TopeMaxLen = 512

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

// ComprobarMaxLen devuelve un error claro si n no es un truncado válido: de 3 (<s>, un token y </s>) a TopeMaxLen.
func ComprobarMaxLen(n int) error {
	if n < 3 || n > TopeMaxLen {
		return fmt.Errorf("tok: max_len %d fuera de rango (3..%d)", n, TopeMaxLen)
	}
	return nil
}

// Tokenizar devuelve los ids de «query: »+texto con <s> y </s>, truncado a MaxTok (tokenizer(..., truncation=True,
// max_length=128)). Para otro truncado, TokenizarMax.
func (t *Tokenizador) Tokenizar(texto string) []int32 { return t.TokenizarMax(Prefijo, texto, MaxTok) }

// TokenizarPasaje es Tokenizar con «passage: » en lugar de «query: » (la torre de esquemas).
func (t *Tokenizador) TokenizarPasaje(texto string) []int32 {
	return t.TokenizarMax(PrefijoPasaje, texto, MaxTok)
}

// TokenizarCon tokeniza prefijo+texto con <s> y </s>, truncado a MaxTok. El prefijo forma parte del texto tokenizado.
func (t *Tokenizador) TokenizarCon(prefijo, texto string) []int32 { return t.TokenizarMax(prefijo, texto, MaxTok) }

// TokenizarMax tokeniza prefijo+texto con <s> y </s> y deja a lo sumo maxLen ids (incluidos los dos especiales), como
// tokenizer(..., truncation=True, max_length=maxLen). maxLen fuera de 3..TopeMaxLen se acota a ese rango: quien abre el modelo
// debe validarlo antes con ComprobarMaxLen y dar el error al usuario.
func (t *Tokenizador) TokenizarMax(prefijo, texto string, maxLen int) []int32 {
	maxLen = min(max(maxLen, 3), TopeMaxLen)
	cuerpo := t.m.Tokenizar(prefijo + texto)
	if len(cuerpo) > maxLen-2 {
		cuerpo = cuerpo[:maxLen-2]
	}
	ids := make([]int32, 0, len(cuerpo)+2)
	ids = append(ids, idBOS)
	ids = append(ids, cuerpo...)
	return append(ids, idEOS)
}
