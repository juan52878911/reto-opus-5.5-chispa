package decide

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"math"
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
	chispa3.SimprotoActual = chispa3.SimprotoRef
	t.Cleanup(func() { chispa3.SimprotoActual = chispa3.Simproto })
}

// La implementación entera (S cuantizada a int8) queda cerca de Python: Δp < 1e-2 en los casos del fixture.
func TestL2cParidadEnteraConPython(t *testing.T) {
	fx, conj, p := leerFixtureConj(t)
	e, _ := conj.Buscar(ClaveConj(p))
	var peor float64
	for n, c := range fx.Casos {
		r := cabezaConj(p, e, c.S, c.Sims, nil, c.L0)
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
		ids := make([]string, len(p.Opciones))
		for i, o := range p.Opciones {
			ids[i] = o.ID
		}
		sp := chispa3.SimprotoActual(e, c.S, ids)
		for i := range sp {
			if d := math.Abs(sp[i] - c.Sp[i]); d > 1e-5 {
				t.Errorf("caso %d: simproto[%d] Go %v Python %v", n, i, sp[i], c.Sp[i])
			}
		}
		r := cabezaConj(p, e, c.S, c.Sims, nil, c.L0)
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

func (s *simFalsa) Similitudes(context.Context, Pregunta) ([][]float32, []float64, bool, error) {
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
	e, p, l0, sims, S := cabezaBench()
	b.Run("armada", func(b *testing.B) {
		b.ReportAllocs()
		for i := 0; i < b.N; i++ {
			cabezaConj(p, &e, S, sims, nil, l0)
		}
	})
	b.Run("decodificada", func(b *testing.B) {
		raw, err := chispa3.CodificarConj([]chispa3.EntradaConj{e})
		if err != nil {
			b.Fatal(err)
		}
		c, err := chispa3.DecodificarConj(raw)
		if err != nil {
			b.Fatal(err)
		}
		d, ok := c.Buscar(e.Hash)
		if !ok {
			b.Fatal("entrada no encontrada")
		}
		b.ReportAllocs()
		b.ResetTimer()
		for i := 0; i < b.N; i++ {
			cabezaConj(p, d, S, sims, nil, l0)
		}
	})
}

// cabezaBench arma una tarea de 150 clases con 16 ranuras de 256: el coste de la cabeza sin el ONNX.
func cabezaBench() (e chispa3.EntradaConj, p Pregunta, l0 map[string]float64, sims []float64, S [][]float32) {
	const C, K, D = 150, 16, 256
	e = chispa3.EntradaConj{Cabeza: chispa3.CabezaLR, K: K, D: D, T: 0.1, Beta: 1, Esc: [3]float32{1, 1, 1},
		W: []float32{1, 1, 1, 0.1, 0.1, 0.1}}
	p = Pregunta{Kind: KindChoice}
	l0, sims = map[string]float64{}, make([]float64, C)
	for i := 0; i < C; i++ {
		id := string(rune('A'+i/26)) + string(rune('a'+i%26))
		e.Clases = append(e.Clases, id)
		p.Opciones = append(p.Opciones, Opcion{ID: id})
		l0[id], sims[i] = 1.0/C, float64(i%7)/7
	}
	e.Hash = chispa3.HashEsquema("bench", e.Clases)
	e.Escala, e.Proto = make([]float32, C*K), make([]byte, C*K*D)
	for i := range e.Escala {
		e.Escala[i] = 0.01
	}
	for i := range e.Proto {
		e.Proto[i] = byte(i * 31)
	}
	S = make([][]float32, K)
	for k := range S {
		S[k] = make([]float32, D)
		for j := range S[k] {
			S[k][j] = float32(j%5) / 5
		}
	}
	return
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

func TestAplicarTauL2c(t *testing.T) {
	tau := 0.42
	nuevo := func() *Config { return &Config{Capas: []Capa{{Nombre: "L0", Tau: 0.8}, {Nombre: "L2", Tau: 0.7}}} }
	casos := []struct {
		nombre            string
		calib             chispa3.Calib
		esL2c, tauDeCalib bool
		quiere            float64
	}{
		{"con τ de L2c", chispa3.Calib{TauL2c: &tau}, true, true, 0.42},
		{"sin τ de L2c: igual que antes", chispa3.Calib{}, true, true, 0.7},
		{"L2 sin cabeza conjunta", chispa3.Calib{TauL2c: &tau}, false, true, 0.7},
		{"config explícita manda", chispa3.Calib{TauL2c: &tau}, true, false, 0.7},
	}
	for _, c := range casos {
		cfg := nuevo()
		aplicarTauL2c(cfg, c.calib, c.esL2c, c.tauDeCalib)
		if cfg.Capas[1].Tau != c.quiere || cfg.Capas[0].Tau != 0.8 {
			t.Errorf("%s: τ L0=%v L2=%v, quiero L2=%v", c.nombre, cfg.Capas[0].Tau, cfg.Capas[1].Tau, c.quiere)
		}
	}
}
