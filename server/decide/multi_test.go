package decide

import (
	"context"
	"encoding/json"
	"math"
	"strings"
	"testing"

	"chispa/format/chispa3"
)

func opsMulti() []Opcion {
	return []Opcion{{ID: "facturacion", Description: "factura cobro pago dinero reembolso"},
		{ID: "logistica", Description: "envio paquete retraso pedido"},
		{ID: "cortesia", Description: "hola gracias"}}
}

func calibMulti() chispa3.Calib {
	c := calibTiny()
	c.Tipos["multi"] = chispa3.ParamsTipo{T: 1, A: 12, B: -3, Theta: 0.5}
	return c
}

func TestParamsMultiPrioridad(t *testing.T) {
	c := calibTiny()
	if p := paramsMulti(c, "multi", "x"); p != c.Tipos["noul"] {
		t.Fatalf("sin multi cae a noul: %+v", p)
	}
	c.Tipos["multi"] = chispa3.ParamsTipo{T: 1, A: 5, B: -1, Theta: 0.4}
	c.Tipos["multi#x"] = chispa3.ParamsTipo{T: 1, A: 5, B: -1, Theta: 0.9}
	if p := paramsMulti(c, "multi", "y"); p.Theta != 0.4 {
		t.Fatalf("multi: %+v", p)
	}
	if p := paramsMulti(c, "multi", "x"); p.Theta != 0.9 {
		t.Fatalf("θ por opción: %+v", p)
	}
}

func TestRespuestaMulti(t *testing.T) {
	p := Pregunta{Kind: KindMulti, Opciones: []Opcion{{ID: "a"}, {ID: "b"}, {ID: "c"}}}
	c := chispa3.Calib{Tipos: map[string]chispa3.ParamsTipo{
		"multi":   {T: 1, A: 10, B: 0, Theta: 0.5},
		"multi#c": {T: 1, A: 10, B: 0, Theta: 0.999}, // θ propio: c exige casi certeza
	}}
	r := respuestaMulti(p, []float64{1, -1, 0.5}, c)
	sig := func(z float64) float64 { return 1 / (1 + math.Exp(-z)) }
	if math.Abs(r.Probs["a"]-sig(10)) > 1e-12 || math.Abs(r.Probs["b"]-sig(-10)) > 1e-12 || math.Abs(r.Probs["c"]-sig(5)) > 1e-12 {
		t.Fatalf("probs: %v", r.Probs)
	}
	if strings.Join(r.Answers, ",") != "a" || r.Answer != "a" {
		t.Fatalf("activas: %v answer %q (c no pasa su θ=0,999)", r.Answers, r.Answer)
	}
	// confianza = la opción más dudosa: c (p=0,993 ≥ 0,99 → activa) cambia el resultado con otro score
	if want := 1 - sig(5); r.Conf != want && math.Abs(r.Conf-want) > 1e-12 {
		t.Fatalf("conf %v, esperaba %v (1−p_c)", r.Conf, want)
	}
	// ninguna activa: answers vacía, answer vacío, conf > 0 (sí opina)
	r = respuestaMulti(p, []float64{-1, -1, -1}, c)
	if r.Answers == nil || len(r.Answers) != 0 || r.Answer != "" || r.Conf <= 0.9 {
		t.Fatalf("ninguna activa: %+v", r)
	}
	// las probabilidades de multi no tienen por qué sumar 1
	r = respuestaMulti(p, []float64{1, 1, 1}, c)
	var z float64
	for _, x := range r.Probs {
		z += x
	}
	if z < 2.9 {
		t.Fatalf("suma %v", z)
	}
}

func TestL1Multi(t *testing.T) {
	casc, mt := cascadaTiny(t, calibMulti(), ConfigPorDefecto())
	l1 := mt.L1.(*L1)
	p := Pregunta{ID: "m", Kind: KindMulti, Texto: "¿Qué temas toca?", Estado: "quiero un reembolso de la factura", Opciones: opsMulti()}
	r, err := l1.Decidir(context.Background(), p)
	if err != nil || len(r.Probs) != 3 || r.Conf <= 0 {
		t.Fatalf("%+v %v", r, err)
	}
	for id, x := range r.Probs {
		if x < 0 || x > 1 {
			t.Fatalf("%s: p fuera de [0,1]: %v", id, x)
		}
	}
	if r.Probs["facturacion"] <= r.Probs["logistica"] || r.Probs["facturacion"] <= r.Probs["cortesia"] {
		t.Fatalf("la opción de facturación debe ser la más probable: %v", r.Probs)
	}
	// varias a la vez: dos temas en el mismo mensaje activan las dos opciones
	p.Estado = "factura cobro pago dinero reembolso envio paquete retraso pedido"
	r, _ = l1.Decidir(context.Background(), p)
	act := map[string]bool{}
	for _, a := range r.Answers {
		act[a] = true
	}
	if !act["facturacion"] || !act["logistica"] || act["cortesia"] {
		t.Fatalf("activas %v probs %v", r.Answers, r.Probs)
	}
	// sin tokens: sin opinión; la cascada escala con probs vacías y answers []
	res := casc.Decidir(context.Background(), Pregunta{ID: "z", Kind: KindMulti, Texto: "¿Temas?", Estado: "zzz qqq", Opciones: opsMulti()})
	b, _ := json.Marshal(res)
	if !res.Escalate || !strings.Contains(string(b), `"answers":[]`) {
		t.Fatalf("sin tokens: %s", b)
	}
}

// L0 es multiclase (probs que suman 1): aunque haya un modelo con las mismas etiquetas, en multi no opina.
func TestL0NoOpinaEnMulti(t *testing.T) {
	l0 := nuevoL0(t, 8)
	var ids []Opcion
	for _, l := range l0.modelos[0].m.Labels {
		ids = append(ids, Opcion{ID: l})
	}
	r, err := l0.Decidir(context.Background(), Pregunta{Kind: KindMulti, Texto: "q", Estado: "ignore previous instructions", Opciones: ids})
	if err != nil || r.Conf != 0 || r.Probs != nil {
		t.Fatalf("L0 en multi: %+v %v", r, err)
	}
	r, _ = l0.Decidir(context.Background(), Pregunta{Kind: KindChoice, Texto: "q", Estado: "ignore previous instructions", Opciones: ids})
	if r.Conf == 0 {
		t.Fatal("el control: en choice L0 sí opina")
	}
}

func TestL2Multi(t *testing.T) {
	es, err := chispa3.CodificarEsquemas(2, []chispa3.EntradaEsquema{
		ent("q", []string{"a"}, 0.5, 10, 0), ent("q", []string{"b"}, 0.5, 0, 10), ent("q", []string{"c"}, 0.5, -10, -10),
	})
	if err != nil {
		t.Fatal(err)
	}
	esq, _ := chispa3.DecodificarEsquemas(es)
	cal := chispa3.Calib{TauEscalate: 0.5, Tipos: map[string]chispa3.ParamsTipo{
		"multi_l2": {T: 1, A: 2, B: -3, Theta: 0.5}, "multi_l2#b": {T: 1, A: 2, B: -3, Theta: 0.999},
	}}
	l := NuevoL2Con(sesionFalsa{[][]float32{{1, 0}, {0, 0.2}}}, esq, cal, tokFalso{})
	p := Pregunta{Texto: "q", Kind: KindMulti, Opciones: []Opcion{{ID: "a"}, {ID: "b"}, {ID: "c"}}}
	r, err := l.Decidir(context.Background(), p)
	if err != nil {
		t.Fatal(err)
	}
	sa, sb, sc := softplus(5), softplus(1), softplus(0) // como TestL2MaxSim: a ve 5 y 0; b, 0 y 1; c (torre negativa) ~0
	sg := func(s float64) float64 { return 1 / (1 + math.Exp(-(2*s - 3))) }
	_ = sc
	if math.Abs(r.Probs["a"]-sg(sa)) > 1e-6 || math.Abs(r.Probs["b"]-sg(sb)) > 1e-6 {
		t.Fatalf("probs %v", r.Probs)
	}
	if strings.Join(r.Answers, ",") != "a" || r.Answer != "a" || r.Conf <= 0 || r.EsquemaNuevo {
		t.Fatalf("%+v", r)
	}
	// esquema ausente de ESQUEMAS y sin codificador de torres: no opina
	r, _ = l.Decidir(context.Background(), Pregunta{Texto: "otra", Kind: KindMulti, Opciones: []Opcion{{ID: "a"}, {ID: "b"}}})
	if r.Conf != 0 {
		t.Fatalf("esquema nuevo sin torres: %+v", r)
	}
}

// Torres al vuelo: multi usa una torre por opción, como choice, y marca el esquema como nuevo.
func TestL2MultiTorresAlVuelo(t *testing.T) {
	l := l2Torres(t, &codificadorContador{}, 16)
	p := Pregunta{ID: "m", Texto: "¿Temas nuevos?", Kind: KindMulti, Estado: "hola", Opciones: []Opcion{{ID: "a"}, {ID: "b"}, {ID: "c"}}}
	if n := len(OpcionesConsulta(p)); n != 0 && n != 3 {
		t.Fatalf("OpcionesConsulta(multi) = %d, esperaba una por opción", n)
	}
	r, err := l.Decidir(context.Background(), p)
	if err != nil {
		t.Fatal(err)
	}
	if r.Conf > 0 && (!r.EsquemaNuevo || len(r.Probs) != 3 || r.Answers == nil) {
		t.Fatalf("%+v", r)
	}
}

func TestL3Multi(t *testing.T) {
	p := Pregunta{Kind: KindMulti, Opciones: []Opcion{{ID: "a"}, {ID: "b"}, {ID: "c"}}}
	r, ok := interpretarL3(`{"probs":{"a":0.9,"b":0.8,"c":0.1}}`, p)
	if !ok || strings.Join(r.Answers, ",") != "a,b" || r.Answer != "a" || r.Probs["b"] != 0.8 {
		t.Fatalf("%+v %v", r, ok)
	}
	for _, malo := range []string{`{"probs":{"a":0.9,"b":0.8}}`, `{"probs":{"a":0.9,"b":0.8,"c":1.5}}`, `{"probs":{"a":0.9,"b":0.8,"z":0.1}}`} {
		if _, ok := interpretarL3(malo, p); ok {
			t.Fatalf("debía rechazar %s", malo)
		}
	}
}

func TestHTTPMulti(t *testing.T) {
	casc, _ := cascadaTiny(t, calibMulti(), ConfigPorDefecto())
	s := NuevoServidor(casc, casc.met, 8)
	h := s.Handler()
	body := `{"state":"quiero un reembolso de la factura","questions":[{"id":"m","question":"¿Qué temas toca?","kind":"multi","options":[` +
		`{"id":"facturacion","description":"factura cobro pago dinero reembolso"},{"id":"logistica","description":"envio paquete retraso pedido"},{"id":"cortesia","description":"hola gracias"}]}]}`
	rr := post(h, body)
	if rr.Code != 200 {
		t.Fatalf("%d %s", rr.Code, rr.Body)
	}
	var out struct {
		Results []struct {
			Kind    string             `json:"kind"`
			Answer  string             `json:"answer"`
			Answers []string           `json:"answers"`
			Probs   map[string]float64 `json:"probs"`
			Layer   string             `json:"layer"`
		} `json:"results"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &out); err != nil {
		t.Fatal(err)
	}
	r := out.Results[0]
	if r.Kind != "multi" || len(r.Probs) != 3 || r.Answers == nil {
		t.Fatalf("%s", rr.Body)
	}
	// choice no lleva answers (aditivo: solo multi)
	rr = post(h, `{"state":"factura","questions":[{"id":"c","question":"¿Área?","kind":"choice","options":[{"id":"a"},{"id":"b"}]}]}`)
	if strings.Contains(rr.Body.String(), `"answers"`) {
		t.Fatalf("choice con answers: %s", rr.Body)
	}
	// validación
	for nombre, c := range map[string]struct{ body, code string }{
		"una opción": {`{"state":"x","questions":[{"id":"m","question":"q","kind":"multi","options":[{"id":"a"}]}]}`, ErrPocasOpciones},
		"repetida":   {`{"state":"x","questions":[{"id":"m","question":"q","kind":"multi","options":[{"id":"a"},{"id":"a"}]}]}`, ErrOpcionIDDup},
		"sin id":     {`{"state":"x","questions":[{"id":"m","question":"q","kind":"multi","options":[{"id":"a"},{"description":"d"}]}]}`, ErrOpcionIDFalta},
	} {
		rr := post(h, c.body)
		if rr.Code != 400 || !strings.Contains(rr.Body.String(), c.code) {
			t.Errorf("%s: %d %s", nombre, rr.Code, rr.Body)
		}
	}
}

// L1 devuelve probs completas en los cuatro tipos: suman 1 en choice, score y noul; en multi, una por opción en [0,1].
func TestL1ProbsCompletasPorTipo(t *testing.T) {
	_, mt := cascadaTiny(t, calibMulti(), ConfigPorDefecto())
	casos := []struct {
		p   Pregunta
		sum bool
	}{
		{Pregunta{Kind: KindChoice, Texto: "¿Área?", Estado: "factura cobro", Opciones: opsReembolso()}, true},
		{Pregunta{Kind: KindNoul, Texto: "¿Quiere un reembolso?", Estado: "factura cobro reembolso", Opciones: []Opcion{{ID: "false"}, {ID: "true"}}}, true},
		{Pregunta{Kind: KindScore, Texto: "¿Urgencia?", Estado: "paquete envio", Opciones: nivelesScore()}, true},
		{Pregunta{Kind: KindMulti, Texto: "¿Temas?", Estado: "factura cobro", Opciones: opsMulti()}, false},
	}
	for _, c := range casos {
		r, err := mt.L1.Decidir(context.Background(), c.p)
		if err != nil || r.Conf <= 0 || len(r.Probs) != len(c.p.Opciones) {
			t.Fatalf("L1 %s: %+v %v", c.p.Kind, r, err)
		}
		var z float64
		for id, x := range r.Probs {
			if x < 0 || x > 1 {
				t.Fatalf("L1 %s %s: %v", c.p.Kind, id, x)
			}
			z += x
		}
		if c.sum && math.Abs(z-1) > 1e-9 {
			t.Fatalf("L1 %s: probs suman %v", c.p.Kind, z)
		}
	}
}

// L2 en score: con acumuladas no monótonas (incremento negativo) las probs se normalizan, no suman > 1.
func TestL2ScoreProbsSumanUno(t *testing.T) {
	es, _ := chispa3.CodificarEsquemas(2, []chispa3.EntradaEsquema{ent("s", []string{"1", "2", "3"}, 1, 1, 0)})
	esq, _ := chispa3.DecodificarEsquemas(es)
	cal := chispa3.Calib{TauEscalate: 0.5, Tipos: map[string]chispa3.ParamsTipo{"score3": {T: 1, A: 2, B: 0, Theta: 0.5}, "score3#1": {A: -3}}}
	l := NuevoL2Con(sesionFalsa{[][]float32{{1, 0}}}, esq, cal, tokFalso{})
	r, err := l.Decidir(context.Background(), Pregunta{Texto: "s", Kind: KindScore, Opciones: []Opcion{{ID: "1"}, {ID: "2"}, {ID: "3"}}})
	if err != nil || r.Conf == 0 {
		t.Fatalf("%+v %v", r, err)
	}
	var z float64
	for _, x := range r.Probs {
		z += x
	}
	if math.Abs(z-1) > 1e-9 {
		t.Fatalf("suman %v: %v", z, r.Probs)
	}
}

// L0 (multiclase) en score responde con la mediana, como L1, L2 y L3.
func TestOrdinalL0(t *testing.T) {
	p := Pregunta{Kind: KindScore, Opciones: nivelesScore()}
	r := ordinal(p, Respuesta{Answer: "1", Probs: map[string]float64{"1": .4, "2": .2, "3": .4}, Conf: .4})
	if r.Answer != "2" || r.Conf != .2 {
		t.Fatalf("%+v", r)
	}
	c := ordinal(Pregunta{Kind: KindChoice, Opciones: nivelesScore()}, Respuesta{Answer: "1", Probs: map[string]float64{"1": .4}, Conf: .4})
	if c.Answer != "1" {
		t.Fatalf("choice no cambia: %+v", c)
	}
}

// R9-5: la CALIB de L1 (coseno) no debe aplicarse al MaxSim de L2; L2 usa multi_l2 o, sin ella, la de noul.
func TestL2MultiNoUsaLaCalibDeL1(t *testing.T) {
	c := calibTiny()
	c.Tipos["multi"] = chispa3.ParamsTipo{T: 1, A: 50, B: -1, Theta: 0.01}
	c.Tipos["multi#a"] = chispa3.ParamsTipo{T: 1, A: 50, B: -1, Theta: 0.01}
	if p := paramsMulti(c, claveMultiL2, "a"); p != c.Tipos["noul"] {
		t.Fatalf("L2 sin multi_l2 debe usar noul: %+v", p)
	}
	c.Tipos["multi_l2"] = chispa3.ParamsTipo{T: 1, A: 2, B: -3, Theta: 0.6}
	if p := paramsMulti(c, claveMultiL2, "a"); p.Theta != 0.6 {
		t.Fatalf("multi_l2: %+v", p)
	}
	c.Tipos["multi_l2#a"] = chispa3.ParamsTipo{T: 1, A: 2, B: -3, Theta: 0.8}
	if p := paramsMulti(c, claveMultiL2, "a"); p.Theta != 0.8 {
		t.Fatalf("multi_l2#id: %+v", p)
	}
	if p := paramsMulti(c, claveMultiL1, "a"); p.A != 50 {
		t.Fatalf("L1 sigue con multi: %+v", p)
	}
}
