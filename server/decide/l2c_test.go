package decide

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"math"
	"math/rand/v2"
	"os"
	"testing"

	"chispa/format/chispa3"
)

// paridad.json lo genera sdk/python/tests/fixture_conjunta.py con conjunta.Cabeza de model/l2.
type fixtureConj struct {
	Pregunta   string
	Opciones   []string
	Tolerancia float64
	ConjB64    string `json:"conj_b64"`
	Casos      []struct {
		S     [][]float32
		Sims  []float64
		L0    map[string]float64
		Sp    []float64
		L2    []float64
		Probs []float64
	}
}

func leerFixtureConj(t *testing.T) (fixtureConj, *chispa3.Conj, Pregunta) {
	t.Helper()
	b, err := os.ReadFile("../../model/l2/tests/fixtures_conjunta/paridad.json")
	if err != nil {
		t.Fatal(err)
	}
	var fx fixtureConj
	if err := json.Unmarshal(b, &fx); err != nil {
		t.Fatal(err)
	}
	raw, err := base64.StdEncoding.DecodeString(fx.ConjB64)
	if err != nil {
		t.Fatal(err)
	}
	conj, err := chispa3.DecodificarConj(raw)
	if err != nil {
		t.Fatal(err)
	}
	p := Pregunta{ID: "q", Texto: fx.Pregunta, Kind: KindChoice}
	for _, o := range fx.Opciones {
		p.Opciones = append(p.Opciones, Opcion{ID: o})
	}
	return fx, conj, p
}

// exacto usa simprotoRef (float, sin cuantizar S) mientras dure la prueba: paridad estricta con Python.
func exacto(t *testing.T) {
	t.Helper()
	simprotoActual = simprotoRef
	t.Cleanup(func() { simprotoActual = simproto })
}

// La implementación entera (S cuantizada a int8) queda cerca de Python: Δp < 1e-2 en los casos del fixture.
func TestL2cParidadEnteraConPython(t *testing.T) {
	fx, conj, p := leerFixtureConj(t)
	e, _ := conj.Buscar(ClaveConj(p))
	var peor float64
	for n, c := range fx.Casos {
		r := cabezaConj(p, e, c.S, c.Sims, c.L0)
		for i, o := range p.Opciones {
			peor = math.Max(peor, math.Abs(r.Probs[o.ID]-c.Probs[i]))
		}
		_ = n
	}
	t.Logf("peor |Δp| entera = %.3g", peor)
	if peor > 1e-2 {
		t.Fatalf("Δp %v", peor)
	}
}

func TestL2cParidadConPython(t *testing.T) {
	exacto(t)
	fx, conj, p := leerFixtureConj(t)
	e, ok := conj.Buscar(ClaveConj(p))
	if !ok {
		t.Fatal("la clave de CONJ de Go no es la que escribió Python")
	}
	var peor float64
	for n, c := range fx.Casos {
		// Intermedios: simproto con los prototipos int8 y P_L2.
		sp := simprotoActual(e, c.S, p.Opciones)
		for i := range sp {
			if d := math.Abs(sp[i] - c.Sp[i]); d > 1e-5 {
				t.Errorf("caso %d: simproto[%d] Go %v Python %v", n, i, sp[i], c.Sp[i])
			}
		}
		r := cabezaConj(p, e, c.S, c.Sims, c.L0)
		var suma float64
		for i, o := range p.Opciones {
			d := math.Abs(r.Probs[o.ID] - c.Probs[i])
			peor = math.Max(peor, d)
			suma += r.Probs[o.ID]
			if d > fx.Tolerancia {
				t.Errorf("caso %d: p(%s) Go %v Python %v (Δ=%.2g)", n, o.ID, r.Probs[o.ID], c.Probs[i], d)
			}
		}
		if math.Abs(suma-1) > 1e-9 {
			t.Errorf("caso %d: las probabilidades suman %v", n, suma)
		}
	}
	t.Logf("peor |Δp| = %.3g en %d casos", peor, len(fx.Casos))
}

type simFalsa struct {
	S    [][]float32
	sims []float64
	n    int
}

func (s *simFalsa) Similitudes(Pregunta) ([][]float32, []float64, bool, error) {
	s.n++
	return s.S, s.sims, true, nil
}

func conL0(probs map[string]float64) Previas { return Previas{"L0": {Probs: probs, Conf: 0.5}} }

func TestL2cDecideYCaeAL2(t *testing.T) {
	exacto(t)
	fx, conj, p := leerFixtureConj(t)
	c := fx.Casos[0]
	sf := &simFalsa{S: c.S, sims: c.Sims}
	// Base L2 con las mismas similitudes: ESQUEMAS con una torre por opción y ranuras que dan sims fijas no hace falta,
	// L2 base solo se usa en los caminos de caída, que aquí no tienen torres (sin opinión).
	esq, _ := chispa3.DecodificarEsquemas(mustEsq(t))
	base := NuevoL2Con(sesionFalsa{c.S}, esq, chispa3.Calib{}, tokFalso{})
	l := NuevoL2cCon(base, sf, conj)
	ctx := context.Background()

	if l.Nombre() != "L2" {
		t.Fatalf("nombre %q: la config llama a la capa L2", l.Nombre())
	}
	r, err := l.DecidirCon(ctx, p, conL0(c.L0))
	if err != nil || sf.n != 1 {
		t.Fatalf("%v, llamadas a similitudes %d", err, sf.n)
	}
	want, wi := 0.0, 0
	for i, v := range c.Probs {
		if v > want {
			want, wi = v, i
		}
	}
	if r.Answer != fx.Opciones[wi] || math.Abs(r.Conf-want) > 1e-4 {
		t.Fatalf("respuesta %+v, esperaba %s con %v", r, fx.Opciones[wi], want)
	}

	// Sin probabilidades de L0, con otro esquema o sin CONJ: cae a L2 (aquí sin torres → sin opinión), sin usar la cabeza.
	for nombre, caso := range map[string]struct {
		p  Pregunta
		pr Previas
	}{
		"sin L0":          {p, nil},
		"L0 sin probs":    {p, Previas{"L0": {}}},
		"otro esquema":    {Pregunta{Texto: "otra", Kind: KindChoice, Opciones: p.Opciones}, conL0(c.L0)},
		"otro conjunto":   {Pregunta{Texto: p.Texto, Kind: KindChoice, Opciones: p.Opciones[:3]}, conL0(c.L0)},
		"noul no aplica":  {Pregunta{Texto: p.Texto, Kind: KindNoul, Opciones: p.Opciones}, conL0(c.L0)},
		"score no aplica": {Pregunta{Texto: p.Texto, Kind: KindScore, Opciones: p.Opciones}, conL0(c.L0)},
	} {
		sf.n = 0
		r, err := l.DecidirCon(ctx, caso.p, caso.pr)
		if err != nil || r.Conf != 0 || sf.n != 0 {
			t.Errorf("%s: %+v %v, similitudes %d", nombre, r, err, sf.n)
		}
	}
}

func mustEsq(t *testing.T) []byte {
	t.Helper()
	b, err := chispa3.CodificarEsquemas(2, []chispa3.EntradaEsquema{ent("zzz", []string{"a"}, 1, 1, 0)})
	if err != nil {
		t.Fatal(err)
	}
	return b
}

// La cascada pasa a L2c lo que dijo L0, y la ordena τ como siempre.
func TestCascadaPasaPreviasAL2c(t *testing.T) {
	exacto(t)
	fx, conj, p := leerFixtureConj(t)
	c := fx.Casos[1]
	esq, _ := chispa3.DecodificarEsquemas(mustEsq(t))
	l2c := NuevoL2cCon(NuevoL2Con(sesionFalsa{c.S}, esq, chispa3.Calib{}, tokFalso{}), &simFalsa{S: c.S, sims: c.Sims}, conj)
	l0 := decisorFijo{"L0", Respuesta{Answer: "x", Probs: c.L0, Conf: 0.1}}
	casc, err := NuevaCascada([]Capa{{Nombre: "L0", Tau: 0.9}, {Nombre: "L2", Tau: 0.5}}, []Decisor{l0, l2c}, NuevasMetricas())
	if err != nil {
		t.Fatal(err)
	}
	res := casc.Decidir(context.Background(), p)
	if res.Layer != "L2" || res.Escalate || len(res.Probs) != len(fx.Opciones) {
		t.Fatalf("%+v", res)
	}
	var want float64
	for _, v := range c.Probs {
		want = math.Max(want, v)
	}
	if got := res.Probs[res.Answer]; math.Abs(got-want) > 1e-4 {
		t.Fatalf("p(top) %v, esperaba %v", got, want)
	}
}

type decisorFijo struct {
	n string
	r Respuesta
}

func (d decisorFijo) Nombre() string                                       { return d.n }
func (d decisorFijo) Decidir(context.Context, Pregunta) (Respuesta, error) { return d.r, nil }

func BenchmarkL2cCabeza(b *testing.B) {
	// Una tarea de 150 clases con 16 ranuras de 256: el coste de la cabeza sin el ONNX.
	const C, K, D = 150, 16, 256
	e := chispa3.EntradaConj{Cabeza: chispa3.CabezaLR, K: K, D: D, T: 0.1, Beta: 1, Esc: [3]float32{1, 1, 1},
		W: []float32{1, 1, 1, 0.1, 0.1, 0.1}}
	p := Pregunta{Kind: KindChoice}
	l0, sims := map[string]float64{}, make([]float64, C)
	for i := 0; i < C; i++ {
		id := string(rune('A'+i/26)) + string(rune('a'+i%26))
		e.Clases = append(e.Clases, id)
		p.Opciones = append(p.Opciones, Opcion{ID: id})
		l0[id], sims[i] = 1.0/C, float64(i%7)/7
	}
	e.Escala, e.Proto = make([]float32, C*K), make([]byte, C*K*D)
	for i := range e.Escala {
		e.Escala[i] = 0.01
	}
	for i := range e.Proto {
		e.Proto[i] = byte(i * 31)
	}
	S := make([][]float32, K)
	for k := range S {
		S[k] = make([]float32, D)
		for j := range S[k] {
			S[k][j] = float32(j%5) / 5
		}
	}
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		cabezaConj(p, &e, S, sims, l0)
	}
}

func ficheroCon(t *testing.T, conj []byte) *chispa3.Fichero {
	t.Helper()
	secs := []chispa3.Seccion{{Tipo: chispa3.L2, Datos: []byte("onnx")}, {Tipo: chispa3.ESQUEMAS, Datos: mustEsq(t)}}
	if conj != nil {
		secs = append(secs, chispa3.Seccion{Tipo: chispa3.CONJ, Datos: conj})
	}
	var buf bytes.Buffer
	if err := chispa3.Escribir(&buf, secs); err != nil {
		t.Fatal(err)
	}
	f, err := chispa3.Desde(buf.Bytes(), chispa3.Limites{})
	if err != nil {
		t.Fatal(err)
	}
	return f
}

// Sin ORT el montaje deja L2 como stub y lo avisa, con o sin CONJ; un CONJ dañado es un error de carga.
func TestArmarDesdeConConj(t *testing.T) {
	fx, _, _ := leerFixtureConj(t)
	raw, _ := base64.StdEncoding.DecodeString(fx.ConjB64)
	for nombre, conj := range map[string][]byte{"sin CONJ": nil, "con CONJ": raw} {
		mt, err := ArmarDesde(ficheroCon(t, conj), NuevoL0(4), &Config{}, false, tokFalso{})
		if err != nil || mt.L2.Nombre() != "L2" {
			t.Fatalf("%s: %v", nombre, err)
		}
		if _, ok := mt.L2.(*L2c); ok {
			continue // compilado con ort: L2c montada
		}
		if len(mt.Avisos) != 1 {
			t.Errorf("%s: avisos %v", nombre, mt.Avisos)
		}
	}
	if _, err := ArmarDesde(ficheroCon(t, raw[:len(raw)-1]), NuevoL0(4), &Config{}, false, tokFalso{}); err == nil {
		t.Fatal("un CONJ truncado debe ser un error de carga")
	}
}

// dot3 y dot3x4 son exactos frente al producto entero ingenuo, también en los extremos (protos −128, S ±127).
func TestDot3Exacto(t *testing.T) {
	rnd := rand.New(rand.NewPCG(1, 2))
	for _, d := range []int{1, 2, 3, 4, 7, 256, 384, 1000} {
		w := (d + 2) / 3
		for _, modo := range []string{"azar", "max", "min"} {
			p, q := make([]int8, 4*d), make([][]int8, 4)
			for i := range p[:d] {
				switch modo {
				case "azar":
					p[i] = int8(rnd.IntN(256) - 128)
				case "max":
					p[i] = -128
				default:
					p[i] = 127
				}
			}
			var qp, qq [4][]int64
			qp[0] = make([]int64, w)
			for i := range qp[0] {
				var v [3]int8
				for k := 0; k < 3 && 3*i+k < d; k++ {
					v[k] = p[3*i+k]
				}
				qp[0][i] = empaquetar3(v[0], v[1], v[2])
			}
			var want [4]int64
			for s := range q {
				q[s] = make([]int8, d)
				for i := range q[s] {
					switch modo {
					case "azar":
						q[s][i] = int8(rnd.IntN(255) - 127)
					case "max":
						q[s][i] = -127
					default:
						q[s][i] = -127
					}
					want[s] += int64(p[i]) * int64(q[s][i])
				}
				qq[s] = make([]int64, w)
				for i := range qq[s] {
					g := func(k int) int8 {
						if k < d {
							return q[s][k]
						}
						return 0
					}
					qq[s][i] = empaquetar3(g(3*i+2), g(3*i+1), g(3*i))
				}
				if got := dot3(qp[0], qq[s]); got != want[s] {
					t.Fatalf("d=%d %s: dot3 %d, esperaba %d", d, modo, got, want[s])
				}
			}
			if got := dot3x4(qp[0], qq[0], qq[1], qq[2], qq[3]); got != want {
				t.Fatalf("d=%d %s: dot3x4 %v, esperaba %v", d, modo, got, want)
			}
		}
	}
}

// simproto cuantizado queda a ≤ 1e-2 (relativo a la escala de los valores) del cálculo en float, con y sin clases ausentes.
func TestSimprotoCercaDeLaReferencia(t *testing.T) {
	rnd := rand.New(rand.NewPCG(3, 4))
	for _, ns := range []int{1, 3, 4, 5, 16} {
		const C, K, D = 20, 8, 100
		e := chispa3.EntradaConj{K: K, D: D}
		var ops []Opcion
		for i := 0; i < C; i++ {
			id := string(rune('a' + i))
			e.Clases = append(e.Clases, id)
			ops = append(ops, Opcion{ID: id})
		}
		ops = append(ops, Opcion{ID: "zz"})
		e.Escala, e.Proto = make([]float32, C*K), make([]byte, C*K*D)
		for i := range e.Escala {
			e.Escala[i] = 0.02 + rnd.Float32()*0.01
		}
		for i := range e.Proto {
			e.Proto[i] = byte(rnd.IntN(256))
		}
		S := make([][]float32, ns)
		for k := range S {
			S[k] = make([]float32, D)
			for j := range S[k] {
				S[k][j] = rnd.Float32()*2 - 1
			}
		}
		S[0][0] = 0 // incluye una ranura distinta de cero en todo lo demás
		got, want := simproto(&e, S, ops), simprotoRef(&e, S, ops)
		var maxv float64
		for _, v := range want {
			maxv = math.Max(maxv, math.Abs(v))
		}
		for i := range got {
			if math.Abs(got[i]-want[i]) > 1e-2*maxv {
				t.Fatalf("ns=%d opción %d: %v frente a %v", ns, i, got[i], want[i])
			}
		}
		if got[C] != 0 {
			t.Fatal("clase ausente debe valer 0")
		}
	}
}

// BenchmarkSimproto150 es el coste de simproto sola con 150 clases, K=16 prototipos, 16 ranuras de 256.
func BenchmarkSimproto150(b *testing.B) {
	const C, K, D = 150, 16, 256
	e := chispa3.EntradaConj{K: K, D: D}
	var ops []Opcion
	for i := 0; i < C; i++ {
		id := string(rune('A'+i/26)) + string(rune('a'+i%26))
		e.Clases = append(e.Clases, id)
		ops = append(ops, Opcion{ID: id})
	}
	e.Escala, e.Proto = make([]float32, C*K), make([]byte, C*K*D)
	for i := range e.Escala {
		e.Escala[i] = 0.01
	}
	for i := range e.Proto {
		e.Proto[i] = byte(i * 31)
	}
	S := make([][]float32, 16)
	for k := range S {
		S[k] = make([]float32, D)
		for j := range S[k] {
			S[k][j] = float32(j%5) / 5
		}
	}
	b.Run("entero", func(b *testing.B) {
		for i := 0; i < b.N; i++ {
			simproto(&e, S, ops)
		}
	})
	b.Run("float", func(b *testing.B) {
		for i := 0; i < b.N; i++ {
			simprotoRef(&e, S, ops)
		}
	})
}
