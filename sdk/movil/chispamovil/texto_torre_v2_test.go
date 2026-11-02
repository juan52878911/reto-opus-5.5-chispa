package chispamovil

import (
	"encoding/json"
	"os"
	"reflect"
	"slices"
	"strings"
	"testing"

	"chispa/format/chispa3"
	"chispa/runtime/torre"
)

// Paridad con el generador de Python (server/decide/testdata/gen_texto_torre_v2.py): v1 y v2 de los mismos casos.
func TestTextosTorreL2ParidadV2(t *testing.T) {
	b, err := os.ReadFile("../../../server/decide/testdata/texto_torre_v2.json")
	if err != nil {
		t.Fatal(err)
	}
	var cs []struct {
		Kind     string `json:"kind"`
		Pregunta string `json:"pregunta"`
		Opciones []struct {
			ID          string `json:"id"`
			Description string `json:"description"`
		} `json:"opciones"`
		V1 []string `json:"v1"`
		V2 []string `json:"v2_sin_id"`
	}
	if err := json.Unmarshal(b, &cs); err != nil || len(cs) < 15 {
		t.Fatalf("paridad: %d casos, %v", len(cs), err)
	}
	for i, k := range cs {
		p := pregunta{Texto: k.Pregunta, Kind: k.Kind}
		for _, o := range k.Opciones {
			p.Opciones = append(p.Opciones, opcion{ID: o.ID, Description: o.Description})
		}
		for ver, want := range map[string][]string{"v1": k.V1, "v2_sin_id": k.V2} {
			if got := torre.Textos(ver, aTorre(p)); !reflect.DeepEqual(got, want) {
				t.Errorf("caso %d (%s, %s): Go %q, Python %q", i, k.Kind, ver, got, want)
			}
		}
	}
}

// El fichero abierto lee META.texto_torre y TextosTorreL2 coincide con los textos que pediría el servidor (misma versión).
func TestTextosTorreL2SegunMeta(t *testing.T) {
	for _, ver := range []string{"", "v1", "v2_sin_id"} {
		meta, err := chispa3.MetaTexto{Meta: chispa3.Meta{Version: 1}, TextoTorre: ver}.Codificar()
		if err != nil {
			t.Fatal(err)
		}
		secs := append(metaYCalib(t), chispa3.Seccion{Tipo: chispa3.L2, Datos: []byte("ONNX-falso")},
			chispa3.Seccion{Tipo: chispa3.ESQUEMAS, Datos: mustEsq()}, seccionTorreFalsa(t)) // texto_torre solo se lee con TORR
		secs[0].Datos = meta
		c, err := Abrir(escribirV3(t, secs))
		if err != nil {
			t.Fatalf("%q: %v", ver, err)
		}
		efectiva := ver
		if efectiva == "" {
			efectiva = "v1"
		}
		if c.TextoTorre() != efectiva {
			t.Errorf("%q: TextoTorre %q", ver, c.TextoTorre())
		}
		for _, q := range preguntasTorre {
			g := &grabador{}
			p, _ := leerPregunta(q)
			if _, err := servidorL2(g).ConTextoTorre(ver).Decidir(t.Context(), aDecideL2(p)); err != nil {
				t.Fatal(err)
			}
			var textos []string
			if err := json.Unmarshal([]byte(c.TextosTorreL2(q)), &textos); err != nil {
				t.Fatal(err)
			}
			if !slices.Equal(textos, g.textos) {
				t.Errorf("%q %s: móvil %q ≠ servidor %q", ver, q, textos, g.textos)
			}
			if ver == "v2_sin_id" && strings.Contains(q, `"description"`) && slices.ContainsFunc(textos, func(s string) bool { return strings.Contains(s, "· queja ·") }) {
				t.Errorf("v2 con descripción no debe llevar el id: %q", textos)
			}
		}
		c.Cerrar()
	}
}

// Valor desconocido en META.texto_torre: error de carga claro.
func TestAbrirTextoTorreDesconocido(t *testing.T) {
	secs := append(metaYCalib(t), chispa3.Seccion{Tipo: chispa3.L2, Datos: []byte("ONNX-falso")},
		chispa3.Seccion{Tipo: chispa3.ESQUEMAS, Datos: mustEsq()}, seccionTorreFalsa(t))
	secs[0].Datos = []byte(`{"version":1,"texto_torre":"v9"}`)
	if _, err := Abrir(escribirV3(t, secs)); err == nil || !strings.Contains(err.Error(), "texto_torre") {
		t.Fatalf("error %v", err)
	}
}
