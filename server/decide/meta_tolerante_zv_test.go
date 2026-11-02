package decide

import (
	"testing"

	"chispa/format/chispa3"
)

// Un .chispa zero-shot con META «libre» (licencias anidadas, dorado que no es sha256) cargaba antes de ZT: el runtime solo lee
// texto_torre de META y solo con TORR.
func TestArmarDesdeMetaZeroShotTolerante(t *testing.T) {
	f := conTorreSeccion(t)
	secs := []chispa3.Seccion{{Tipo: chispa3.META, Datos: []byte(
		`{"version":1,"tareas":["q"],"licencias":{"massive":{"licencia":"CC-BY"}},"dorado":"dorado/v3.jsonl","otro":1,"texto_torre":"v2_sin_id"}`)}}
	for _, tp := range []chispa3.Tipo{chispa3.L2, chispa3.ESQUEMAS} {
		d, _ := f.Bytes(tp)
		secs = append(secs, chispa3.Seccion{Tipo: tp, Datos: d})
	}
	tr, err := chispa3.CodificarTORR(chispa3.Torre{Dim: 2, MaxLen: 128, Prefijo: "passage: ", TextoTorre: chispa3.TextoTorreV2SinID, ONNX: []byte("onnx-torre")})
	if err != nil {
		t.Fatal(err)
	}
	secs = append(secs, chispa3.Seccion{Tipo: chispa3.TORR, Datos: tr})
	mt, err := ArmarDesde(v3Tiny(t, calibTiny(), secs...), NuevoL0(8), &Config{}, false, tokFalso{}, ConSesionS(sesionFalsa{[][]float32{{3, 0}}}))
	if err != nil {
		t.Fatalf("META zero-shot debía cargar: %v", err)
	}
	if mt.Cerrar != nil {
		mt.Cerrar()
	}
}

// Sin TORR no se mira texto_torre: ni un valor desconocido impide cargar.
func TestArmarDesdeMetaSinTorreNoSeLee(t *testing.T) {
	f := conTorreSeccion(t)
	secs := []chispa3.Seccion{{Tipo: chispa3.META, Datos: []byte(`{"version":1,"licencias":{"a":{"b":1}},"texto_torre":"v9"}`)}}
	for _, tp := range []chispa3.Tipo{chispa3.L2, chispa3.ESQUEMAS} {
		d, _ := f.Bytes(tp)
		secs = append(secs, chispa3.Seccion{Tipo: tp, Datos: d})
	}
	mt, err := ArmarDesde(v3Tiny(t, calibTiny(), secs...), NuevoL0(8), &Config{}, false, tokFalso{}, ConSesionS(sesionFalsa{[][]float32{{3, 0}}}))
	if err != nil {
		t.Fatalf("sin TORR no se lee texto_torre: %v", err)
	}
	if mt.Cerrar != nil {
		mt.Cerrar()
	}
}
