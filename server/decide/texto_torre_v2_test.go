package decide

import (
	"encoding/json"
	"net/http/httptest"
	"os"
	"reflect"
	"strings"
	"testing"

	"chispa/format/chispa3"
)

type casoTextoV2 struct {
	Kind     string   `json:"kind"`
	Pregunta string   `json:"pregunta"`
	Opciones []Opcion `json:"opciones"`
	V1       []string `json:"v1"`
	V2       []string `json:"v2_sin_id"`
}

// Paridad con el generador de Python (testdata/gen_texto_torre_v2.py): v1 y v2 de los mismos casos (multi incluido).
func TestTextosTorreParidadV2(t *testing.T) {
	b, err := os.ReadFile("testdata/texto_torre_v2.json")
	if err != nil {
		t.Fatal(err)
	}
	var cs []casoTextoV2
	if err := json.Unmarshal(b, &cs); err != nil || len(cs) < 25 {
		t.Fatalf("%d casos, %v", len(cs), err)
	}
	for i, c := range cs {
		p := Pregunta{Texto: c.Pregunta, Kind: c.Kind, Opciones: c.Opciones}
		if got := TextosTorre(chispa3.TextoTorreV1, p); !reflect.DeepEqual(got, c.V1) {
			t.Errorf("caso %d (%s) v1: Go %q, Python %q", i, c.Kind, got, c.V1)
		}
		if got := TextosTorre(chispa3.TextoTorreV2SinID, p); !reflect.DeepEqual(got, c.V2) {
			t.Errorf("caso %d (%s) v2: Go %q, Python %q", i, c.Kind, got, c.V2)
		}
	}
}

func conTextoTorre(t *testing.T, version string) *chispa3.Fichero {
	t.Helper()
	meta, err := chispa3.MetaTexto{Meta: chispa3.Meta{Version: 1}, TextoTorre: version}.Codificar()
	if err != nil {
		t.Fatal(err)
	}
	f := conTorreSeccion(t)
	secs := []chispa3.Seccion{{Tipo: chispa3.META, Datos: meta}}
	for _, tp := range []chispa3.Tipo{chispa3.L2, chispa3.ESQUEMAS} {
		b, err := f.Bytes(tp)
		if err != nil {
			t.Fatal(err)
		}
		secs = append(secs, chispa3.Seccion{Tipo: tp, Datos: b})
	}
	tr, err := chispa3.CodificarTORR(chispa3.Torre{Dim: 2, MaxLen: 128, Prefijo: "passage: ", TextoTorre: version, ONNX: []byte("onnx-torre")})
	if err != nil {
		t.Fatal(err)
	}
	secs = append(secs, chispa3.Seccion{Tipo: chispa3.TORR, Datos: tr})
	return v3Tiny(t, calibTiny(), secs...)
}

// Servidor armado desde un .chispa sintético: las torres al vuelo (choice, noul «true», score nivel máximo) usan el texto de la
// versión de META; /healthz y Capacidades la exponen. v1 (o ausente) lleva el id; v2 lo quita solo si hay descripción.
func TestTorreAlVueloSegunTextoTorre(t *testing.T) {
	cuerpo := `{"state":"me cobraron dos veces","questions":[{"id":"q1","kind":"choice","question":"¿De qué trata?",
	  "options":[{"id":"ventas","description":"compras"},{"id":"quejas"}]},
	 {"id":"q2","kind":"noul","question":"¿Es una queja?","options":[{"id":"false"},{"id":"true","description":"reclamos"}]},
	 {"id":"q3","kind":"score","question":"¿Qué tan molesto?","options":[{"id":"3","description":"mucho"},{"id":"1"},{"id":"2"}]}]}`
	v1 := []string{"passage: ¿De qué trata? · ventas · compras", "passage: ¿De qué trata? · quejas · ",
		"passage: ¿Es una queja? · true · reclamos", "passage: ¿Qué tan molesto? · 3 · mucho"}
	v2 := []string{"passage: ¿De qué trata? · compras", "passage: ¿De qué trata? · quejas · ",
		"passage: ¿Es una queja? · reclamos", "passage: ¿Qué tan molesto? · mucho"}
	for _, c := range []struct {
		version, healthz string
		want             []string
	}{{"", "v1", v1}, {"v1", "v1", v1}, {"v2_sin_id", "v2_sin_id", v2}} {
		enc := &codificadorPorTexto{clave: "· quejas ·"}
		cfg := Config{CacheEsquemas: 64}
		mt, err := ArmarDesde(conTextoTorre(t, c.version), NuevoL0(8), &cfg, false, tokFalso{}, ConSesionS(sesionFalsa{[][]float32{{3, 0}}}), ConCodificadorTorre(enc))
		if err != nil || len(mt.Avisos) != 0 {
			t.Fatalf("%q: %v %v", c.version, err, mt.Avisos)
		}
		casc, err := NuevaCascada([]Capa{{"L2", 0.5}}, []Decisor{mt.L2}, NuevasMetricas())
		if err != nil {
			t.Fatal(err)
		}
		if cp := casc.Capacidades(); cp.TextoTorre != c.healthz || !cp.TorreAlVuelo {
			t.Fatalf("%q: Capacidades %+v", c.version, cp)
		}
		h := NuevoServidor(casc, NuevasMetricas(), 0).Handler()
		if rr := post(h, cuerpo); rr.Code != 200 {
			t.Fatalf("%q: %d %s", c.version, rr.Code, rr.Body)
		}
		if !reflect.DeepEqual(enc.textos, c.want) {
			t.Errorf("%q: textos %q, quería %q", c.version, enc.textos, c.want)
		}
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, httptest.NewRequest("GET", "/healthz", nil))
		if b := rec.Body.String(); !strings.Contains(b, `"texto_torre":"`+c.healthz+`"`) {
			t.Errorf("%q: healthz %s", c.version, b)
		}
	}
}

// Un valor desconocido en META.texto_torre es un error de carga claro, no un v1 silencioso.
func TestArmarDesdeTextoTorreDesconocido(t *testing.T) {
	f := conTorreSeccion(t)
	b, _ := f.Bytes(chispa3.META)
	malo := strings.Replace(string(b), `"version":1`, `"version":1,"texto_torre":"v9"`, 1)
	secs := []chispa3.Seccion{{Tipo: chispa3.META, Datos: []byte(malo)}}
	for _, tp := range []chispa3.Tipo{chispa3.L2, chispa3.ESQUEMAS, chispa3.TORR} {
		d, _ := f.Bytes(tp)
		secs = append(secs, chispa3.Seccion{Tipo: tp, Datos: d})
	}
	_, err := ArmarDesde(v3Tiny(t, calibTiny(), secs...), NuevoL0(8), &Config{}, false, tokFalso{}, ConSesionS(sesionFalsa{[][]float32{{3, 0}}}))
	if err == nil || !strings.Contains(err.Error(), "texto_torre") || !strings.Contains(err.Error(), "v9") {
		t.Fatalf("error %v", err)
	}
}

// La versión efectiva sale de TORR: META sin texto_torre con TORR v2 monta v2; META y TORR discrepantes son un error de carga
// claro (en los dos sentidos), no un texto elegido en silencio.
func TestArmarDesdeTextoTorreSaleDeTORR(t *testing.T) {
	armar := func(meta, texto string) (Montaje, error) {
		f := conTorreSeccion(t)
		secs := []chispa3.Seccion{{Tipo: chispa3.META, Datos: []byte(meta)}}
		for _, tp := range []chispa3.Tipo{chispa3.L2, chispa3.ESQUEMAS} {
			d, _ := f.Bytes(tp)
			secs = append(secs, chispa3.Seccion{Tipo: tp, Datos: d})
		}
		tr, err := chispa3.CodificarTORR(chispa3.Torre{Dim: 2, MaxLen: 128, Prefijo: "passage: ", TextoTorre: texto, ONNX: []byte("onnx-torre")})
		if err != nil {
			t.Fatal(err)
		}
		secs = append(secs, chispa3.Seccion{Tipo: chispa3.TORR, Datos: tr})
		return ArmarDesde(v3Tiny(t, calibTiny(), secs...), NuevoL0(8), &Config{CacheEsquemas: 64}, false, tokFalso{}, ConSesionS(sesionFalsa{[][]float32{{3, 0}}}), ConCodificadorTorre(&codificadorPorTexto{clave: "x"}))
	}
	mt, err := armar(`{"version":1}`, chispa3.TextoTorreV2SinID)
	if err != nil {
		t.Fatal(err)
	}
	if v := mt.L2.(*L2).VersionTextoTorre(); v != chispa3.TextoTorreV2SinID {
		t.Errorf("versión efectiva %q, quería v2_sin_id (de TORR)", v)
	}
	for _, c := range []struct{ meta, texto string }{
		{`{"version":1,"texto_torre":"v2_sin_id"}`, chispa3.TextoTorreV1},
		{`{"version":1,"texto_torre":"v1"}`, chispa3.TextoTorreV2SinID},
	} {
		if _, err := armar(c.meta, c.texto); err == nil || !strings.Contains(err.Error(), "no coinciden") {
			t.Errorf("%s con TORR %q: error %v", c.meta, c.texto, err)
		}
	}
}

// Descripciones repetidas en v2: solo esas opciones llevan id, en las torres al vuelo del servidor (choice y multi).
func TestTextosTorreDescripcionesRepetidas(t *testing.T) {
	for _, kind := range []string{KindChoice, KindMulti} {
		p := Pregunta{Texto: "q", Kind: kind, Opciones: []Opcion{{ID: "a", Description: "igual"}, {ID: "b", Description: " igual\t"},
			{ID: "c", Description: "otra"}, {ID: "d"}}}
		want := []string{"passage: q · a · igual", "passage: q · b ·  igual\t", "passage: q · otra", "passage: q · d · "}
		if got := TextosTorre(chispa3.TextoTorreV2SinID, p); !reflect.DeepEqual(got, want) {
			t.Errorf("%s: %q, quería %q", kind, got, want)
		}
		// La firma por opción (la que usa L2) ve toda la pregunta y da lo mismo que la lista.
		for i, o := range OpcionesConsulta(p) {
			if got := TextoTorre(chispa3.TextoTorreV2SinID, p, o); got != want[i] {
				t.Errorf("%s opción %s: %q, quería %q", kind, o.ID, got, want[i])
			}
		}
	}
}
