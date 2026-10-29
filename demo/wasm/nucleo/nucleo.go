// Package nucleo es la lógica de la demo sin syscall/js, para poder probarla en nativo y en wasm con el mismo código.
//
// Decidir hace lo mismo que la capa L1 del servidor (server/decide/l1.go) para preguntas «choice»: coseno entre el
// mensaje y «pregunta · opción · descripción», y softmax del coseno / T con T = 0,05.
package nucleo

import (
	"crypto/sha256"
	"encoding/binary"
	"encoding/json"
	"errors"
	"math"
	"sort"
	"strings"
	"time"

	"chispa/runtime/l1"
)

const temperatura = 0.05

type Opcion struct {
	ID          string `json:"id"`
	Description string `json:"description,omitempty"`
}

type Pregunta struct {
	Texto    string   `json:"question"`
	Kind     string   `json:"kind"`
	Opciones []Opcion `json:"options"`
}

type Respuesta struct {
	Answer string             `json:"answer"`
	Conf   float64            `json:"conf"`
	Probs  map[string]float64 `json:"probs"`
}

type Demo struct {
	M     *l1.Modelo
	clave string
	ops   [][]float32
}

func Nueva(datos []byte) (*Demo, error) {
	m, err := l1.Desde(datos)
	if err != nil {
		return nil, err
	}
	if err := m.Verificar(); err != nil {
		return nil, err
	}
	return &Demo{M: m}, nil
}

// opciones calcula (y recuerda la última) la torre de opciones de la pregunta.
func (d *Demo) opciones(p Pregunta) [][]float32 {
	clave := p.Texto
	for _, o := range p.Opciones {
		clave += "\x00" + o.ID + "\x01" + o.Description
	}
	if clave == d.clave && d.ops != nil {
		return d.ops
	}
	d.ops = make([][]float32, len(p.Opciones))
	for i, o := range p.Opciones {
		s := []string{p.Texto, o.ID}
		if o.Description != "" {
			s = append(s, o.Description)
		}
		d.ops[i] = make([]float32, d.M.Dim())
		d.M.Embed(strings.Join(s, " · "), d.ops[i])
	}
	d.clave = clave
	return d.ops
}

// Decidir clasifica texto frente a la pregunta (JSON). Sin tokens en el texto devuelve Answer vacío.
func (d *Demo) Decidir(texto, preguntaJSON string) (Respuesta, error) {
	var p Pregunta
	if err := json.Unmarshal([]byte(preguntaJSON), &p); err != nil {
		return Respuesta{}, err
	}
	if len(p.Opciones) == 0 || (p.Kind != "" && p.Kind != "choice") {
		return Respuesta{}, errors.New("la demo solo admite preguntas kind=choice con opciones")
	}
	return d.decidir(texto, p), nil
}

func (d *Demo) decidir(texto string, p Pregunta) Respuesta {
	ops := d.opciones(p)
	msg := make([]float32, d.M.Dim())
	if !d.M.Embed(texto, msg) {
		return Respuesta{Probs: map[string]float64{}}
	}
	sims := make([]float64, len(ops))
	mx := math.Inf(-1)
	for i, o := range ops {
		for j := range msg {
			sims[i] += float64(msg[j]) * float64(o[j])
		}
		mx = math.Max(mx, sims[i])
	}
	var z float64
	ex := make([]float64, len(sims))
	for i, s := range sims {
		ex[i] = math.Exp((s - mx) / temperatura)
		z += ex[i]
	}
	r := Respuesta{Probs: make(map[string]float64, len(sims))}
	for i, o := range p.Opciones {
		pr := ex[i] / z
		r.Probs[o.ID] = pr
		if pr > r.Conf {
			r.Conf, r.Answer = pr, o.ID
		}
	}
	return r
}

// Huella es el sha256 de los embeddings float32 LE de los textos (vector cero si no hay tokens), en hex.
func (d *Demo) Huella(textos []string) string {
	h := sha256.New()
	v := make([]float32, d.M.Dim())
	b := make([]byte, 4*len(v))
	for _, t := range textos {
		d.M.Embed(t, v)
		for i, x := range v {
			binary.LittleEndian.PutUint32(b[4*i:], math.Float32bits(x))
		}
		h.Write(b)
	}
	return hexa(h.Sum(nil))
}

func hexa(b []byte) string {
	const dig = "0123456789abcdef"
	s := make([]byte, 2*len(b))
	for i, c := range b {
		s[2*i], s[2*i+1] = dig[c>>4], dig[c&15]
	}
	return string(s)
}

const relleno = "quiero saber el precio y la disponibilidad del producto que vi ayer en la tienda porque mi pedido llegó con la caja rota y necesito ayuda para cambiarlo antes del viernes gracias buenos días "

// TextoDeTokens devuelve un texto en español cuyo número de tokens es exactamente n (o el más cercano por debajo).
func (d *Demo) TextoDeTokens(n int) (string, int) {
	pal := strings.Fields(relleno)
	mejor, nm := "", 0
	var sb []string
	for i := 0; len(d.M.Tokenizar(strings.Join(sb, " "))) < n && i < 4*n+16; i++ {
		sb = append(sb, pal[i%len(pal)])
		s := strings.Join(sb, " ")
		if k := len(d.M.Tokenizar(s)); k <= n {
			mejor, nm = s, k
		}
	}
	return mejor, nm
}

type Latencia struct {
	Tokens int     `json:"tokens"`
	Real   int     `json:"tokens_reales"`
	Reps   int     `json:"reps"`
	P50us  float64 `json:"p50_us"`
	P99us  float64 `json:"p99_us"`
}

// Medir cronometra Decidir (embedding del mensaje + coseno con las opciones, torre ya en caché) reps veces sobre
// un texto de n tokens.
func (d *Demo) Medir(n, reps int, preguntaJSON string) (Latencia, error) {
	var p Pregunta
	if err := json.Unmarshal([]byte(preguntaJSON), &p); err != nil {
		return Latencia{}, err
	}
	txt, real := d.TextoDeTokens(n)
	d.decidir(txt, p) // calienta la caché de opciones
	t := make([]float64, reps)
	for i := range t {
		t0 := time.Now()
		d.decidir(txt, p)
		t[i] = float64(time.Since(t0).Nanoseconds()) / 1e3
	}
	sort.Float64s(t)
	pct := func(q float64) float64 { return t[int(math.Ceil(q*float64(reps)))-1] }
	return Latencia{Tokens: n, Real: real, Reps: reps, P50us: pct(0.50), P99us: pct(0.99)}, nil
}

// Lote es el resultado de decidir varios textos en una sola llamada.
type Lote struct {
	N       int      `json:"n"`
	Answers []string `json:"answers"`
	TotalUs float64  `json:"total_us"`
}

// DecidirLote decide cada texto frente a la pregunta (la torre de opciones se calcula una sola vez) y mide el
// tiempo total del lote dentro del wasm, sin el coste de cruzar a JS por texto.
func (d *Demo) DecidirLote(textos []string, preguntaJSON string) (Lote, error) {
	var p Pregunta
	if err := json.Unmarshal([]byte(preguntaJSON), &p); err != nil {
		return Lote{}, err
	}
	if len(p.Opciones) == 0 || (p.Kind != "" && p.Kind != "choice") {
		return Lote{}, errors.New("la demo solo admite preguntas kind=choice con opciones")
	}
	d.opciones(p)
	l := Lote{N: len(textos), Answers: make([]string, len(textos))}
	t0 := time.Now()
	for i, t := range textos {
		l.Answers[i] = d.decidir(t, p).Answer
	}
	l.TotalUs = float64(time.Since(t0).Nanoseconds()) / 1e3
	return l, nil
}
