package decide

import (
	"testing"

	"chispa/format/chispa3"
)

// T1: prioridad config > CALIB > default 0,846, y modo explícito «sin τ propio».
func TestTauL2EsquemaNuevoT1(t *testing.T) {
	calibTau := 0.3
	cfgTau := 0.9
	build := func(cfg Config, calib *float64) *float64 {
		esq, _ := chispa3.CodificarEsquemas(2, nil)
		f := v3Tiny(t, chispa3.Calib{TauEscalate: 0.5, TauL2EsquemaNuevo: calib, Tipos: map[string]chispa3.ParamsTipo{}}, chispa3.Seccion{Tipo: chispa3.L2, Datos: []byte("onnx-l2")}, chispa3.Seccion{Tipo: chispa3.ESQUEMAS, Datos: esq})
		cfg.Capas = ConfigPorDefecto().Capas
		if _, err := ArmarDesde(f, NuevoL0(8), &cfg, false, tokFalso{}, ConSesionS(sesionFalsa{[][]float32{{3, 0}}})); err != nil {
			t.Fatal(err)
		}
		return cfg.TauL2EsquemaNuevo
	}
	if TauL2EsquemaNuevoPorDefecto != 0.846 {
		t.Fatalf("default: %v", TauL2EsquemaNuevoPorDefecto)
	}
	if v := build(Config{}, nil); v == nil || *v != 0.846 {
		t.Errorf("default: %v", v)
	}
	if v := build(Config{}, &calibTau); v == nil || *v != 0.3 {
		t.Errorf("CALIB sobre default: %v", v)
	}
	if v := build(Config{TauL2EsquemaNuevo: &cfgTau}, &calibTau); v == nil || *v != 0.9 {
		t.Errorf("config sobre CALIB: %v", v)
	}
	if v := build(Config{TauL2EsquemaNuevoApagado: true}, nil); v != nil {
		t.Errorf("apagado sin CALIB: %v", v)
	}
	if v := build(Config{TauL2EsquemaNuevoApagado: true}, &calibTau); v != nil {
		t.Errorf("apagado ignora también CALIB: %v", v)
	}
	if err := (Config{Capas: ConfigPorDefecto().Capas, CacheEsquemas: 1, CacheRespuestas: 1, TauL2EsquemaNuevo: &cfgTau, TauL2EsquemaNuevoApagado: true}).Validar(); err == nil {
		t.Error("apagado + τ debe rechazarse")
	}
}
