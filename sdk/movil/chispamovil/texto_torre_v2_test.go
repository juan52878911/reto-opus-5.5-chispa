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

// Paridad con el generador de Python (fixture copiado tal cual del entrenamiento): v1 y v2 de los mismos casos.
func TestTextosTorreL2ParidadV2(t *testing.T) {
	b, err := os.ReadFile("../../../server/decide/testdata/texto_torre_v2.json")
	if err != nil {
		t.Fatal(err)
	}
	var fx struct {
		Preguntas []struct {
			Kind     string `json:"kind"`
			Pregunta string `json:"pregunta"`
			Opciones []struct {
				ID          string `json:"id"`
				Description string `json:"description"`
			} `json:"opciones"`
			V1 []string `json:"v1"`
			V2 []string `json:"v2_sin_id"`
		} `json:"preguntas"`
	}
	if err := json.Unmarshal(b, &fx); err != nil || len(fx.Preguntas) == 0 {
		t.Fatalf("paridad: %d casos, %v", len(fx.Preguntas), err)
	}
	cs := fx.Preguntas
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
			chispa3.Seccion{Tipo: chispa3.ESQUEMAS, Datos: mustEsq()}, seccionTorreFalsaTexto(t, ver)) // texto_torre solo se lee con TORR; TORR dice la versión
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

func abrirConMetaYTorr(t *testing.T, meta, texto string) (*Chispa, error) {
	t.Helper()
	secs := append(metaYCalib(t), chispa3.Seccion{Tipo: chispa3.L2, Datos: []byte("ONNX-falso")},
		chispa3.Seccion{Tipo: chispa3.ESQUEMAS, Datos: mustEsq()}, seccionTorreFalsaTexto(t, texto))
	secs[0].Datos = []byte(meta)
	return Abrir(escribirV3(t, secs))
}

// La versión efectiva sale de TORR; META que la trae y discrepa carga sin torre al vuelo, con aviso y motivo (en los dos sentidos).
func TestAbrirTextoTorreSaleDeTORR(t *testing.T) {
	c, err := abrirConMetaYTorr(t, `{"version":1}`, chispa3.TextoTorreV2SinID)
	if err != nil || c.TextoTorre() != "v2_sin_id" {
		t.Fatalf("TORR v2 sin texto_torre en META: %v", err)
	}
	c.Cerrar()
	for _, meta := range []struct{ meta, texto string }{
		{`{"version":1,"texto_torre":"v2_sin_id"}`, chispa3.TextoTorreV1},
		{`{"version":1,"texto_torre":"v1"}`, chispa3.TextoTorreV2SinID},
	} {
		c, err := abrirConMetaYTorr(t, meta.meta, meta.texto)
		if err != nil {
			t.Errorf("%s con TORR %q: Abrir no debe fallar: %v", meta.meta, meta.texto, err)
			continue
		}
		if c.TieneTorre() || c.TorreAlVueloMotivo() != "texto_torre_inconsistente" || !strings.Contains(c.Avisos(), "no coinciden") {
			t.Errorf("%s con TORR %q: torre %v, motivo %q, avisos %q", meta.meta, meta.texto, c.TieneTorre(), c.TorreAlVueloMotivo(), c.Avisos())
		}
		c.Cerrar()
	}
}

// TextosTorreL2 aplica la regla de descripciones repetidas y da los textos de las listas de paridad.
func TestTextosTorreL2DescripcionesRepetidas(t *testing.T) {
	c, err := abrirConMetaYTorr(t, `{"version":1}`, chispa3.TextoTorreV2SinID)
	if err != nil {
		t.Fatal(err)
	}
	defer c.Cerrar()
	// multi sin CALIB «multi_l2» no pide torres; su regla (la misma torre.Textos) la cubre la paridad del JSON.
	for _, kind := range []string{"choice"} {
		q := `{"kind":"` + kind + `","question":"q","options":[{"id":"a","description":"igual"},{"id":"b","description":" igual "},{"id":"c","description":"otra"}]}`
		want := []string{"passage: q · a · igual", "passage: q · b ·  igual ", "passage: q · otra"}
		var got []string
		if err := json.Unmarshal([]byte(c.TextosTorreL2(q)), &got); err != nil || !slices.Equal(got, want) {
			t.Errorf("%s: %q (%v), quería %q", kind, got, err, want)
		}
	}
}
