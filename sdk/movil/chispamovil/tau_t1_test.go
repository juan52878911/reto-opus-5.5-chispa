package chispamovil

import (
	"bytes"
	"os"
	"path/filepath"
	"testing"

	"chispa/format/chispa3"
)

func abrirConTauNuevo(t *testing.T, tau *float64) *Chispa {
	t.Helper()
	calib, _ := chispa3.Calib{TauEscalate: 0.6, TauL2EsquemaNuevo: tau, Tipos: map[string]chispa3.ParamsTipo{"choice": {T: 0.1, A: 1, Theta: .5}}}.Codificar()
	var buf bytes.Buffer
	if err := chispa3.Escribir(&buf, []chispa3.Seccion{metaYCalib(t)[0], {Tipo: chispa3.CALIB, Datos: calib}}); err != nil {
		t.Fatal(err)
	}
	ruta := filepath.Join(t.TempDir(), "t.chispa")
	os.WriteFile(ruta, buf.Bytes(), 0o600)
	c, err := Abrir(ruta)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { c.Cerrar() })
	return c
}

// T1: CALIB > default 0,846, y SinTauEsquemaNuevo devuelve −1 (también por encima de CALIB).
func TestT1TauL2EsquemaNuevo(t *testing.T) {
	if v := abrirConTauNuevo(t, nil).TauL2EsquemaNuevo(); v != 0.846 {
		t.Errorf("default: %v", v)
	}
	tau := 0.3
	c := abrirConTauNuevo(t, &tau)
	if v := c.TauL2EsquemaNuevo(); v != 0.3 {
		t.Errorf("CALIB: %v", v)
	}
	c.SinTauEsquemaNuevo(true)
	if v := c.TauL2EsquemaNuevo(); v != -1 {
		t.Errorf("apagado con CALIB: %v", v)
	}
	c.SinTauEsquemaNuevo(false)
	if v := c.TauL2EsquemaNuevo(); v != 0.3 {
		t.Errorf("reactivado: %v", v)
	}
	d := abrirConTauNuevo(t, nil)
	d.SinTauEsquemaNuevo(true)
	if v := d.TauL2EsquemaNuevo(); v != -1 {
		t.Errorf("apagado sin CALIB: %v", v)
	}
}
