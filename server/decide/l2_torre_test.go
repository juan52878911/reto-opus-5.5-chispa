package decide

import (
	"context"
	"encoding/json"
	"strings"
	"testing"

	"chispa/format/chispa3"
)

// codificadorPorTexto devuelve una torre por texto y apunta los textos pedidos: la que contiene «clave» apunta al eje 0.
type codificadorPorTexto struct {
	clave  string
	textos []string
}

func (c *codificadorPorTexto) Torre(texto string) ([]float32, error) {
	c.textos = append(c.textos, texto)
	if strings.Contains(texto, c.clave) {
		return []float32{1, 0}, nil
	}
	return []float32{0, 1}, nil
}

func conTorreSeccion(t *testing.T) *chispa3.Fichero {
	t.Helper()
	esq, err := chispa3.CodificarEsquemas(2, []chispa3.EntradaEsquema{ent("solo en ESQUEMAS", []string{"a"}, 1, 1, 0)})
	if err != nil {
		t.Fatal(err)
	}
	tr, err := chispa3.CodificarTORR(chispa3.Torre{Dim: 2, MaxLen: 128, Prefijo: "passage: ", ONNX: []byte("onnx-torre")})
	if err != nil {
		t.Fatal(err)
	}
	return v3Tiny(t, calibTiny(), chispa3.Seccion{Tipo: chispa3.L2, Datos: []byte("onnx-l2")},
		chispa3.Seccion{Tipo: chispa3.ESQUEMAS, Datos: esq}, chispa3.Seccion{Tipo: chispa3.TORR, Datos: tr})
}

// De extremo a extremo por /v1/decide: un esquema que ningún .chispa trae lo decide L2 con la torre calculada al vuelo.
// Sin la sección TORR (o sin codificador) L2 calla y la petición sube a la capa siguiente.
func TestDecideHTTPEsquemaNuevoConTorre(t *testing.T) {
	enc := &codificadorPorTexto{clave: "· quejas ·"}
	ses := sesionFalsa{[][]float32{{3, 0}}}
	cfg := Config{CacheEsquemas: 64, CacheRespuestas: 0}
	mt, err := ArmarDesde(conTorreSeccion(t), NuevoL0(8), &cfg, false, tokFalso{}, ConSesionS(ses), ConCodificadorTorre(enc))
	if err != nil || len(mt.Avisos) != 0 {
		t.Fatalf("%v %v", err, mt.Avisos)
	}
	l2, ok := mt.L2.(*L2)
	if !ok || l2.torres == nil {
		t.Fatalf("L2 %T sin torres", mt.L2)
	}
	casc, err := NuevaCascada([]Capa{{"L2", 0.5}}, []Decisor{mt.L2}, NuevasMetricas())
	if err != nil {
		t.Fatal(err)
	}
	h := NuevoServidor(casc, NuevasMetricas(), 0).Handler()
	cuerpo := `{"state":"me cobraron dos veces","questions":[{"id":"q1","kind":"choice","question":"¿De qué trata?",
	  "options":[{"id":"ventas","description":"compras"},{"id":"quejas","description":"reclamos"}]},
	 {"id":"q2","kind":"noul","question":"¿Es una queja?","options":[{"id":"false"},{"id":"true","description":"quejas"}]},
	 {"id":"q3","kind":"score","question":"¿Qué tan molesto?","options":[{"id":"3"},{"id":"1"},{"id":"2"}]}]}`
	rr := post(h, cuerpo)
	if rr.Code != 200 {
		t.Fatalf("%d %s", rr.Code, rr.Body)
	}
	var out struct {
		Results []struct {
			ID, Answer, Layer string
		} `json:"results"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &out); err != nil || len(out.Results) != 3 {
		t.Fatalf("%v %s", err, rr.Body)
	}
	if r := out.Results[0]; r.Layer != "L2" || r.Answer != "quejas" {
		t.Fatalf("choice: %+v", r)
	}
	if r := out.Results[1]; r.Layer != "L2" || r.Answer != "true" {
		t.Fatalf("noul: %+v", r)
	}
	// choice: 2 torres; noul: 1 (la de «true»); score: 1 (el nivel 3, aunque venga primero en la petición o no)
	if len(enc.textos) != 4 {
		t.Fatalf("textos %q", enc.textos)
	}
	want := []string{"passage: ¿De qué trata? · ventas · compras", "passage: ¿De qué trata? · quejas · reclamos",
		"passage: ¿Es una queja? · true · quejas", "passage: ¿Qué tan molesto? · 3 · "}
	for i, w := range want {
		if enc.textos[i] != w || !strings.Contains(enc.textos[i], " · ") {
			t.Errorf("texto %d: %q, esperaba %q", i, enc.textos[i], w)
		}
	}
	// Segunda petición: todo sale de la caché.
	post(h, cuerpo)
	if len(enc.textos) != 4 || l2.Hits.Load() != 3 {
		t.Fatalf("caché: %d textos, %d aciertos", len(enc.textos), l2.Hits.Load())
	}

	// Sin la sección TORR no se monta nada: L2 sin opinión como hoy.
	f := v3Tiny(t, calibTiny(), chispa3.Seccion{Tipo: chispa3.L2, Datos: []byte("onnx-l2")},
		chispa3.Seccion{Tipo: chispa3.ESQUEMAS, Datos: mustEsq(t)})
	mt2, err := ArmarDesde(f, NuevoL0(8), &cfg, false, tokFalso{}, ConSesionS(ses), ConCodificadorTorre(enc))
	if err != nil {
		t.Fatal(err)
	}
	if l := mt2.L2.(*L2); l.torres != nil {
		t.Fatal("torres montadas sin sección TORR")
	}
	r, err := mt2.L2.Decidir(context.Background(), Pregunta{Texto: "nuevo", Kind: KindChoice, Opciones: opsReembolso()})
	if err != nil || r.Conf != 0 {
		t.Fatalf("%+v %v", r, err)
	}
}

// Con TORR pero un tokenizador sin modo passage la torre no se monta y se avisa; L2 sigue con ESQUEMAS.
func TestArmarDesdeTorreSinTokenizadorPasaje(t *testing.T) {
	mt, err := ArmarDesde(conTorreSeccion(t), NuevoL0(8), &Config{CacheEsquemas: 8}, false, tokFalso{}, ConSesionS(sesionFalsa{[][]float32{{1, 0}}}))
	if err != nil {
		t.Fatal(err)
	}
	if mt.L2.(*L2).torres != nil || len(mt.Avisos) != 1 || !strings.Contains(mt.Avisos[0], "sin torres") {
		t.Fatalf("%+v", mt.Avisos)
	}
}

// Regresión: la caché es por torre, no por esquema. Con las opciones en otro orden la torre de cada una sigue siendo la suya.
func TestTorreCacheIndependienteDelOrden(t *testing.T) {
	esq, _ := chispa3.DecodificarEsquemas(mustEsq(t))
	l := NuevoL2Con(sesionFalsa{[][]float32{{3, 0}}}, esq, chispa3.Calib{}, tokFalso{}).ConTorres(&codificadorPorTexto{clave: "· quejas ·"}, 16)
	p := Pregunta{Texto: "¿de qué trata?", Kind: KindChoice, Estado: "x",
		Opciones: []Opcion{{ID: "quejas", Description: "r"}, {ID: "ventas", Description: "c"}}}
	r1, _ := l.Decidir(context.Background(), p)
	p.Opciones[0], p.Opciones[1] = p.Opciones[1], p.Opciones[0]
	r2, _ := l.Decidir(context.Background(), p)
	if r1.Answer != "quejas" || r2.Answer != "quejas" || l.Hits.Load() != 1 {
		t.Fatalf("%+v %+v hits=%d", r1, r2, l.Hits.Load())
	}
	// Misma pregunta y opciones con otra descripción: otra torre (HashEsquema de ESQUEMAS no distingue descripciones).
	if claveTorre("q", Opcion{ID: "a", Description: "x"}) == claveTorre("q", Opcion{ID: "a", Description: "y"}) {
		t.Fatal("la clave ignora la descripción")
	}
}
