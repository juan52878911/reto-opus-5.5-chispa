package chispamovil

import (
	"context"
	"math"
	"testing"

	"chispa/format/chispa3"

	"github.com/juan52878911/chispa/server/decide"
)

// calibConL2 es la CALIB de calibTorre repartida en dos espacios: tipos (L1, con valores que L2 no debe leer) y tipos_l2 (los de calibTorre).
func calibConL2() chispa3.Calib {
	tau := calibTorre().TauEscalate
	return chispa3.Calib{
		TauEscalate:   0.9,
		TauEscalateL2: &tau,
		Tipos: map[string]chispa3.ParamsTipo{
			"choice": {T: 9}, "noul": {T: 3, A: -7, B: 4, Theta: 0.1}, "score3": {T: 1, A: 5, B: 5, Theta: 0.5}, "score3#1": {T: 1, A: 3, B: 3, Theta: 0.5},
		},
		TiposL2: calibTorre().Tipos,
	}
}

// Con tipos_l2, L2 móvil decide como el servidor con esos tipos (paridad) y como un fichero viejo cuyos tipos son los mismos (igualdad
// exacta); un fichero sin tipos_l2 decide igual que antes.
func TestTiposL2ParidadYCompatibilidad(t *testing.T) {
	if got := calibConL2().ParaL2(); got.TauEscalate != 0.4 || got.Tipos["choice"].T != 0.5 {
		t.Fatalf("ParaL2: %+v", got)
	}
	for _, q := range preguntasTorre {
		p, err := leerPregunta(q)
		if err != nil {
			t.Fatal(err)
		}
		esq, _ := chispa3.DecodificarEsquemas(mustEsq())
		g := &grabador{}
		srv := decide.NuevoL2Con(sesFalsa{ranurasTorre}, esq, calibConL2().ParaL2(), tokFalso{}).ConTorres(g, 64)
		want, err := srv.Decidir(context.Background(), aDecideL2(p))
		if err != nil {
			t.Fatalf("%s: servidor: %v", q, err)
		}
		nuevo := movilConTorres(t, calibConL2(), q, g.textos)
		viejo := movilConTorres(t, calibTorre(), q, g.textos)
		if nuevo != viejo {
			t.Fatalf("%s: con tipos_l2 %+v ≠ fichero viejo %+v", q, nuevo, viejo)
		}
		if nuevo.Opina != (want.Conf > 0) || (nuevo.Opina && (nuevo.Answer != want.Answer || math.Abs(nuevo.Conf-want.Conf) > 1e-9)) {
			t.Fatalf("%s: móvil %+v ≠ servidor %+v", q, nuevo, want)
		}
	}
}

// movilConTorres instala las torres de textos y puntúa; devuelve la respuesta sin mapas (comparable con ==).
func movilConTorres(t *testing.T, calib chispa3.Calib, q string, textos []string) (r struct {
	Ok, Opina bool
	Answer    string
	Conf      float64
}) {
	t.Helper()
	c := movilL2(t)
	c.calib = calib
	if !c.InstalarTorresL2(q, torresBytes(textos), len(textos)) {
		t.Fatalf("%s: instalar", q)
	}
	x := leer(t, c.PuntuarL2(q, ranuras(ranurasTorre...), len(ranurasTorre)))
	r.Ok, r.Opina, r.Answer, r.Conf = x.Ok, x.Opina, x.Answer, x.Conf
	return r
}

func TestTauEscalateL2YL1ConservaSusTipos(t *testing.T) {
	c := &Chispa{calib: calibConL2()}
	if c.TauEscalate() != 0.9 || c.TauEscalateL2() != 0.4 {
		t.Fatalf("τ L1 %v, τ L2 %v", c.TauEscalate(), c.TauEscalateL2())
	}
	if c.params("choice").T != 9 || c.paramsL2("choice").T != 0.5 {
		t.Fatalf("L1 %v, L2 %v", c.params("choice").T, c.paramsL2("choice").T)
	}
	v := &Chispa{calib: calibTorre()}
	if v.TauEscalate() != 0.4 || v.TauEscalateL2() != 0.4 || v.params("choice") != v.paramsL2("choice") {
		t.Fatal("un fichero sin tipos_l2: L1 y L2 leen lo mismo")
	}
}

// multi: L1 lee «multi@…» de tipos y L2 «multi_l2@…» de tipos_l2.
func TestMultiTiposL2(t *testing.T) {
	q := `{"question":"¿Qué pide?","kind":"multi","options":[{"id":"a"},{"id":"b"}]}`
	p, _ := leerPregunta(q)
	esq := claveCalibMulti(p)
	c := &Chispa{calib: chispa3.Calib{
		Tipos:   map[string]chispa3.ParamsTipo{"noul": {T: 1, A: 1, B: 0, Theta: 0.5}, "multi" + esq: {T: 1, A: 2, B: 0, Theta: 0.5}},
		TiposL2: map[string]chispa3.ParamsTipo{"noul": {T: 1, A: 7, B: 0, Theta: 0.5}, "multi_l2" + esq: {T: 1, A: 3, B: 1, Theta: 0.5}},
	}}
	if prm, ok := c.buscarParamsMulti("multi", esq, "a"); !ok || prm.A != 2 {
		t.Fatalf("L1: %+v %v", prm, ok)
	}
	if prm, ok := c.buscarParamsMulti("multi_l2", esq, "a"); !ok || prm.A != 3 {
		t.Fatalf("L2: %+v %v", prm, ok)
	}
	if prm, ok := c.buscarParamsMulti("multi_l2", "@otro", "a"); ok || prm.A != 7 {
		t.Fatalf("respaldo de L2 = noul de tipos_l2: %+v %v", prm, ok)
	}
}
