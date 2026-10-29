package decide

import (
	"math"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"chispa/format/chispa3"
)

func TestSopl1InvalidaConLambdaInfinita(t *testing.T) {
	inf := math.Inf(1)
	fin := 5.0
	build := func(cfg Config) (Montaje, error) {
		f := v3Tiny(t, chispa3.Calib{TauEscalate: 0.5, Tipos: map[string]chispa3.ParamsTipo{}}, chispa3.Seccion{Tipo: chispa3.SOPL1, Datos: []byte("basura")})
		cfg.Capas = ConfigPorDefecto().Capas
		return ArmarDesde(f, NuevoL0(8), &cfg, true, tokFalso{})
	}
	for nombre, cfg := range map[string]Config{"nil": {}, "inf": {L1ShrinkageLambda: &inf, L2ShrinkageLambda: &inf}} {
		mt, err := build(cfg)
		if err != nil {
			t.Fatalf("%s: SOPL1 inválida no debe impedir arrancar: %v", nombre, err)
		}
		if len(mt.Avisos) == 0 || !strings.Contains(mt.Avisos[0], "SOPL1") {
			t.Errorf("%s: falta el aviso: %v", nombre, mt.Avisos)
		}
	}
	if _, err := build(Config{L1ShrinkageLambda: &fin}); err == nil || !strings.Contains(err.Error(), "SOPL1") {
		t.Errorf("con λ finito debe dar error claro: %v", err)
	}
}

func TestTauL2EsquemaNuevoDeCalibConConfig(t *testing.T) {
	calibTau := 0.3
	esq, _ := chispa3.CodificarEsquemas(2, nil)
	f := v3Tiny(t, chispa3.Calib{TauEscalate: 0.5, TauL2EsquemaNuevo: &calibTau, Tipos: map[string]chispa3.ParamsTipo{}}, chispa3.Seccion{Tipo: chispa3.L2, Datos: []byte("onnx-l2")}, chispa3.Seccion{Tipo: chispa3.ESQUEMAS, Datos: esq})
	cfg := Config{Capas: ConfigPorDefecto().Capas}
	// tauDeCalib=false: hay -config, pero sin el campo.
	if _, err := ArmarDesde(f, NuevoL0(8), &cfg, false, tokFalso{}, ConSesionS(sesionFalsa{[][]float32{{3, 0}}})); err != nil {
		t.Fatal(err)
	}
	if cfg.TauL2EsquemaNuevo == nil || *cfg.TauL2EsquemaNuevo != 0.3 {
		t.Errorf("τ de CALIB debe usarse si la config no lo trae: %v", cfg.TauL2EsquemaNuevo)
	}
}

func TestConTimeoutCabeceras(t *testing.T) {
	lento := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { <-r.Context().Done() })
	w := httptest.NewRecorder()
	ConTimeout(lento, 10*time.Millisecond).ServeHTTP(w, httptest.NewRequest("POST", "/v1/decide", nil))
	if w.Code != 503 || w.Header().Get("Retry-After") == "" || w.Header().Get("Content-Type") != "application/json" || !strings.Contains(w.Body.String(), `"timeout"`) {
		t.Errorf("timeout: %d %v %s", w.Code, w.Header(), w.Body)
	}
	w = httptest.NewRecorder()
	ConTimeout(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(200) }), time.Second).ServeHTTP(w, httptest.NewRequest("GET", "/", nil))
	if w.Code != 200 || w.Header().Get("Retry-After") != "" {
		t.Errorf("respuesta normal: %d %v", w.Code, w.Header())
	}
}
