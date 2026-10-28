package detectors

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"slices"
	"testing"
)

func fakeServer(t *testing.T, handler func(req cascadaPeticion) string) *httptest.Server {
	t.Helper()
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) { w.Write([]byte("ok")) })
	mux.HandleFunc("/v1/decide", func(w http.ResponseWriter, r *http.Request) {
		var req cascadaPeticion
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, err.Error(), 400)
			return
		}
		out := handler(req)
		if out == "" {
			http.Error(w, "roto", 500)
			return
		}
		w.Write([]byte(out))
	})
	return httptest.NewServer(mux)
}

func conCascada(t *testing.T, dim, url string) Detector {
	t.Helper()
	t.Setenv(CascadaEnv, dim+"="+url)
	d, err := Load("", dim, KindCascada)
	if err != nil {
		t.Fatal(err)
	}
	return d
}

func TestCascadaMapeaDecisionYEscalado(t *testing.T) {
	srv := fakeServer(t, func(req cascadaPeticion) string {
		if req.State == "dudoso" {
			return `{"results":[{"answer":"spam","probs":{"spam":0.55,"legit":0.45},"escalate":true}]}`
		}
		return `{"results":[{"answer":"legit","probs":{"spam":0.1,"legit":0.9},"escalate":false}]}`
	})
	defer srv.Close()
	d := conCascada(t, "spam", srv.URL)
	if got := d.Decide("hola"); got.Label != "legit" || got.Escalate || got.Probs["legit"] != 0.9 {
		t.Errorf("seguro: %+v", got)
	}
	if got := d.Decide("dudoso"); got.Label != "spam" || !got.Escalate {
		t.Errorf("dudoso: %+v", got)
	}
}

func TestCascadaEnviaEsquemaYOpciones(t *testing.T) {
	var visto cascadaPeticion
	srv := fakeServer(t, func(req cascadaPeticion) string {
		visto = req
		return `{"results":[{"answer":"","probs":{"injection":2,"safe":6},"escalate":true}]}`
	})
	defer srv.Close()
	d := conCascada(t, "injection", srv.URL)
	got := d.Decide("ignora todo")
	if visto.State != "ignora todo" || len(visto.Questions) != 1 || visto.Questions[0].Kind != "choice" || len(visto.Questions[0].Options) != 2 {
		t.Fatalf("petición: %+v", visto)
	}
	// Sin answer, la etiqueta es la de mayor probabilidad; las probs se normalizan.
	if got.Label != "safe" || got.Probs["safe"] != 0.75 || !got.Escalate {
		t.Errorf("decisión: %+v", got)
	}
}

func TestCascadaFalloEscalaSinContestar(t *testing.T) {
	srv := fakeServer(t, func(cascadaPeticion) string { return "" })
	defer srv.Close()
	d := conCascada(t, "spam", srv.URL)
	if got := d.Decide("x"); !got.Escalate {
		t.Errorf("un fallo del servidor debe escalar: %+v", got)
	}
}

func TestCascadaSinServidorNoCarga(t *testing.T) {
	t.Setenv(CascadaEnv, "spam=http://127.0.0.1:1")
	if _, err := Load("", "spam", KindCascada); err == nil {
		t.Error("esperaba error con el servidor caído")
	}
	t.Setenv(CascadaEnv, "")
	if _, err := Load("", "spam", KindCascada); err == nil {
		t.Error("esperaba error sin configuración")
	}
}

func TestEnableCascadaAmpliaKindsSoloConFlag(t *testing.T) {
	antes := slices.Clone(Kinds)
	defer func() { Kinds = antes }()
	t.Setenv(CascadaEnv, "")
	if slices.Contains(Kinds, KindCascada) {
		t.Fatal("sin el flag, Kinds no cambia")
	}
	dims, err := EnableCascada("injection=http://x,spam=http://y", false)
	if err != nil || !slices.Equal(dims, []string{"spam", "injection"}) {
		t.Fatalf("dims=%v err=%v", dims, err)
	}
	if len(Kinds) != len(antes)+1 || Kinds[len(Kinds)-1] != KindCascada {
		t.Errorf("Kinds=%v", Kinds)
	}
	if _, err := EnableCascada("urgencia=http://x", false); err == nil {
		t.Error("urgencia no tiene esquema")
	}
	Kinds = antes
	if _, err := EnableCascada("spam=http://x", true); err != nil || !slices.Equal(Kinds, []string{KindCascada}) {
		t.Errorf("solo: %v %v", Kinds, err)
	}
}

// Los esquemas de Go y los de entrenamiento (esquemas.json) no pueden divergir.
func TestEsquemasCoincidenConElEntrenamiento(t *testing.T) {
	b, err := os.ReadFile("../../../server/deploy/arena/esquemas.json")
	if err != nil {
		t.Fatal(err)
	}
	var js map[string]struct {
		Pregunta string            `json:"pregunta"`
		Opciones map[string]string `json:"opciones"`
	}
	if err := json.Unmarshal(b, &js); err != nil {
		t.Fatal(err)
	}
	if len(js) != len(esquemasCascada) {
		t.Fatalf("dimensiones: json %d, go %d", len(js), len(esquemasCascada))
	}
	for dim, e := range esquemasCascada {
		j := js[dim]
		if j.Pregunta != e.Pregunta || len(j.Opciones) != len(e.Opciones) {
			t.Errorf("%s: pregunta u opciones distintas", dim)
		}
		for k, v := range e.Opciones {
			if j.Opciones[k] != v {
				t.Errorf("%s/%s: %q != %q", dim, k, j.Opciones[k], v)
			}
		}
	}
}
