package decide

import (
	"strings"
	"testing"

	"chispa/format/chispa3"
)

func capasCalib(cal chispa3.Calib) (*L1, *L2) {
	l1 := &L1{calib: cal, cache: newLRU[map[string][]float32](0, 1<<20, costeEmbeddings)}
	l2 := NuevoL2Con(nil, nil, cal.ParaL2(), nil)
	return l1, l2
}

// H7: con τ de config distintos a los de CALIB, la métrica publica los de la config y marca el origen.
func TestCalibTauEfectivoConfigCalibDefault(t *testing.T) {
	l2c := 0.2
	nuevoCal := 0.9
	cal := chispa3.Calib{Tipos: map[string]chispa3.ParamsTipo{"choice": {T: 1}}, TauEscalate: 0.55, TauL2c: &l2c, TauL2EsquemaNuevo: &nuevoCal}
	l1, l2 := capasCalib(cal)
	cfgNuevo := 0.77
	m := NuevasMetricas()
	// config manda: L1 0.91 (≠ CALIB), L2 igual a CALIB de L2c, esquema nuevo de config
	c1, err := NuevaCascadaConTauNuevo([]Capa{{"L1", 0.91}, {"L2", 0.2}}, []Decisor{l1, l2}, m, &cfgNuevo)
	if err != nil {
		t.Fatal(err)
	}
	c1.PublicaCalib()
	out := metricasTexto(m)
	for _, q := range []string{
		`chispa_calib_tau{capa="L1",clave="tau_escalate",origen="config"} 0.91`,
		`chispa_calib_tau{capa="L2",clave="tau_escalate",origen="calib"} 0.2`,
		`chispa_calib_tau{capa="L2",clave="tau_l2_esquema_nuevo",origen="config"} 0.77`,
	} {
		if !strings.Contains(out, q) {
			t.Errorf("falta %s\n%s", q, out)
		}
	}
	if strings.Contains(out, `clave="tau_l2c"`) || strings.Contains(out, `origen="fichero"} 0.55`) {
		t.Errorf("publica τ que no están en servicio:\n%s", out)
	}
	// valores de la capa por defecto, sin CALIB: origen default, incluido el de esquema nuevo
	l1, l2 = capasCalib(chispa3.Calib{})
	m = NuevasMetricas()
	dn := TauL2EsquemaNuevoPorDefecto
	c2, err := NuevaCascadaConTauNuevo([]Capa{{"L1", 0.8}, {"L2", 0.7}}, []Decisor{l1, l2}, m, &dn)
	if err != nil {
		t.Fatal(err)
	}
	c2.PublicaCalib()
	out = metricasTexto(m)
	for _, q := range []string{
		`chispa_calib_tau{capa="L1",clave="tau_escalate",origen="default"} 0.8`,
		`chispa_calib_tau{capa="L2",clave="tau_l2_esquema_nuevo",origen="default"} 0.846`,
	} {
		if !strings.Contains(out, q) {
			t.Errorf("falta %s\n%s", q, out)
		}
	}
}

// H8: tras armar una cascada sin L2 (stub) las series de la L2 anterior desaparecen.
func TestCalibRecargaSinL2VaciaSeries(t *testing.T) {
	cal := chispa3.Calib{Tipos: map[string]chispa3.ParamsTipo{"choice": {T: 1}}, TauEscalate: 0.5}
	l1, l2 := capasCalib(cal)
	m := NuevasMetricas()
	c1, err := NuevaCascada([]Capa{{"L1", 0.8}, {"L2", 0.7}}, []Decisor{l1, l2}, m)
	if err != nil {
		t.Fatal(err)
	}
	c1.PublicaCalib()
	if !strings.Contains(metricasTexto(m), `capa="L2"`) {
		t.Fatal("L2 debería estar publicada")
	}
	l1b, _ := capasCalib(cal)
	c2, err := NuevaCascada([]Capa{{"L1", 0.8}}, []Decisor{l1b}, m)
	if err != nil {
		t.Fatal(err)
	}
	c2.PublicaCalib()
	out := metricasTexto(m)
	for _, l := range strings.Split(out, "\n") {
		if strings.HasPrefix(l, "chispa_calib") && strings.Contains(l, `capa="L2"`) && !strings.Contains(l, "defecto_total") {
			t.Errorf("serie vieja de L2: %s", l)
		}
	}
	if !strings.Contains(out, `capa="L1"`) {
		t.Error("L1 debe seguir publicada")
	}
}

// H9: sin_tipo de score mira la clave que usa cada capa.
func TestCalibSinTipoScorePorCapa(t *testing.T) {
	solo4 := chispa3.Calib{Tipos: map[string]chispa3.ParamsTipo{"score4": {T: 1}, "score4#1": {T: 1}}}
	if v := VistaCalibCapa("L1", solo4, OrigenFichero, true); !contiene(v.SinCalib, "score") {
		t.Errorf("L1 con solo score4 debe avisar score: %v", v.SinCalib)
	}
	if v := VistaCalibCapa("L2", solo4, OrigenFichero, true); contiene(v.SinCalib, "score") {
		t.Errorf("L2 con score4 no debe avisar score: %v", v.SinCalib)
	}
	solo := chispa3.Calib{Tipos: map[string]chispa3.ParamsTipo{"score": {T: 1}}}
	if v := VistaCalibCapa("L1", solo, OrigenFichero, true); contiene(v.SinCalib, "score") {
		t.Errorf("L1 con score no debe avisar: %v", v.SinCalib)
	}
	if v := VistaCalibCapa("L2", solo, OrigenFichero, true); !contiene(v.SinCalib, "score") {
		t.Errorf("L2 con solo score debe avisar: %v", v.SinCalib)
	}
}

func contiene(xs []string, x string) bool {
	for _, y := range xs {
		if y == x {
			return true
		}
	}
	return false
}
