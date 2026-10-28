// Paquete l1 es el runtime del L1 de Chispa: un Model2Vec (embedding estático) en Go puro,
// con pesos int8 y aritmética entera para que el resultado sea idéntico en amd64 y arm64.
package l1

import (
	"crypto/sha256"
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"math"
)

const (
	versionFormato = 1
	tamCabecera    = 256
	escalaBits     = 32
)

var magia = [8]byte{'C', 'H', 'L', '1'}

// Índices de sección, en el orden en que las escribe exportar.py.
const (
	secParams = iota
	secCharsmap
	secPiezas
	secOffsets
	secScores
	secHash
	secPesos
	secEscalas
	secPrefijos
	numSecciones
)

type params struct {
	MaxTokens    int            `json:"max_tokens"`
	RecorteTexto int            `json:"recorte_texto"`
	MaxPiezaCar  int            `json:"max_pieza_car"`
	UnkID        int            `json:"unk_id"`
	UnkPenaliz   float64        `json:"unk_penalizacion"`
	MinScore     float64        `json:"min_score"`
	Metaspace    string         `json:"metaspace"`
	Prepend      string         `json:"prepend"`
	Anadidos     map[string]int `json:"anadidos"`
	Puntuacion   string         `json:"puntuacion"`
	Normalize    bool           `json:"normalize"`
	EscalaBits   int            `json:"escala_bits"`
	Dim          int            `json:"dim"`
	ModeloOrigen string         `json:"modelo_origen"`
	Tokenizador  string         `json:"tokenizador"`
	MedianaPieza int            `json:"mediana_pieza"`
	Modo         string         `json:"modo,omitempty"`
}

// Modelo es un .chispa-l1 cargado. Es de solo lectura y seguro para uso concurrente.
type Modelo struct {
	data     []byte
	cerrar   func() error
	dim      int
	vocab    int
	tablaB   uint
	prefB    uint
	sec      [numSecciones][]byte
	p        params
	unkScore float64
	norm     normalizador
	anadidos []anadido
	hashSHA  [32]byte
}

type anadido struct {
	texto string
	id    int32
}

// Desde interpreta data como un .chispa-l1. data debe seguir vivo mientras se use el modelo.
func Desde(data []byte) (*Modelo, error) {
	if len(data) < tamCabecera || [8]byte(data[:8]) != magia {
		return nil, errors.New("l1: no es un .chispa-l1")
	}
	le := binary.LittleEndian
	if v := le.Uint32(data[8:]); v != versionFormato {
		return nil, fmt.Errorf("l1: versión %d no soportada", v)
	}
	m := &Modelo{data: data}
	m.dim = int(le.Uint32(data[12:]))
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
	case m.dim <= 0 || m.dim != m.p.Dim || m.p.EscalaBits != escalaBits || m.p.Metaspace == "" || m.p.Prepend != "always":
		return nil, errors.New("l1: parámetros incoherentes")
	case len(m.sec[secPesos]) != v*m.dim, len(m.sec[secEscalas]) != 4*v, len(m.sec[secScores]) != 8*v,
		len(m.sec[secOffsets]) != 4*(v+1), len(m.sec[secHash]) != 4<<m.tablaB, len(m.sec[secPrefijos]) != 1<<(m.prefB-3):
		return nil, errors.New("l1: tamaños de sección incoherentes")
	}
	if int(le.Uint32(m.sec[secOffsets][4*v:])) != len(m.sec[secPiezas]) {
		return nil, errors.New("l1: offsets de piezas incoherentes")
	}
	m.unkScore = m.p.MinScore - m.p.UnkPenaliz
	n, err := nuevoNormalizador(m.sec[secCharsmap], m.p.Puntuacion)
	if err != nil {
		return nil, err
	}
	m.norm = n
	for t, id := range m.p.Anadidos {
		m.anadidos = append(m.anadidos, anadido{t, int32(id)})
	}
	return m, nil
}

// Verificar recalcula el sha256 del cuerpo y lo compara con el de la cabecera.
func (m *Modelo) Verificar() error {
	if sha256.Sum256(m.data[tamCabecera:]) != m.hashSHA {
		return errors.New("l1: hash del cuerpo no coincide")
	}
	return nil
}

// Hash devuelve el sha256 del cuerpo declarado en la cabecera.
func (m *Modelo) Hash() [32]byte { return m.hashSHA }

// Dim es la dimensión del embedding.
func (m *Modelo) Dim() int { return m.dim }

// Vocab es el tamaño del vocabulario.
func (m *Modelo) Vocab() int { return m.vocab }

func (m *Modelo) score(id int32) float64 {
	return math.Float64frombits(binary.LittleEndian.Uint64(m.sec[secScores][8*int(id):]))
}

// Cerrar libera el mapeo de memoria si el modelo se abrió con Abrir.
func (m *Modelo) Cerrar() error {
	if m.cerrar != nil {
		return m.cerrar()
	}
	return nil
}
