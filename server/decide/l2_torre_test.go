package decide

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

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

// Un .chispa escrito por `chispa train --torre` (zero-shot, ONNX diminuto de dim 256; lo regenera
// `sdk/python/tests/fixture_torre.py`) monta las torres al vuelo con el tokenizador y el codificador falsos de estos tests.
func TestArmarDesdeFicheroDeChispaTrainTorre(t *testing.T) {
	f, err := chispa3.Abrir("../torre/testdata/torre_train.chispa")
	if err != nil {
		t.Fatal(err)
	}
	tr, err := f.Torre()
	if err != nil || tr.Dim != 256 || tr.MaxLen != 128 || tr.Prefijo != "passage: " || len(tr.ONNX) == 0 {
		t.Fatalf("%+v %v", tr, err)
	}
	enc := &codificadorPorTexto{clave: "· alta ·"}
	mt, err := ArmarDesde(f, NuevoL0(8), &Config{CacheEsquemas: 16}, false, tokFalso{}, ConSesionS(sesionFalsa{[][]float32{{3, 0}}}), ConCodificadorTorre(enc))
	if err != nil || len(mt.Avisos) != 0 {
		t.Fatalf("%v %v", err, mt.Avisos)
	}
	l2, ok := mt.L2.(*L2)
	if !ok || l2.torres == nil {
		t.Fatalf("L2 %T sin torres", mt.L2)
	}
}

// contador de pasadas del codificador, seguro para concurrencia.
type codificadorContador struct{ n atomic.Int64 }

func (c *codificadorContador) Torre(string) ([]float32, error) {
	c.n.Add(1)
	time.Sleep(time.Millisecond)
	return []float32{1, 0}, nil
}

func preguntaConOpciones(n int) Pregunta {
	ops := make([]Opcion, n)
	for i := range ops {
		ops[i] = Opcion{ID: fmt.Sprintf("o%d", i), Description: "d"}
	}
	return Pregunta{Texto: "¿q?", Kind: KindChoice, Estado: "x", Opciones: ops}
}

func l2Torres(t *testing.T, enc CodificadorTorre, cache int) *L2 {
	t.Helper()
	esq, _ := chispa3.DecodificarEsquemas(mustEsq(t))
	return NuevoL2Con(sesionFalsa{[][]float32{{3, 0}}}, esq, chispa3.Calib{}, tokFalso{}).ConTorres(enc, cache)
}

// Hallazgo 5: con ctx cancelado no se calcula ninguna torre.
func TestL2CtxCanceladoNoCalculaTorres(t *testing.T) {
	enc := &codificadorContador{}
	l := l2Torres(t, enc, 1024)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := l.Decidir(ctx, preguntaConOpciones(10)); err == nil || enc.n.Load() != 0 {
		t.Fatalf("err=%v torres=%d", err, enc.n.Load())
	}
}

// Hallazgo 5: por encima del tope de torres nuevas L2 no opina y no calcula nada.
func TestL2TopeTorresNuevas(t *testing.T) {
	enc := &codificadorContador{}
	l := l2Torres(t, enc, 1024).ConMaxTorresNuevas(8)
	r, err := l.Decidir(context.Background(), preguntaConOpciones(9))
	if err != nil || r.Conf != 0 || enc.n.Load() != 0 {
		t.Fatalf("%+v %v torres=%d", r, err, enc.n.Load())
	}
	if r, err = l.Decidir(context.Background(), preguntaConOpciones(8)); err != nil || r.Answer == "" || enc.n.Load() != 8 {
		t.Fatalf("%+v %v torres=%d", r, err, enc.n.Load())
	}
}

// Hallazgo 6: peticiones concurrentes del mismo esquema calculan cada torre una vez.
func TestL2Singleflight(t *testing.T) {
	enc := &codificadorContador{}
	l := l2Torres(t, enc, 1024)
	var wg sync.WaitGroup
	for g := 0; g < 16; g++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for e := 0; e < 20; e++ {
				p := preguntaConOpciones(2)
				p.Texto = fmt.Sprintf("esquema %d", e)
				if _, err := l.Decidir(context.Background(), p); err != nil {
					t.Error(err)
				}
			}
		}()
	}
	wg.Wait()
	if n := enc.n.Load(); n != 40 {
		t.Fatalf("%d pasadas, esperaba 40", n)
	}
}

// Hallazgo 7: TORR con otra dimensión que las ranuras de L2 → aviso al montar, sin torres.
func TestArmarDesdeTorreDimDistinta(t *testing.T) {
	esq, _ := chispa3.CodificarEsquemas(2, []chispa3.EntradaEsquema{ent("solo en ESQUEMAS", []string{"a"}, 1, 1, 0)})
	tr, _ := chispa3.CodificarTORR(chispa3.Torre{Dim: 3, MaxLen: 128, Prefijo: "passage: ", ONNX: []byte("x")})
	f := v3Tiny(t, calibTiny(), chispa3.Seccion{Tipo: chispa3.L2, Datos: []byte("onnx-l2")},
		chispa3.Seccion{Tipo: chispa3.ESQUEMAS, Datos: esq}, chispa3.Seccion{Tipo: chispa3.TORR, Datos: tr})
	mt, err := ArmarDesde(f, NuevoL0(8), &Config{CacheEsquemas: 8}, false, tokFalso{}, ConSesionS(sesionFalsa{[][]float32{{1, 0}}}), ConCodificadorTorre(&codificadorContador{}))
	if err != nil || mt.L2.(*L2).torres != nil || len(mt.Avisos) != 1 || !strings.Contains(mt.Avisos[0], "dimensión 3") {
		t.Fatalf("%v %v", err, mt.Avisos)
	}
}

// Hallazgo 4: prefijo de TORR distinto de «passage: » → aviso que nombra versión y prefijo; sin torres.
func TestArmarDesdeTorrePrefijoInvalido(t *testing.T) {
	esq, _ := chispa3.CodificarEsquemas(2, []chispa3.EntradaEsquema{ent("solo en ESQUEMAS", []string{"a"}, 1, 1, 0)})
	tr, _ := chispa3.CodificarTORR(chispa3.Torre{Dim: 2, MaxLen: 128, Prefijo: "query: ", ONNX: []byte("x")})
	f := v3Tiny(t, calibTiny(), chispa3.Seccion{Tipo: chispa3.L2, Datos: []byte("onnx-l2")},
		chispa3.Seccion{Tipo: chispa3.ESQUEMAS, Datos: esq}, chispa3.Seccion{Tipo: chispa3.TORR, Datos: tr})
	mt, err := ArmarDesde(f, NuevoL0(8), &Config{CacheEsquemas: 8}, false, tokFalso{}, ConSesionS(sesionFalsa{[][]float32{{1, 0}}}), ConCodificadorTorre(&codificadorContador{}))
	if err != nil || mt.L2.(*L2).torres != nil || len(mt.Avisos) != 1 || !strings.Contains(mt.Avisos[0], `TORR v1: prefijo "query: " no válido; se espera "passage: "`) {
		t.Fatalf("%v %v", err, mt.Avisos)
	}
}

// Hallazgo 13: cache_torres independiente de cache_esquemas (2000 torres caben con cache_esquemas=1024).
func TestCacheTorresPropia(t *testing.T) {
	c := ConfigPorDefecto()
	if c.CacheTorres < 16384 || c.MaxTorresNuevas != 64 {
		t.Fatalf("%+v", c)
	}
	enc := &codificadorContador{}
	l := l2Torres(t, enc, c.CacheTorres).ConMaxTorresNuevas(64)
	for vuelta := 0; vuelta < 2; vuelta++ {
		for e := 0; e < 100; e++ {
			p := preguntaConOpciones(20)
			p.Texto = fmt.Sprintf("e%d", e)
			l.Decidir(context.Background(), p)
		}
	}
	if enc.n.Load() != 2000 {
		t.Fatalf("%d pasadas, esperaba 2000", enc.n.Load())
	}
}
