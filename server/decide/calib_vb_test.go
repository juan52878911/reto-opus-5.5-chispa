package decide

import (
	"strings"
	"testing"

	"chispa/format/chispa3"
)

func tauL1Texto(m *Metricas) string {
	for _, l := range strings.Split(metricasTexto(m), "\n") {
		if strings.HasPrefix(l, `chispa_calib_tau{capa="L1",clave="tau_escalate"`) {
			return l
		}
	}
	return ""
}

func armadoCalibTau(t *testing.T, m *Metricas, tau float64, claves []ClaveAPI) *Armado {
	t.Helper()
	l1, l2 := capasCalib(chispa3.Calib{Tipos: map[string]chispa3.ParamsTipo{"choice": {T: 1}}, TauEscalate: 0.5})
	c, err := NuevaCascada([]Capa{{"L1", tau}, {"L2", 0.7}}, []Decisor{l1, l2}, m)
	if err != nil {
		t.Fatal(err)
	}
	return &Armado{Cascada: c, CacheRespuestas: 4, Limites: LimitesPorDefecto(), APIKeys: claves}
}

// R15-3: una recarga rechazada por api_keys no publica la CALIB ni los τ del modelo rechazado.
func TestVBRecargaRechazadaNoPublicaCalib(t *testing.T) {
	m := NuevasMetricas()
	claves := []ClaveAPI{{ID: "k", HashSHA256: strings.Repeat("a", 64), RPS: 1}}
	armados := []*Armado{armadoCalibTau(t, m, 0.5, claves)}
	s := NuevoServidorDe(armados[0], m)
	if !strings.Contains(tauL1Texto(m), "} 0.5") {
		t.Fatalf("arranque: %q", tauL1Texto(m))
	}
	s = s.ConRecarga(func() (*Armado, error) { return armadoCalibTau(t, m, 0.91, nil), nil }, "tok")
	if err := s.Recargar(); err == nil {
		t.Fatal("la recarga sin api_keys debía rechazarse")
	}
	if l := tauL1Texto(m); !strings.Contains(l, "} 0.5") || strings.Contains(l, "0.91") {
		t.Fatalf("/metrics publica el τ del modelo rechazado: %q", l)
	}
}

// R15-3: si NuevaCascada falla (nombre de capa), tampoco toca las series publicadas.
func TestVBNuevaCascadaFallidaNoTocaCalib(t *testing.T) {
	m := NuevasMetricas()
	armadoCalibTau(t, m, 0.5, nil).Cascada.PublicaCalib()
	l1, l2 := capasCalib(chispa3.Calib{Tipos: map[string]chispa3.ParamsTipo{"choice": {T: 1}}, TauEscalate: 0.33})
	if _, err := NuevaCascada([]Capa{{"L1", 0.91}, {"L3", 0.7}}, []Decisor{l1, l2}, m); err == nil {
		t.Fatal("el nombre de capa no casa: debía fallar")
	}
	if l := tauL1Texto(m); !strings.Contains(l, "} 0.5") {
		t.Fatalf("NuevaCascada fallida cambió /metrics: %q", l)
	}
	// y una recarga que prospera sí las publica
	armadoCalibTau(t, m, 0.91, nil).Cascada.PublicaCalib()
	if !strings.Contains(tauL1Texto(m), "} 0.91") {
		t.Fatalf("tras publicar: %q", tauL1Texto(m))
	}
}

// R15-7: con CONJ y tau_l2c, el servidor publica tau_escalate (respaldo) y tau_l2c por separado.
func TestVBTauL2cYRespaldoPorSeparado(t *testing.T) {
	l2c, nuevo := 0.2, 0.9
	cal := chispa3.Calib{Tipos: map[string]chispa3.ParamsTipo{"choice": {T: 1}}, TauEscalate: 0.55, TauL2c: &l2c, TauL2EsquemaNuevo: &nuevo}
	l1 := &L1{calib: cal, cache: newLRU[map[string][]float32](0, 1<<20, costeEmbeddings)}
	l2 := NuevoL2cCon(NuevoL2Con(nil, nil, cal.ParaL2(), nil), nil, nil)
	m := NuevasMetricas()
	c, err := NuevaCascadaConTauNuevo([]Capa{{"L1", 0.8}, {"L2", l2c}}, []Decisor{l1, l2}, m, &nuevo)
	if err != nil {
		t.Fatal(err)
	}
	c.PublicaCalib()
	out := metricasTexto(m)
	for _, q := range []string{
		`chispa_calib_tau{capa="L2",clave="tau_escalate",origen="calib"} 0.55`,
		`chispa_calib_tau{capa="L2",clave="tau_l2c",origen="calib"} 0.2`,
	} {
		if !strings.Contains(out, q) {
			t.Errorf("falta %s\n%s", q, out)
		}
	}
}
