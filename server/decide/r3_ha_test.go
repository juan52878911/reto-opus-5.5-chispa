package decide

import (
	"context"
	"math"
	"os"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	"chispa/format/chispa3"
)

// calib_coral.json está escrito a mano con la convención de a_calib_chispa (model/l2/calibrar.py): para scoreK,
// b = b[0] y «scoreK#j» (j = 1..K−2) lleva a = b[j] − b[j−1]. Los b completos que codifica:
var bCoral = map[int][]float64{3: {0.1, 0.9}, 5: {-0.5, 0.2, 0.9, 1.7}}

func calibCoralFixture(t *testing.T) chispa3.Calib {
	t.Helper()
	raw, err := os.ReadFile("testdata/calib_coral.json")
	if err != nil {
		t.Fatal(err)
	}
	c, err := chispa3.DecodificarCalib(raw)
	if err != nil {
		t.Fatal(err)
	}
	return c
}

func preguntaScore(K int) Pregunta {
	p := Pregunta{ID: "q", Texto: "Gravedad", Kind: KindScore}
	for i := 1; i <= K; i++ {
		p.Opciones = append(p.Opciones, Opcion{ID: strconv.Itoa(i)})
	}
	return p
}

func TestR3CoralConvencionDelExportador(t *testing.T) {
	cal := calibCoralFixture(t)
	for _, K := range []int{3, 5} {
		if _, ok := cal.Tipos["score"+strconv.Itoa(K)+"#"+strconv.Itoa(K-1)]; ok {
			t.Fatalf("K=%d: el fixture no debe tener #%d", K, K-1)
		}
		l := &L2{calib: cal}
		const s = 0.7
		r, err := l.score(preguntaScore(K), s)
		if err != nil || r.Conf == 0 {
			t.Fatalf("K=%d: L2 no opinó con claves del exportador: %+v %v", K, r, err)
		}
		a := cal.Tipos["score"+strconv.Itoa(K)].A
		b := bCoral[K]
		var suma float64
		for i := 0; i < K; i++ {
			hi, lo := 1.0, 0.0
			if i > 0 {
				hi = 1 / (1 + math.Exp(-(a*s - b[i-1])))
			}
			if i < K-1 {
				lo = 1 / (1 + math.Exp(-(a*s - b[i])))
			}
			want := hi - lo
			got := r.Probs[strconv.Itoa(i+1)]
			suma += got
			if math.Abs(got-want) > 1e-9 {
				t.Fatalf("K=%d p(%d)=%v, esperaba %v", K, i+1, got, want)
			}
		}
		if math.Abs(suma-1) > 1e-9 {
			t.Fatalf("K=%d suma %v", K, suma)
		}
	}
}

func TestR3SingleflightPanicoLiderRecibeError(t *testing.T) {
	l2 := armarL2Torres(t, codificadorFn(func() ([]float32, error) { panic("x") }), 0)
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	var (
		t0  torreDin
		err error
		pan any
	)
	func() {
		defer func() { pan = recover() }()
		t0, err = l2.torreUnica(ctx, "k", "texto")
	}()
	if pan != nil {
		t.Fatalf("el pánico no debe escapar: %v", pan)
	}
	if err == nil || !strings.Contains(err.Error(), "pánico") || len(t0.v) != 0 {
		t.Fatalf("el líder debe recibir error de pánico: torre=%v err=%v", t0, err)
	}
}

// Si la torre de una opción entra en pánico, L2 no decide con una torre vacía: devuelve el error.
func TestR3PanicoEnUnaOpcionNoDecideEnSilencio(t *testing.T) {
	var mu sync.Mutex
	n := 0
	l2 := armarL2Torres(t, codificadorFn(func() ([]float32, error) {
		mu.Lock()
		n++
		k := n
		mu.Unlock()
		if k == 2 {
			panic("tensor mal formado")
		}
		return []float32{1, 0}, nil
	}), 0)
	r, err := l2.Decidir(context.Background(), Pregunta{ID: "q", Estado: "hola", Texto: "esquema nuevo", Kind: KindChoice, Opciones: []Opcion{{ID: "a"}, {ID: "b"}}})
	if err == nil {
		t.Fatalf("esperaba error, salió %+v", r)
	}
}

func TestR3SimsDeValidaTodasLasTorres(t *testing.T) {
	l := NuevoL2Con(sesionFalsa{[][]float32{{1, 0}}}, nil, chispa3.Calib{}, tokFalso{})
	_, _, _, err := l.simsDe(Pregunta{Texto: "q"}, []torreDin{{v: []byte{1, 0}, e: 1}, {}})
	if err == nil {
		t.Fatal("una torre vacía debe dar error")
	}
}

// fuente de similitudes que expone las torres con las que puntuó.
type simConTorres struct {
	*simFalsa
	ts []torreDin
}

func (s *simConTorres) similitudesTorres(ctx context.Context, p Pregunta) ([][]float32, []float64, []torreDin, bool, error) {
	S, sims, ok, err := s.Similitudes(ctx, p)
	return S, sims, s.ts, ok, err
}

func TestR3L2cMezclaConLaTorreQuePuntuo(t *testing.T) {
	l, p, sf := montajeSoporteL2c(t, 1)
	l.ConSoporte(soplDe(t, p, 1), floatPtr(1))
	// Torres al vuelo distintas de las de ESQUEMAS: «a» apunta a (0,1) en lugar de (1,0).
	ts := []torreDin{{v: []byte{0, 127}, e: 1.0 / 127}, {v: []byte{127, 0}, e: 1.0 / 127}}
	conESQ := l.mezclarSimproto(p, sf.S, nil)
	conTs := l.mezclarSimproto(p, sf.S, ts)
	if math.Abs(conESQ[0]-conTs[0]) < 1e-3 {
		t.Fatalf("la prueba no distingue torres: %v vs %v", conESQ, conTs)
	}
	l.sim = &simConTorres{sf, ts}
	l0 := conL0(map[string]float64{"a": 0.5, "b": 0.5})
	r1, err := l.DecidirCon(context.Background(), p, l0)
	if err != nil {
		t.Fatal(err)
	}
	r2, _ := l.DecidirCon(context.Background(), p, l0)
	want := cabezaConj(p, mustConj(t, l, p), sf.S, sf.sims, conTs, l0["L0"].Probs)
	for id, v := range want.Probs {
		if r1.Probs[id] != r2.Probs[id] || math.Abs(r1.Probs[id]-v) > 1e-12 {
			t.Fatalf("p(%s): llamada 1 %v, llamada 2 %v, con la torre que puntuó %v", id, r1.Probs[id], r2.Probs[id], v)
		}
	}
}

func mustConj(t *testing.T, l *L2c, p Pregunta) *chispa3.EntradaConj {
	t.Helper()
	e, ok := l.conj.Buscar(ClaveConj(p))
	if !ok {
		t.Fatal("sin CONJ")
	}
	return e
}
