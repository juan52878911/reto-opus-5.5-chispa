package chispamovil

import (
	"context"
	"encoding/binary"
	"encoding/json"
	"hash/fnv"
	"math"
	"slices"
	"sync"
	"testing"

	"chispa/format/chispa3"

	"github.com/juan52878911/chispa/server/decide"
)

const dTorre = 4

// hDe es una h determinista por texto (la «ONNX» falsa de la torre).
func hDe(texto string) []float32 {
	h := fnv.New64a()
	h.Write([]byte(texto))
	s := h.Sum64()
	v := make([]float32, dTorre)
	for i := range v {
		v[i] = float32(int64(s>>(8*i)&0xff)-128) / 64
	}
	return v
}

// grabador es el decide.CodificadorTorre del servidor que anota los textos que se le piden.
type grabador struct {
	mu     sync.Mutex
	textos []string
}

func (g *grabador) Torre(t string) ([]float32, error) {
	g.mu.Lock()
	g.textos = append(g.textos, t)
	g.mu.Unlock()
	return hDe(t), nil
}

type sesFalsa struct{ S [][]float32 }

func (s sesFalsa) Ranuras([]int64) ([][]float32, error) { return s.S, nil }

type tokFalso struct{}

func (tokFalso) IDs(string) []int64 { return []int64{0, 1, 2} }

var ranurasTorre = [][]float32{{1, -0.5, 0.25, 2}, {-1, 1, 0.5, 0}}

func calibTorre() chispa3.Calib {
	return chispa3.Calib{TauEscalate: 0.4, Tipos: map[string]chispa3.ParamsTipo{
		"choice": {T: 0.5}, "noul": {T: 1, A: 1.5, B: -0.5, Theta: 0.5},
		"score3": {T: 1, A: 1, B: 0, Theta: 0.5}, "score3#1": {T: 1, A: 1, B: 0.2, Theta: 0.5},
	}}
}

func servidorL2(g *grabador) *decide.L2 {
	esq, _ := chispa3.DecodificarEsquemas(mustEsq())
	return decide.NuevoL2Con(sesFalsa{ranurasTorre}, esq, calibTorre(), tokFalso{}).ConTorres(g, 64)
}

func mustEsq() []byte {
	b, err := chispa3.CodificarEsquemas(4, []chispa3.EntradaEsquema{
		{Hash: chispa3.HashEsquema("¿Qué quiere?", []string{"compra"}), Escala: 0.1, Vec: []int8{100, 0, 0, 0}},
	})
	if err != nil {
		panic(err)
	}
	return b
}

func movilL2(t *testing.T) *Chispa {
	esq, err := chispa3.DecodificarEsquemas(mustEsq())
	if err != nil {
		t.Fatal(err)
	}
	return &Chispa{esq: esq, tieneL2: true, calib: calibTorre()}
}

var preguntasTorre = []string{
	`{"question":"¿Cuál es el motivo?","kind":"choice","options":[{"id":"queja","description":"se queja del cobro"},{"id":"duda"},{"id":"baja","description":"quiere irse"}]}`,
	`{"question":"¿Es urgente?","kind":"noul","options":[{"id":"false"},{"id":"true","description":"urgente ya"}]}`,
	`{"question":"Gravedad","kind":"score","options":[{"id":"1"},{"id":"2","description":"media"},{"id":"3","description":"alta"}]}`,
	`{"question":"Gravedad","kind":"score","options":[{"id":"bajo"},{"id":"medio"},{"id":"alto"}]}`,
}

func torresBytes(textos []string) []byte {
	var b []byte
	for _, t := range textos {
		for _, x := range hDe(t) {
			b = binary.LittleEndian.AppendUint32(b, math.Float32bits(x))
		}
	}
	return b
}

// Los textos de torre de chispamovil son los que el servidor le pide a su CodificadorTorre (misma regla noul/score), y con
// torres instaladas L2 móvil decide igual que L2 del servidor con torres al vuelo.
func TestTextosYDecisionIgualesAlServidor(t *testing.T) {
	for _, q := range preguntasTorre {
		g := &grabador{}
		srv := servidorL2(g)
		p, err := leerPregunta(q)
		if err != nil {
			t.Fatal(err)
		}
		want, err := srv.Decidir(context.Background(), aDecideL2(p))
		if err != nil {
			t.Fatalf("%s: servidor: %v", q, err)
		}
		c := movilL2(t)
		var textos []string
		if err := json.Unmarshal([]byte(c.TextosTorreL2(q)), &textos); err != nil {
			t.Fatal(err)
		}
		if !slices.Equal(textos, g.textos) {
			t.Fatalf("%s: textos móvil %q ≠ servidor %q", q, textos, g.textos)
		}
		if c.TorresL2(q) {
			t.Fatalf("%s: sin instalar no debía haber torres", q)
		}
		if !c.InstalarTorresL2(q, torresBytes(textos), len(textos)) || !c.TorresL2(q) {
			t.Fatalf("%s: instalar", q)
		}
		if got := c.TextosTorreL2(q); got != "[]" {
			t.Fatalf("%s: con torres instaladas no se piden textos: %s", q, got)
		}
		r := leer(t, c.PuntuarL2(q, ranuras(ranurasTorre...), len(ranurasTorre)))
		if !r.Ok || r.Opina != (want.Conf > 0) || (r.Opina && (r.Answer != want.Answer || math.Abs(r.Conf-want.Conf) > 1e-9)) {
			t.Fatalf("%s: móvil %+v ≠ servidor %+v", q, r, want)
		}
		for k, v := range want.Probs {
			if math.Abs(r.Probs[k]-v) > 1e-9 {
				t.Fatalf("%s: prob %s móvil %v ≠ servidor %v", q, k, r.Probs[k], v)
			}
		}
	}
}

// Esquema nuevo → textos → torres falsas → L2 decide; las mismas opciones en otro orden siguen en caché (sin pedir textos
// distintos ni emparejar mal), y el esquema de ESQUEMAS no se toca.
func TestEsquemaNuevoOtroOrdenSigueEnCache(t *testing.T) {
	c := movilL2(t)
	q := preguntasTorre[0]
	var textos []string
	json.Unmarshal([]byte(c.TextosTorreL2(q)), &textos)
	if len(textos) != 3 || textos[0] != "passage: ¿Cuál es el motivo? · queja · se queja del cobro" || textos[1] != "passage: ¿Cuál es el motivo? · duda · " {
		t.Fatalf("textos: %q", textos)
	}
	if !c.InstalarTorresL2(q, torresBytes(textos), 3) {
		t.Fatal("instalar")
	}
	r1 := leer(t, c.PuntuarL2(q, ranuras(ranurasTorre...), 2))
	if !r1.Ok || !r1.Opina {
		t.Fatalf("L2: %+v", r1)
	}
	// mismas opciones, otro orden
	q2 := `{"question":"¿Cuál es el motivo?","kind":"choice","options":[{"id":"baja","description":"quiere irse"},{"id":"queja","description":"se queja del cobro"},{"id":"duda"}]}`
	if !c.TorresL2(q2) || c.TextosTorreL2(q2) != "[]" {
		t.Fatal("otro orden debía seguir en caché")
	}
	r2 := leer(t, c.PuntuarL2(q2, ranuras(ranurasTorre...), 2))
	if r1.Answer != r2.Answer || math.Abs(r1.Probs["baja"]-r2.Probs["baja"]) > 1e-12 || math.Abs(r1.Probs["queja"]-r2.Probs["queja"]) > 1e-12 {
		t.Fatalf("el orden cambió la decisión: %+v ≠ %+v", r1, r2)
	}
	// otra descripción = otra torre
	q3 := `{"question":"¿Cuál es el motivo?","kind":"choice","options":[{"id":"queja","description":"otra"},{"id":"duda"},{"id":"baja","description":"quiere irse"}]}`
	if c.TorresL2(q3) {
		t.Fatal("otra descripción no debía estar en caché")
	}
	// ESQUEMAS manda: la pregunta de fichero no pide textos
	if got := c.TextosTorreL2(`{"question":"¿Qué quiere?","kind":"choice","options":[{"id":"compra"}]}`); got != "[]" {
		t.Fatalf("ESQUEMAS: %s", got)
	}
}

func TestInstalarTorresL2Rechaza(t *testing.T) {
	c := movilL2(t)
	q := preguntasTorre[0]
	ok := torresBytes([]string{"a", "b", "c"})
	nan := slices.Clone(ok)
	binary.LittleEndian.PutUint32(nan[8:], math.Float32bits(float32(math.NaN())))
	for nombre, caso := range map[string]struct {
		b []byte
		n int
	}{"n de menos": {ok, 2}, "n cero": {ok, 0}, "bytes sueltos": {ok[:len(ok)-1], 3}, "NaN": {nan, 3}, "vacío": {nil, 3}} {
		if c.InstalarTorresL2(q, caso.b, caso.n) || c.TorresL2(q) {
			t.Fatalf("%s: debía rechazar", nombre)
		}
	}
	if (&Chispa{}).InstalarTorresL2(q, ok, 3) || c.InstalarTorresL2("{", ok, 3) {
		t.Fatal("sin L2 o pregunta rota debía dar false")
	}
	if c.TextosTorreL2("{") != "[]" || (&Chispa{}).TextosTorreL2(q) != "[]" {
		t.Fatal("textos sin L2 o pregunta rota deben ser []")
	}
}

func TestTorreMetadatosEIds(t *testing.T) {
	c := &Chispa{}
	if c.TieneTorre() || c.OnnxTorre() != nil || c.DimTorre() != 0 || c.IdsPasaje("x") != nil {
		t.Fatal("sin TORR todo vacío")
	}
	c.torre = &chispa3.Torre{Dim: 256, MaxLen: 8, Prefijo: "passage: ", ONNX: []byte{1, 2, 3}}
	if !c.TieneTorre() || len(c.OnnxTorre()) != 3 || c.DimTorre() != 256 {
		t.Fatal("metadatos")
	}
	if c.IdsPasaje("x") != nil { // sin tokenizador
		t.Fatal("sin tokenizador debía ser nil")
	}
}

// El ONNX de la sección TORR llega por OnnxTorre al abrir un .chispa que la trae.
func TestAbrirConTORR(t *testing.T) {
	tb, err := chispa3.CodificarTORR(chispa3.Torre{Dim: 256, MaxLen: 64, Prefijo: "passage: ", ONNX: []byte("onnx!")})
	if err != nil {
		t.Fatal(err)
	}
	c := ficheroV3(t, chispa3.Seccion{Tipo: chispa3.TORR, Datos: tb})
	if !c.TieneTorre() || string(c.OnnxTorre()) != "onnx!" || c.DimTorre() != 256 {
		t.Fatalf("TORR: %v %q %d", c.TieneTorre(), c.OnnxTorre(), c.DimTorre())
	}
}

// aDecideL2 es aDecide con el estado que usan los tests de L2.
func aDecideL2(p pregunta) decide.Pregunta {
	d := aDecide(p)
	d.ID, d.Estado = "q", "hola"
	return d
}
