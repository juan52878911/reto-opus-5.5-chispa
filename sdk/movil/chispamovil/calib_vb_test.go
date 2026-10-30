package chispamovil

import (
	"testing"

	"chispa/format/chispa3"
)

// R15-7: tau_l2c solo se publica con CONJ; tau_escalate (respaldo) se publica siempre, como en el servidor.
func TestVBTauL2cSoloConConj(t *testing.T) {
	l2c := 0.2
	cal := chispa3.Calib{TauEscalate: 0.5, TauL2c: &l2c}
	ts := tausDe(t, &Chispa{tieneL2: true, calib: cal}, "L2")
	if _, ok := ts["tau_l2c"]; ok {
		t.Fatalf("sin CONJ no hay L2c: no se publica tau_l2c: %+v", ts)
	}
	if ts["tau_escalate"].Valor != 0.5 {
		t.Fatalf("tau_escalate de respaldo: %+v", ts)
	}
	ts = tausDe(t, &Chispa{tieneL2: true, conj: &chispa3.Conj{}, calib: cal}, "L2")
	if ts["tau_l2c"].Valor != 0.2 || ts["tau_l2c"].Origen != origenCalib || ts["tau_escalate"].Valor != 0.5 {
		t.Fatalf("con CONJ: tau_escalate y tau_l2c separados: %+v", ts)
	}
}
