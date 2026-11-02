package decide

import (
	"context"
	"strings"
	"testing"
)

func promptUsuarioL3(t *testing.T, ids ...string) string {
	t.Helper()
	f := &llmFalso{contenido: `{"probs":{"1":0.3,"2":0.4,"3":0.3}}`}
	l, _ := nuevoL3Test(t, f.arranca(t), nil)
	if _, err := l.Decidir(context.Background(), pregL3(KindScore, ids...)); err != nil {
		t.Fatal(err)
	}
	return f.ultima.Load().(peticionL3).Messages[1].Content
}

// H1: el prompt de score lista las opciones por nivel, sea cual sea el orden de la petición.
func TestXAPromptL3ScoreOrden(t *testing.T) {
	a := promptUsuarioL3(t, "1", "2", "3")
	b := promptUsuarioL3(t, "3", "1", "2")
	if a != b {
		t.Fatalf("el prompt depende del orden declarado:\n%s\n%s", a, b)
	}
	if !strings.Contains(a, `"id":"1"`) || strings.Index(a, `"id":"1"`) > strings.Index(a, `"id":"3"`) {
		t.Fatalf("opciones fuera de nivel: %s", a)
	}
}

// «01», «+1», huecos, 0..K-1 y ids no numéricos no son 1..K: opcionesNiveles no los acepta, en cualquier orden.
func TestXAIdsNoCanonicosNoSonNiveles(t *testing.T) {
	for _, ids := range [][]string{{"2", "01", "1"}, {"2", "+1", "1"}, {"01", "2", "3"}, {"0", "1", "2"}, {"1", "2", "4"}, {"bajo", "medio", "alto"}} {
		if got, ok := opcionesNiveles(pregL3(KindScore, ids...).Opciones); ok || got != nil {
			t.Fatalf("%v aceptado: %v", ids, got)
		}
	}
}

// En score la caché de nonce no distingue el orden de las opciones: 1..K en cualquier orden comparte entrada.
func TestXANonceScoreOrdenNoImporta(t *testing.T) {
	s, h, _ := servidorConClaves(t, nil)
	cuerpo := func(ids ...string) string {
		var ops []string
		for _, id := range ids {
			ops = append(ops, `{"id":"`+id+`"}`)
		}
		return `{"state":"s","questions":[{"id":"q","question":"¿?","kind":"score","nonce":"n1","options":[` + strings.Join(ops, ",") + `]}]}`
	}
	respuesta(t, h, cuerpo("1", "2", "3"))
	respuesta(t, h, cuerpo("3", "1", "2"))
	if n := s.Met.NonceHits.Load(); n != 1 {
		t.Fatalf("1..K en otro orden debe compartir caché (aciertos %d)", n)
	}
}

// L0: un modelo entrenado sobre ids que no son 1..K opina en choice y no en score; en score con 1..K sí opina (sin tocar el orden).
func TestScoreL0IdsNoUnoAKNoOpina(t *testing.T) {
	m, fx := cargarFixtureL0TF(t, "modelo.l0tf")
	l0 := NuevoL0(4)
	if err := l0.AnadirTF("tf", m); err != nil {
		t.Fatal(err)
	}
	ops := opcionesDe(fx.Etiquetas)
	q := func(k string) Pregunta {
		return Pregunta{Kind: k, Texto: "q", Opciones: ops, Estado: fx.Frases[1].Texto}
	}
	if r, _ := l0.Decidir(context.Background(), q(KindChoice)); r.Conf == 0 {
		t.Fatal("choice con esas etiquetas debía opinar")
	}
	if r, err := l0.Decidir(context.Background(), q(KindScore)); err != nil || r.Conf != 0 || r.Answer != "" {
		t.Fatalf("score con ids %v: %+v %v", fx.Etiquetas, r, err)
	}
}

// L3 no opina en score sin 1..K: ni llama al LLM ni gasta presupuesto. Con 1..K en cualquier orden sí.
func TestScoreL3IdsNoUnoAKNoLlama(t *testing.T) {
	f := &llmFalso{contenido: `{"probs":{"1":0.3,"2":0.4,"3":0.3}}`}
	l, mt := nuevoL3Test(t, f.arranca(t), nil)
	for _, ids := range [][]string{{"bajo", "medio", "alto"}, {"0", "1", "2"}, {"1", "2", "4"}, {"01", "2", "3"}} {
		if r, err := l.Decidir(context.Background(), pregL3(KindScore, ids...)); err != nil || r.Conf != 0 || r.Incompleto {
			t.Fatalf("%v: %+v %v", ids, r, err)
		}
	}
	if f.ultima.Load() != nil || cuentaL3(mt, "ok") != 0 {
		t.Fatal("L3 llamó al LLM con ids que no son 1..K")
	}
	if r, _ := l.Decidir(context.Background(), pregL3(KindScore, "2", "3", "1")); r.Conf == 0 || f.ultima.Load() == nil {
		t.Fatalf("1..K desordenado debía opinar: %+v", r)
	}
}

// Agregación de ventanas: score sin 1..K no opina aunque las ventanas traigan probs; con 1..K desordenado da la misma mediana.
func TestScoreAgregarRespuestasIdsNoUnoAK(t *testing.T) {
	probs := map[string]float64{"1": .45, "2": .1, "3": .45}
	rs := []Respuesta{{Answer: "1", Probs: probs, Conf: .45}, {Answer: "1", Probs: probs, Conf: .45}}
	if r := agregarRespuestas(Pregunta{Kind: KindScore, Opciones: opsWA([]string{"3", "1", "2"})}, rs, "media", .5); r.Answer != "2" {
		t.Fatalf("1..K: %+v", r)
	}
	for _, ids := range [][]string{{"bajo", "medio", "alto"}, {"0", "1", "2"}, {"1", "2", "4"}, {"01", "2", "3"}} {
		for n := 1; n <= 2; n++ { // con una sola ventana también
			if r := agregarRespuestas(Pregunta{Kind: KindScore, Opciones: opsWA(ids)}, rs[:n], "media", .5); r.Conf != 0 || r.Answer != "" {
				t.Fatalf("%v (%d): %+v", ids, n, r)
			}
		}
	}
}

// La cascada cuenta en chispa_score_ids_no_validos_total cada capa que no opinó por los ids; con 1..K no cuenta.
func TestScoreCascadaMetricaIdsNoValidos(t *testing.T) {
	casc, _ := cascadaTiny(t, calibTiny(), ConfigPorDefecto())
	q := Pregunta{ID: "n", Kind: KindScore, Texto: "¿Urgencia?", Estado: "paquete envio", Opciones: []Opcion{{ID: "bajo"}, {ID: "medio"}, {ID: "alto"}}}
	res := casc.Decidir(context.Background(), q)
	if !res.Escalate || res.Answer != "" {
		t.Fatalf("%+v", res)
	}
	for _, c := range []string{"L1", "L2"} {
		if n := contador(&casc.met.mu, casc.met.scoreIds, c).Load(); n != 1 {
			t.Fatalf("capa %s: %d, esperaba 1", c, n)
		}
	}
	var sb strings.Builder
	casc.met.Escribe(&sb)
	if !strings.Contains(sb.String(), `chispa_score_ids_no_validos_total{capa="L1"} 1`) {
		t.Fatalf("falta la serie en /metrics:\n%s", sb.String())
	}
	q.Opciones = nivelesScore()
	casc.Decidir(context.Background(), q)
	if n := contador(&casc.met.mu, casc.met.scoreIds, "L1").Load(); n != 1 {
		t.Fatalf("1..K contó: %d", n)
	}
}
