package chispamovil

import (
	"encoding/json"
	"testing"

	"chispa/format/chispa3"
)

func tausDe(t *testing.T, c *Chispa, capa string) map[string]tauCalib {
	t.Helper()
	var vs []vistaCalib
	if err := json.Unmarshal([]byte(c.CalibJSON()), &vs); err != nil {
		t.Fatal(err)
	}
	out := map[string]tauCalib{}
	for _, v := range vs {
		if v.Capa == capa {
			for _, x := range v.Taus {
				out[x.Clave] = x
			}
		}
	}
	return out
}

// H7: los τ publicados son los que lee la cascada: τ de esquema nuevo (default o CALIB) y tau_l2c, con su origen.
func TestCalibTauEfectivoYOrigen(t *testing.T) {
	c := &Chispa{tieneL2: true, calib: chispa3.Calib{TauEscalate: 0.5}}
	ts := tausDe(t, c, "L2")
	if x, ok := ts["tau_l2_esquema_nuevo"]; !ok || x.Valor != TauL2EsquemaNuevoPorDefecto || x.Origen != origenDefecto {
		t.Fatalf("esquema nuevo por defecto: %+v", ts)
	}
	l2c, nuevo := 0.2, 0.9
	c = &Chispa{tieneL2: true, conj: &chispa3.Conj{}, calib: chispa3.Calib{TauEscalate: 0.5, TauL2c: &l2c, TauL2EsquemaNuevo: &nuevo}}
	ts = tausDe(t, c, "L2")
	if ts["tau_l2_esquema_nuevo"].Valor != 0.9 || ts["tau_l2_esquema_nuevo"].Origen != origenCalib || ts["tau_l2c"].Valor != 0.2 {
		t.Fatalf("CALIB: %+v", ts)
	}
	c.SinTauEsquemaNuevo(true)
	if _, ok := tausDe(t, c, "L2")["tau_l2_esquema_nuevo"]; ok {
		t.Fatal("apagado: no hay τ propio")
	}
	if ts := tausDe(t, c, "L1"); ts["tau_escalate"].Origen != origenCalib {
		t.Fatalf("L1: %+v", ts)
	}
}

// H9: sin_tipo de score mira la clave que usa cada capa.
func TestCalibSinTipoScorePorCapa(t *testing.T) {
	tiene := func(xs []string, x string) bool {
		for _, y := range xs {
			if y == x {
				return true
			}
		}
		return false
	}
	solo4 := chispa3.Calib{Tipos: map[string]chispa3.ParamsTipo{"score4": {T: 1}, "score4#1": {T: 1}}}
	if !tiene(vistaCalibCapa("L1", solo4, origenFichero, true).SinCalib, "score") || tiene(vistaCalibCapa("L2", solo4, origenFichero, true).SinCalib, "score") {
		t.Fatal("score4: L1 debe avisar y L2 no")
	}
	solo := chispa3.Calib{Tipos: map[string]chispa3.ParamsTipo{"score": {T: 1}}}
	if tiene(vistaCalibCapa("L1", solo, origenFichero, true).SinCalib, "score") || !tiene(vistaCalibCapa("L2", solo, origenFichero, true).SinCalib, "score") {
		t.Fatal("score: L1 no debe avisar y L2 sí")
	}
}
