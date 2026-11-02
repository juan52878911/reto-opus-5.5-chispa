package chispamovil

import (
	"testing"

	"chispa/format/chispa3"
)

func seccionTorreFalsa(t *testing.T) chispa3.Seccion {
	t.Helper()
	tb, err := chispa3.CodificarTORR(chispa3.Torre{Dim: 256, MaxLen: 64, Prefijo: "passage: ", ONNX: []byte("onnx!")})
	if err != nil {
		t.Fatal(err)
	}
	return chispa3.Seccion{Tipo: chispa3.TORR, Datos: tb}
}

func seccionesMetaLibre(t *testing.T, meta string, conTorre bool) []chispa3.Seccion {
	t.Helper()
	secs := append(metaYCalib(t), chispa3.Seccion{Tipo: chispa3.L2, Datos: []byte("ONNX-falso")},
		chispa3.Seccion{Tipo: chispa3.ESQUEMAS, Datos: mustEsq()})
	secs[0].Datos = []byte(meta)
	if conTorre {
		secs = append(secs, seccionTorreFalsa(t))
	}
	return secs
}

// Un .chispa zero-shot con META libre (licencias anidadas, dorado que no es sha256) abre: solo se lee texto_torre, y con TORR.
func TestAbrirMetaZeroShotTolerante(t *testing.T) {
	c, err := Abrir(escribirV3(t, seccionesMetaLibre(t,
		`{"version":1,"tareas":["q"],"licencias":{"massive":{"licencia":"CC-BY"}},"dorado":"dorado/v3.jsonl","otro":1,"texto_torre":"v2_sin_id"}`, true)))
	if err != nil {
		t.Fatalf("META zero-shot debía abrir: %v", err)
	}
	defer c.Cerrar()
	if c.TextoTorre() != "v2_sin_id" {
		t.Errorf("TextoTorre %q", c.TextoTorre())
	}
}

// Sin TORR no se mira texto_torre.
func TestAbrirMetaSinTorreNoSeLee(t *testing.T) {
	c, err := Abrir(escribirV3(t, seccionesMetaLibre(t, `{"version":1,"licencias":{"a":{"b":1}},"texto_torre":"v9"}`, false)))
	if err != nil {
		t.Fatalf("sin TORR no se lee texto_torre: %v", err)
	}
	c.Cerrar()
}
