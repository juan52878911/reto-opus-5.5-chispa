package decide

import (
	"context"
	"testing"

	"chispa/format/chispa3"
)

type decisorNuevo struct {
	conf  float64
	nuevo bool
}

func (decisorNuevo) Nombre() string { return "L2" }
func (d decisorNuevo) Decidir(context.Context, Pregunta) (Respuesta, error) {
	return Respuesta{Answer: "a", Probs: map[string]float64{"a": d.conf}, Conf: d.conf, EsquemaNuevo: d.nuevo}, nil
}

func capa2(t *testing.T, d Decisor, tauNuevo *float64) Resultado {
	t.Helper()
	c, err := NuevaCascadaConTauNuevo([]Capa{{"L2", 0.7}}, []Decisor{d}, NuevasMetricas(), tauNuevo)
	if err != nil {
		t.Fatal(err)
	}
	return c.Decidir(context.Background(), Pregunta{ID: "q", Kind: KindChoice})
}

func TestCascadaTauEsquemaNuevo(t *testing.T) {
	bajo := 0.5
	casos := []struct {
		nombre   string
		d        decisorNuevo
		tauNuevo *float64
		escala   bool
	}{
		{"conocido usa tau_escalate", decisorNuevo{0.6, false}, &bajo, true},
		{"conocido sobre tau_escalate acepta", decisorNuevo{0.8, false}, &bajo, false},
		{"nuevo usa el τ nuevo", decisorNuevo{0.6, true}, &bajo, false},
		{"nuevo sin τ nuevo: como hoy", decisorNuevo{0.6, true}, nil, true},
		{"conocido sin τ nuevo: como hoy", decisorNuevo{0.6, false}, nil, true},
	}
	for _, c := range casos {
		if r := capa2(t, c.d, c.tauNuevo); r.Escalate != c.escala {
			t.Errorf("%s: escalate=%v, quiero %v", c.nombre, r.Escalate, c.escala)
		}
	}
}

func TestL2MarcaEsquemaNuevo(t *testing.T) {
	enc := &codificadorPorTexto{clave: "x"}
	cfg := Config{CacheEsquemas: 64, CacheRespuestas: 0}
	mt, err := ArmarDesde(conTorreSeccion(t), NuevoL0(8), &cfg, false, tokFalso{}, ConSesionS(sesionFalsa{[][]float32{{3, 0}}}), ConCodificadorTorre(enc))
	if err != nil {
		t.Fatal(err)
	}
	ops := []Opcion{{ID: "a"}}
	conocida, err := mt.L2.Decidir(context.Background(), Pregunta{Texto: "solo en ESQUEMAS", Kind: KindChoice, Estado: "e", Opciones: ops})
	if err != nil || conocida.Conf == 0 || conocida.EsquemaNuevo {
		t.Fatalf("conocida: %+v %v", conocida, err)
	}
	nueva, err := mt.L2.Decidir(context.Background(), Pregunta{Texto: "otra", Kind: KindChoice, Estado: "e", Opciones: ops})
	if err != nil || nueva.Conf == 0 || !nueva.EsquemaNuevo {
		t.Fatalf("nueva: %+v %v", nueva, err)
	}
}

func TestPrioridadTauL2EsquemaNuevo(t *testing.T) {
	calibTau := 0.3
	cfgTau := 0.9
	build := func(cfg Config, tauDeCalib bool, calib *float64) *float64 {
		esq, _ := chispa3.CodificarEsquemas(2, nil)
		f := v3Tiny(t, chispa3.Calib{TauEscalate: 0.5, TauL2EsquemaNuevo: calib, Tipos: map[string]chispa3.ParamsTipo{}}, chispa3.Seccion{Tipo: chispa3.L2, Datos: []byte("onnx-l2")}, chispa3.Seccion{Tipo: chispa3.ESQUEMAS, Datos: esq})
		cfg.Capas = ConfigPorDefecto().Capas
		if _, err := ArmarDesde(f, NuevoL0(8), &cfg, tauDeCalib, tokFalso{}, ConSesionS(sesionFalsa{[][]float32{{3, 0}}})); err != nil {
			t.Fatal(err)
		}
		return cfg.TauL2EsquemaNuevo
	}
	if v := build(Config{}, true, &calibTau); v == nil || *v != 0.3 {
		t.Errorf("solo .chispa: %v", v)
	}
	if v := build(Config{TauL2EsquemaNuevo: &cfgTau}, true, &calibTau); v == nil || *v != 0.9 {
		t.Errorf("Config manda sobre .chispa: %v", v)
	}
	if v := build(Config{}, true, nil); v != nil {
		t.Errorf("sin ninguno: %v", v)
	}
	if v := build(Config{}, false, &calibTau); v != nil {
		t.Errorf("con -config explícita no se toma de CALIB: %v", v)
	}
	mal := 1.5
	if err := (Config{Capas: ConfigPorDefecto().Capas, CacheEsquemas: 1, CacheRespuestas: 1, TauL2EsquemaNuevo: &mal}).Validar(); err == nil {
		t.Error("τ fuera de [0,1] debe rechazarse")
	}
}
