package decide

import (
	"context"
	"os"
	"testing"
	"time"
)

// Prueba opcional de L3 contra un LLM OpenAI-compatible real (p. ej. Ollama). Sin CHISPA_L3_URL se salta.
// CHISPA_L3_MODELO es obligatoria; CHISPA_L3_API_KEY, opcional. Para medir latencia y exactitud usa server/l3/medir.sh.
func TestL3Real(t *testing.T) {
	url, modelo := os.Getenv("CHISPA_L3_URL"), os.Getenv("CHISPA_L3_MODELO")
	if url == "" {
		t.Skip("CHISPA_L3_URL sin definir: prueba contra un LLM real saltada")
	}
	if modelo == "" {
		t.Fatal("CHISPA_L3_URL está definida pero falta CHISPA_L3_MODELO")
	}
	cfg := ConfigL3{URL: url, Modelo: modelo, Timeout: Duracion(120 * time.Second)}
	if os.Getenv("CHISPA_L3_API_KEY") != "" {
		cfg.APIKeyEnv = "CHISPA_L3_API_KEY"
	}
	l, err := NuevoL3LLM(cfg, nil)
	if err != nil {
		t.Fatal(err)
	}
	casos := []struct {
		p    Pregunta
		want string
	}{
		{Pregunta{ID: "q1", Estado: "Me cobraron dos veces la misma factura este mes", Texto: "¿De qué trata el mensaje?", Kind: KindChoice,
			Opciones: []Opcion{{ID: "facturacion", Description: "cobros, facturas o pagos"}, {ID: "acceso", Description: "no puede entrar a su cuenta"}, {ID: "uso", Description: "duda de cómo usar el servicio"}}}, "facturacion"},
		{Pregunta{ID: "q2", Estado: "Alguien entró a mi cuenta y movió plata, ayúdenme ya", Texto: "¿Debe pasar a una persona?", Kind: KindNoul,
			Opciones: []Opcion{{ID: "false"}, {ID: "true"}}}, "true"},
	}
	ctx := context.Background()
	for _, c := range casos {
		t0 := time.Now()
		r, err := l.Decidir(ctx, c.p)
		if err != nil {
			t.Fatalf("%s: %v", c.p.ID, err)
		}
		t.Logf("%s: answer=%q probs=%v en %v", c.p.ID, r.Answer, r.Probs, time.Since(t0))
		if len(r.Probs) == 0 {
			t.Errorf("%s: L3 no opinó (respuesta del LLM no válida)", c.p.ID) // no se exige acertar: un modelo pequeño puede fallar
		} else if r.Answer != c.want {
			t.Logf("%s: aviso: esperaba %q", c.p.ID, c.want)
		}
	}
}
