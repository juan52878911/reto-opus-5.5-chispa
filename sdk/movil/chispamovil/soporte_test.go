package chispamovil

import (
	"context"
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"testing"

	"chispa/format/chispa3"
	"github.com/juan52878911/chispa/server/decide"
)

func soplDePrueba(t *testing.T, dim int, p pregunta, textos map[string]string, k map[string]uint32) *chispa3.Sopl1 {
	t.Helper()
	ids := idsDe(p)
	e := chispa3.EntradaSopl1{Hash: chispa3.ClaveConj(p.Texto, ids)}
	e.Ids = append([]string(nil), ids...)
	for i := range e.Ids { // estrictamente crecientes
		for j := i + 1; j < len(e.Ids); j++ {
			if e.Ids[j] < e.Ids[i] {
				e.Ids[i], e.Ids[j] = e.Ids[j], e.Ids[i]
			}
		}
	}
	for _, id := range e.Ids {
		v := make([]float32, dim)
		if tx, ok := textos[id]; ok {
			falso{}.Embed(tx, v)
		}
		esc, q := chispa3.CuantizarMedia(v)
		e.K, e.Escala, e.Media = append(e.K, k[id]), append(e.Escala, esc), append(e.Media, q...)
	}
	b, err := chispa3.CodificarSopl1(dim, []chispa3.EntradaSopl1{e})
	if err != nil {
		t.Fatal(err)
	}
	s, err := chispa3.DecodificarSopl1(b)
	if err != nil {
		t.Fatal(err)
	}
	return s
}

func soporteL1(t *testing.T, lambda float64, textos map[string]string, k map[string]uint32) *Chispa {
	t.Helper()
	p, err := leerPregunta(preguntaCompra)
	if err != nil {
		t.Fatal(err)
	}
	c := conFalso()
	c.sopl, c.lambdaL1 = soplDePrueba(t, 16, p, textos, k), lambdaDe(lambda)
	return c
}

func TestSoporteL1LambdaInfinitoNoCambiaNada(t *testing.T) {
	base := conFalso()
	textos, k := map[string]string{"compra": "necesito ayuda con algo"}, map[string]uint32{"compra": 5, "soporte": 2}
	for _, l := range []float64{math.Inf(1), -1, math.NaN()} {
		c := soporteL1(t, l, textos, k)
		if c.lambdaL1 != nil {
			t.Fatalf("λ=%v debería ser ∞ (nil)", l)
		}
		for _, msg := range []string{"quiero comprar un producto", "necesito ayuda con algo", "hola"} {
			if got, want := c.Decidir(msg, preguntaCompra), base.Decidir(msg, preguntaCompra); got != want {
				t.Fatalf("λ=%v %q: %s ≠ %s", l, msg, got, want)
			}
		}
	}
}

func TestSoporteL1MueveHaciaLosEjemplos(t *testing.T) {
	msg := "necesito ayuda con algo"
	r0 := leer(t, conFalso().Decidir(msg, preguntaCompra))
	if r0.Answer != "soporte" {
		t.Fatalf("la descripción lleva a soporte: %+v", r0)
	}
	textos, k := map[string]string{"compra": msg}, map[string]uint32{"compra": 4}
	prev := r0.Probs["compra"]
	for _, l := range []float64{16, 4, 1, 0.01} {
		r := leer(t, soporteL1(t, l, textos, k).Decidir(msg, preguntaCompra))
		if r.Probs["compra"] <= prev {
			t.Fatalf("λ=%v: %v no sube desde %v", l, r.Probs["compra"], prev)
		}
		prev = r.Probs["compra"]
		if l == 0.01 && r.Answer != "compra" {
			t.Fatalf("w≈1: %+v", r)
		}
	}
	// una pregunta que no está en la sección no cambia
	otra := `{"question":"¿Otra?","kind":"choice","options":[{"id":"compra","description":"quiere comprar un producto"},{"id":"soporte","description":"pide ayuda con algo"}]}`
	if got, want := soporteL1(t, 0.01, textos, k).Decidir(msg, otra), conFalso().Decidir(msg, otra); got != want {
		t.Fatalf("pregunta ausente: %s ≠ %s", got, want)
	}
}

func TestAbrirConSoporteLeeSOPL1(t *testing.T) {
	p, _ := leerPregunta(preguntaCompra)
	e := chispa3.EntradaSopl1{Hash: chispa3.ClaveConj(p.Texto, []string{"compra", "soporte"}), Ids: []string{"compra", "soporte"},
		K: []uint32{2, 0}, Escala: []float32{0, 0}, Media: make([]int8, 8)}
	b, err := chispa3.CodificarSopl1(4, []chispa3.EntradaSopl1{e})
	if err != nil {
		t.Fatal(err)
	}
	c := ficheroV3(t, chispa3.Seccion{Tipo: chispa3.SOPL1, Datos: b})
	if c.sopl == nil || c.sopl.Len() != 1 || c.lambdaL1 != nil || c.lambdaL2 != nil {
		t.Fatalf("Abrir: sopl=%v λ=%v/%v", c.sopl, c.lambdaL1, c.lambdaL2)
	}
	ruta := filepath.Join(t.TempDir(), "s.chispa")
	if err := os.WriteFile(ruta, mustEscribir(t, b), 0o600); err != nil {
		t.Fatal(err)
	}
	c2, err := AbrirConSoporte(ruta, 3, math.Inf(1))
	if err != nil || c2.lambdaL1 == nil || *c2.lambdaL1 != 3 || c2.lambdaL2 != nil {
		t.Fatalf("%v %v", c2, err)
	}
	c2.Cerrar()
	if _, err := AbrirConSoporte(ruta+"x", 1, 1); err == nil {
		t.Fatal("un fichero que no existe debe fallar")
	}
}

func mustEscribir(t *testing.T, sopl []byte) []byte {
	t.Helper()
	var buf = new(bytesBuf)
	if err := chispa3.Escribir(buf, append(metaYCalib(t), chispa3.Seccion{Tipo: chispa3.SOPL1, Datos: sopl})); err != nil {
		t.Fatal(err)
	}
	return buf.b
}

type bytesBuf struct{ b []byte }

func (w *bytesBuf) Write(p []byte) (int, error) { w.b = append(w.b, p...); return len(p), nil }

// La mezcla de L2c del núcleo móvil coincide con la del servidor (decide.L2c.ConSoporte) con |Δp| ≤ 1e-6, y con λ = ∞ da lo de siempre.
func TestCabezaConjuntaConSoporteParidadConServidor(t *testing.T) {
	fx, raw := leerFixtureConj(t)
	conj, err := chispa3.DecodificarConj(raw)
	if err != nil {
		t.Fatal(err)
	}
	pjs, p := preguntaDe(fx.Pregunta, fx.Opciones)
	pm, _ := leerPregunta(pjs)
	ks := map[string]uint32{}
	for i, id := range fx.Opciones {
		ks[id] = uint32(1 + 2*i)
	}
	sopl := soplDePrueba(t, 4, pm, nil, ks)
	for n, caso := range fx.Casos {
		esq, S := torresParaSims(t, fx, caso)
		c := ficheroV3(t,
			chispa3.Seccion{Tipo: chispa3.L2, Datos: []byte("onnx")},
			chispa3.Seccion{Tipo: chispa3.ESQUEMAS, Datos: esq},
			chispa3.Seccion{Tipo: chispa3.CONJ, Datos: raw})
		var in map[string]any
		json.Unmarshal([]byte(pjs), &in)
		in["l0"], in["ranuras"], in["k"] = caso.L0, planas(S), len(S)
		js, _ := json.Marshal(in)
		sinSoporte := leer(t, c.CabezaConjunta(string(js)))
		c.sopl = sopl
		c.lambdaL2 = nil
		if got := leer(t, c.CabezaConjunta(string(js))); got.Conf != sinSoporte.Conf || got.Answer != sinSoporte.Answer {
			t.Fatalf("caso %d: λ=∞ cambió la respuesta: %+v ≠ %+v", n, got, sinSoporte)
		}
		lam := 0.5
		c.lambdaL2 = &lam
		got := leer(t, c.CabezaConjunta(string(js)))

		e, _ := chispa3.DecodificarEsquemas(esq)
		base := decide.NuevoL2Con(nil, e, chispa3.Calib{}, nil)
		sims := make([]float64, len(fx.Opciones))
		for i, id := range fx.Opciones {
			v, esc, _ := e.Buscar(chispa3.HashEsquema(fx.Pregunta, []string{id}))
			sims[i] = chispa3.MaxSim(S, v, esc)
		}
		want, err := decide.NuevoL2cCon(base, simsFijas{S, sims}, conj).ConSoporte(sopl, &lam).
			DecidirCon(context.Background(), p, decide.Previas{"L0": {Probs: caso.L0, Conf: 0.5}})
		if err != nil {
			t.Fatal(err)
		}
		var peor, mueve float64
		for _, id := range fx.Opciones {
			peor = math.Max(peor, math.Abs(got.Probs[id]-want.Probs[id]))
			mueve = math.Max(mueve, math.Abs(got.Probs[id]-sinSoporte.Probs[id]))
		}
		if peor > tolParidad || got.Answer != want.Answer {
			t.Fatalf("caso %d: |Δp| frente al servidor %g (%s frente a %s)", n, peor, got.Answer, want.Answer)
		}
		if mueve == 0 {
			t.Errorf("caso %d: con λ=0,5 la mezcla debería mover las probabilidades", n)
		}
	}
}
