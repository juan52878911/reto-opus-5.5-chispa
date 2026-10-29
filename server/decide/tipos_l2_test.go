package decide

import (
	"context"
	"reflect"
	"testing"

	"chispa/format/chispa3"
)

func armarConCalib(t *testing.T, calib chispa3.Calib) (Montaje, Config) {
	t.Helper()
	esq, err := chispa3.CodificarEsquemas(2, []chispa3.EntradaEsquema{ent("q", []string{"a"}, 0.5, 10, 0), ent("q", []string{"b"}, 0.5, 0, 10)})
	if err != nil {
		t.Fatal(err)
	}
	f := v3Tiny(t, calib, chispa3.Seccion{Tipo: chispa3.L2, Datos: []byte("onnx-l2")}, chispa3.Seccion{Tipo: chispa3.ESQUEMAS, Datos: esq})
	cfg := Config{CacheEsquemas: 64, Capas: ConfigPorDefecto().Capas}
	mt, err := ArmarDesde(f, NuevoL0(8), &cfg, true, tokFalso{}, ConSesionS(sesionFalsa{[][]float32{{0.3, 0.1}, {0.1, 0.4}}}))
	if err != nil {
		t.Fatal(err)
	}
	return mt, cfg
}

func tausDe(cfg Config) map[string]float64 {
	m := map[string]float64{}
	for _, c := range cfg.Capas {
		m[c.Nombre] = c.Tau
	}
	return m
}

// tipos_l2 y tau_escalate_l2 son lo que lee L2; L1 conserva tipos y tau_escalate. Un fichero sin ellos decide igual que antes:
// aquí, igual que uno cuyos tipos y tau_escalate son los de L2.
func TestTiposL2LosLeeL2(t *testing.T) {
	tauL2 := 0.4
	l2 := map[string]chispa3.ParamsTipo{"choice": {T: 0.5}}
	nuevo := chispa3.Calib{TauEscalate: 0.9, TauEscalateL2: &tauL2, Tipos: map[string]chispa3.ParamsTipo{"choice": {T: 9}}, TiposL2: l2}
	viejo := chispa3.Calib{TauEscalate: 0.4, Tipos: l2}
	mn, cn := armarConCalib(t, nuevo)
	mv, cv := armarConCalib(t, viejo)
	if g := tausDe(cn); g["L1"] != 0.9 || g["L2"] != 0.4 {
		t.Fatalf("τ con tipos_l2: %v", g)
	}
	if g := tausDe(cv); g["L2"] != 0.4 {
		t.Fatalf("τ de un fichero viejo: %v", g)
	}
	p := Pregunta{Texto: "q", Kind: KindChoice, Opciones: []Opcion{{ID: "a"}, {ID: "b"}}}
	rn, err := mn.L2.Decidir(context.Background(), p)
	if err != nil {
		t.Fatal(err)
	}
	rv, err := mv.L2.Decidir(context.Background(), p)
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(rn, rv) {
		t.Fatalf("con tipos_l2 %+v ≠ fichero viejo %+v", rn, rv)
	}
	// y L1 sigue con su T: la misma pregunta a un L2 que leyera tipos daría otra confianza
	otro, _ := armarConCalib(t, chispa3.Calib{TauEscalate: 0.9, Tipos: nuevo.Tipos})
	ro, _ := otro.L2.Decidir(context.Background(), p)
	if ro.Conf == rn.Conf {
		t.Fatalf("L2 debía leer tipos_l2 y no tipos: %v", ro.Conf)
	}
}

// tau_escalate_l2 solo mueve el τ de L2.
func TestTauEscalateL2SinAfectarAL1(t *testing.T) {
	tau := 0.2
	_, cfg := armarConCalib(t, chispa3.Calib{TauEscalate: 0.8, TauEscalateL2: &tau, Tipos: map[string]chispa3.ParamsTipo{}})
	if g := tausDe(cfg); g["L1"] != 0.8 || g["L2"] != 0.2 {
		t.Fatalf("%v", g)
	}
}
