package decide

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"log"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

const textoSecretoL3 = "mi-numero-de-tarjeta-4111-SECRETO"

// llmFalso es un servidor OpenAI-compatible: responde contenido (el content del mensaje) y apunta lo que recibe.
type llmFalso struct {
	contenido string
	estado    int
	espera    time.Duration
	llamadas  atomic.Int64
	ultima    atomic.Value // peticionL3
	auth      atomic.Value // string
	ruta      atomic.Value // string
}

func (f *llmFalso) arranca(t *testing.T) *httptest.Server {
	t.Helper()
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		f.llamadas.Add(1)
		f.ruta.Store(r.URL.Path)
		f.auth.Store(r.Header.Get("Authorization"))
		b, _ := io.ReadAll(r.Body)
		var pe peticionL3
		json.Unmarshal(b, &pe)
		f.ultima.Store(pe)
		if f.espera > 0 {
			select {
			case <-time.After(f.espera):
			case <-r.Context().Done():
				return
			}
		}
		if f.estado != 0 {
			http.Error(w, "boom "+textoSecretoL3, f.estado)
			return
		}
		json.NewEncoder(w).Encode(map[string]any{"choices": []any{map[string]any{"message": map[string]string{"role": "assistant", "content": f.contenido}}}})
	}))
	t.Cleanup(s.Close)
	return s
}

func nuevoL3Test(t *testing.T, s *httptest.Server, mod func(*ConfigL3)) (*L3LLM, *Metricas) {
	t.Helper()
	cfg := ConfigL3{URL: s.URL + "/v1/", Modelo: "qwen3:4b-instruct"}
	if mod != nil {
		mod(&cfg)
	}
	l, err := NuevoL3LLM(cfg, nil)
	if err != nil {
		t.Fatal(err)
	}
	m := NuevasMetricas()
	l.UsaMetricas(m)
	return l, m
}

func pregL3(kind string, ids ...string) Pregunta {
	p := Pregunta{ID: "q", Estado: textoSecretoL3, Texto: "¿qué quiere?", Kind: kind}
	for _, id := range ids {
		p.Opciones = append(p.Opciones, Opcion{ID: id, Description: "desc " + id})
	}
	return p
}

func cuentaL3(m *Metricas, r string) uint64 { return contador(&m.mu, m.l3Llamadas, r).Load() }

func TestL3Choice(t *testing.T) {
	f := &llmFalso{contenido: `{"probs":{"a":0.6,"b":0.3,"c":0.1}}`}
	l, m := nuevoL3Test(t, f.arranca(t), nil)
	r, err := l.Decidir(context.Background(), pregL3(KindChoice, "a", "b", "c"))
	if err != nil || r.Answer != "a" || absL3(r.Conf-0.6) > 1e-9 || absL3(r.Probs["b"]-0.3) > 1e-9 {
		t.Fatalf("r=%+v err=%v", r, err)
	}
	if f.ruta.Load() != "/v1/chat/completions" {
		t.Fatalf("ruta %v", f.ruta.Load())
	}
	pe := f.ultima.Load().(peticionL3)
	if pe.Model != "qwen3:4b-instruct" || pe.Temperature != 0 || pe.Stream || len(pe.Messages) != 2 || !strings.Contains(pe.Messages[1].Content, "desc b") {
		t.Fatalf("petición %+v", pe)
	}
	if cuentaL3(m, "ok") != 1 {
		t.Fatal("métrica ok")
	}
}

func TestL3ToleraVallasYTextoAlrededor(t *testing.T) {
	f := &llmFalso{contenido: "```json\n{\"probs\":{\"a\":0.2,\"b\":0.8}}\n```"}
	l, _ := nuevoL3Test(t, f.arranca(t), nil)
	r, _ := l.Decidir(context.Background(), pregL3(KindChoice, "a", "b"))
	if r.Answer != "b" {
		t.Fatalf("%+v", r)
	}
}

func TestL3Noul(t *testing.T) {
	f := &llmFalso{contenido: `{"probs":{"true":0.9,"false":0.1}}`}
	l, _ := nuevoL3Test(t, f.arranca(t), nil)
	r, err := l.Decidir(context.Background(), pregL3(KindNoul, "false", "true"))
	if err != nil || r.Answer != "true" || absL3(r.Conf-0.9) > 1e-9 {
		t.Fatalf("%+v %v", r, err)
	}
}

func TestL3ScoreMediana(t *testing.T) {
	f := &llmFalso{contenido: `{"probs":{"1":0.1,"2":0.2,"3":0.3,"4":0.4}}`}
	l, _ := nuevoL3Test(t, f.arranca(t), nil)
	r, _ := l.Decidir(context.Background(), pregL3(KindScore, "1", "2", "3", "4"))
	// acumulada 0,1 0,3 0,6 → mediana = nivel 3, como L1/L2 (no el modo, que sería 4)
	if r.Answer != "3" || absL3(r.Conf-0.3) > 1e-9 {
		t.Fatalf("%+v", r)
	}
}

func TestL3FaltantesNoOpina(t *testing.T) {
	f := &llmFalso{contenido: `{"probs":{"a":1}}`}
	l, _ := nuevoL3Test(t, f.arranca(t), nil)
	r, _ := l.Decidir(context.Background(), pregL3(KindChoice, "a", "b"))
	if r.Answer != "" || r.Conf != 0 { // R9 #1: faltar no es 0; no se renormaliza
		t.Fatalf("%+v", r)
	}
}

func TestL3RespuestaInvalidaNoOpina(t *testing.T) {
	malas := []string{
		``, `no es json`, `{"probs":{}}`, `{"probs":{"z":1}}`, `{"probs":{"a":-1,"b":2}}`, `{"probs":{"a":0,"b":0}}`,
		`{"probs":{"a":"alto"}}`, `{"respuesta":"a"}`, `{"probs":{"a":1e999}}`, `{"probs":{"a":1,"zz":1}}`, `{"probs":[0.5,0.5]}`,
	}
	for _, c := range malas {
		f := &llmFalso{contenido: c}
		l, m := nuevoL3Test(t, f.arranca(t), nil)
		r, err := l.Decidir(context.Background(), pregL3(KindChoice, "a", "b"))
		if err != nil || r.Conf != 0 || r.Answer != "" || r.Probs != nil {
			t.Errorf("%q: debió no opinar: %+v %v", c, r, err)
		}
		if cuentaL3(m, "invalida") != 1 {
			t.Errorf("%q: métrica invalida", c)
		}
	}
}

func TestL3CuerpoSinFormaDeChat(t *testing.T) {
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { io.WriteString(w, `{"choices":[]}`) }))
	defer s.Close()
	l, m := nuevoL3Test(t, s, nil)
	r, err := l.Decidir(context.Background(), pregL3(KindChoice, "a", "b"))
	if err != nil || r.Conf != 0 || cuentaL3(m, "invalida") != 1 {
		t.Fatalf("%+v %v", r, err)
	}
}

func TestL3Timeout(t *testing.T) {
	f := &llmFalso{contenido: `{"probs":{"a":1}}`, espera: 2 * time.Second}
	l, m := nuevoL3Test(t, f.arranca(t), func(c *ConfigL3) { c.Timeout = Duracion(50 * time.Millisecond) })
	t0 := time.Now()
	r, err := l.Decidir(context.Background(), pregL3(KindChoice, "a", "b"))
	if err == nil || r.Conf != 0 || time.Since(t0) > time.Second {
		t.Fatalf("%+v %v en %v", r, err, time.Since(t0))
	}
	if cuentaL3(m, "timeout") != 1 {
		t.Fatal("métrica timeout")
	}
	if strings.Contains(err.Error(), textoSecretoL3) {
		t.Fatal("el error lleva el texto del cliente")
	}
}

func TestL3ErrorHTTPNoFiltraTexto(t *testing.T) {
	f := &llmFalso{estado: 500}
	l, m := nuevoL3Test(t, f.arranca(t), nil)
	_, err := l.Decidir(context.Background(), pregL3(KindChoice, "a", "b"))
	if !errors.Is(err, errL3Estado) || strings.Contains(err.Error(), textoSecretoL3) || cuentaL3(m, "error") != 1 {
		t.Fatalf("%v", err)
	}
}

func TestL3PresupuestoPorPeticion(t *testing.T) {
	f := &llmFalso{contenido: `{"probs":{"a":1,"b":0}}`}
	l, m := nuevoL3Test(t, f.arranca(t), func(c *ConfigL3) { c.MaxPorPeticion = 2 })
	ctx := conPresupuesto(context.Background()) // una petición: todas sus preguntas comparten el tope
	var ops []float64
	for i := 0; i < 4; i++ {
		r, err := l.Decidir(ctx, pregL3(KindChoice, "a", "b"))
		if err != nil {
			t.Fatal(err)
		}
		ops = append(ops, r.Conf)
	}
	if ops[0] != 1 || ops[1] != 1 || ops[2] != 0 || ops[3] != 0 || f.llamadas.Load() != 2 || cuentaL3(m, "presupuesto") != 2 {
		t.Fatalf("conf=%v llamadas=%d presupuesto=%d", ops, f.llamadas.Load(), cuentaL3(m, "presupuesto"))
	}
	// otra petición, presupuesto nuevo
	if r, _ := l.Decidir(conPresupuesto(context.Background()), pregL3(KindChoice, "a", "b")); r.Conf != 1 {
		t.Fatal("la petición nueva debe tener presupuesto propio")
	}
}

func TestL3ClaveDeEntorno(t *testing.T) {
	t.Setenv("CHISPA_L3_CLAVE_TEST", "s3cret")
	f := &llmFalso{contenido: `{"probs":{"a":1}}`}
	l, _ := nuevoL3Test(t, f.arranca(t), func(c *ConfigL3) { c.APIKeyEnv = "CHISPA_L3_CLAVE_TEST" })
	l.Decidir(context.Background(), pregL3(KindChoice, "a", "b"))
	if f.auth.Load() != "Bearer s3cret" {
		t.Fatalf("auth %v", f.auth.Load())
	}
	if _, err := NuevoL3LLM(ConfigL3{URL: "http://x/v1", Modelo: "m", APIKeyEnv: "CHISPA_L3_NO_EXISTE"}, nil); err == nil {
		t.Fatal("variable vacía debe fallar")
	}
}

func TestL3NoRegistraElTexto(t *testing.T) {
	var buf bytes.Buffer
	log.SetOutput(&buf)
	defer log.SetOutput(io.Discard)
	for _, f := range []*llmFalso{{estado: 500}, {contenido: "basura"}, {contenido: `{"probs":{"a":1}}`}} {
		l, m := nuevoL3Test(t, f.arranca(t), nil)
		l.Decidir(context.Background(), pregL3(KindChoice, "a", "b"))
		var w bytes.Buffer
		m.Escribe(&w)
		if strings.Contains(w.String(), textoSecretoL3) || strings.Contains(buf.String(), textoSecretoL3) {
			t.Fatal("el texto del cliente aparece en logs o métricas")
		}
	}
}

func TestL3EnCascada(t *testing.T) {
	f := &llmFalso{contenido: `{"probs":{"a":0.1,"b":0.9}}`}
	srv := f.arranca(t)
	l3, _ := nuevoL3Test(t, srv, nil)
	c, met := cascadaFalsa(t, []float64{0.8, 0.6}, Stub{"L0"}, l3)
	res := c.Decidir(context.Background(), pregL3(KindChoice, "a", "b"))
	if res.Layer != "L3" || res.Escalate || res.Answer != "b" || absL3(res.Probs["b"]-0.9) > 1e-9 {
		t.Fatalf("%+v", res)
	}
	// por debajo de τ: escala, con la respuesta del LLM como pista
	f.contenido = `{"probs":{"a":0.45,"b":0.55}}`
	res = c.Decidir(context.Background(), pregL3(KindChoice, "a", "b"))
	if res.Layer != CapaEscalar || !res.Escalate || res.Answer != "b" {
		t.Fatalf("%+v", res)
	}
	// basura: L3 no opina, sigue escalada y queda Incompleto (R10-7: no se cachea bajo el nonce)
	f.contenido = "basura"
	res = c.Decidir(context.Background(), pregL3(KindChoice, "a", "b"))
	if res.Layer != CapaEscalar || !res.Escalate || res.Answer != "" || !res.Incompleto {
		t.Fatalf("%+v", res)
	}
	// fallo del endpoint: escala e Incompleto (no se cachea bajo nonce)
	f.estado = 503
	res = c.Decidir(context.Background(), pregL3(KindChoice, "a", "b"))
	if res.Layer != CapaEscalar || !res.Incompleto {
		t.Fatalf("%+v", res)
	}
	var w bytes.Buffer
	met.Escribe(&w)
	for _, s := range []string{`chispa_decididas_total{capa="L3"} 1`, `chispa_l3_llamadas_total{resultado="ok"} 2`, `chispa_l3_llamadas_total{resultado="invalida"} 1`, `chispa_l3_llamadas_total{resultado="error"} 1`, "chispa_l3_latencia_segundos_count 4"} {
		if !strings.Contains(w.String(), s) {
			t.Errorf("falta %q en /metrics", s)
		}
	}
}

func TestL3SoloVeLoEscalado(t *testing.T) {
	f := &llmFalso{contenido: `{"probs":{"a":1}}`}
	l3, _ := nuevoL3Test(t, f.arranca(t), nil)
	c, _ := cascadaFalsa(t, []float64{0.8, 0.6}, porPregunta{}, l3) // porPregunta contesta con 0,9
	if res := c.Decidir(context.Background(), pregL3(KindChoice, "a", "b")); res.Layer == "L3" {
		t.Fatalf("%+v", res)
	}
	if f.llamadas.Load() != 0 {
		t.Fatal("L3 se llamó con la pregunta ya resuelta")
	}
}

func TestL3ConfigApagadaPorDefecto(t *testing.T) {
	d, err := ConfigPorDefecto().DecisorL3()
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := d.(Stub); !ok {
		t.Fatalf("sin sección l3 debe ser el stub, es %T", d)
	}
}

func TestL3ConfigValidacion(t *testing.T) {
	ok := func(mod func(*Config)) error {
		c := ConfigPorDefecto()
		c.L3 = &ConfigL3{URL: "http://127.0.0.1:11434/v1", Modelo: "qwen3:4b-instruct"}
		mod(&c)
		return c.Validar()
	}
	if err := ok(func(*Config) {}); err != nil {
		t.Fatal(err)
	}
	mal := map[string]func(*Config){
		"url":      func(c *Config) { c.L3.URL = "ftp://x" },
		"urlvacia": func(c *Config) { c.L3.URL = "" },
		"modelo":   func(c *Config) { c.L3.Modelo = "" },
		"max":      func(c *Config) { c.L3.MaxPorPeticion = -1 },
		"tau":      func(c *Config) { v := 1.5; c.L3.Tau = &v },
		"sincapa":  func(c *Config) { c.Capas = c.Capas[:3] },
	}
	for n, m := range mal {
		if ok(m) == nil {
			t.Errorf("%s: debió fallar", n)
		}
	}
	// τ de l3 manda sobre el de la capa
	c := ConfigPorDefecto()
	v := 0.9
	c.L3 = &ConfigL3{URL: "http://h/v1", Modelo: "m", Tau: &v}
	if got := c.CapasEfectivas()[3].Tau; got != 0.9 || c.Capas[3].Tau != 0.60 {
		t.Fatalf("tau efectivo %v", got)
	}
}

func TestL3ConfigJSON(t *testing.T) {
	var c Config
	err := json.Unmarshal([]byte(`{"l3":{"url":"http://127.0.0.1:11434/v1","modelo":"qwen3:4b-instruct","api_key_env":"X","timeout":"3s","max_por_peticion":4,"tau":0.7}}`), &c)
	if err != nil || time.Duration(c.L3.Timeout) != 3*time.Second || c.L3.MaxPorPeticion != 4 || *c.L3.Tau != 0.7 {
		t.Fatalf("%+v %v", c.L3, err)
	}
	if json.Unmarshal([]byte(`{"l3":{"timeout":2.5}}`), &c) != nil || time.Duration(c.L3.Timeout) != 2500*time.Millisecond {
		t.Fatal("timeout numérico en segundos")
	}
	if json.Unmarshal([]byte(`{"l3":{"timeout":"nada"}}`), &c) == nil {
		t.Fatal("timeout inválido debe fallar")
	}
}

func absL3(x float64) float64 {
	if x < 0 {
		return -x
	}
	return x
}
