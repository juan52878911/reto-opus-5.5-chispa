package decide

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
)

// R10 #2: sin presupuesto de torres nuevas, L2 escala como Incompleto (no se cachea bajo el nonce).
func TestR10L2PresupuestoAgotadoEsIncompleto(t *testing.T) {
	l, m := l2Met(t, &codificadorContador{})
	l.ConMaxTorresNuevas(4)
	c, err := NuevaCascada([]Capa{{Nombre: "L2", Tau: 0.6}}, []Decisor{l}, m)
	if err != nil {
		t.Fatal(err)
	}
	r := c.Decidir(context.Background(), preguntaConOpciones(5))
	if !r.Escalate || !r.Incompleto {
		t.Fatalf("sin presupuesto debe escalar como Incompleto: %+v", r)
	}
}

// R10 #7: salida de L3 inválida o 2xx sin choices → Incompleto, no una escalada cacheable.
func TestR10L3SalidaInvalidaEsIncompleto(t *testing.T) {
	f := &llmFalso{contenido: `{"probs":{"a":0.9`} // truncado
	l, _ := nuevoL3Test(t, f.arranca(t), nil)
	if r, err := l.Decidir(context.Background(), pregL3(KindChoice, "a", "b")); err != nil || !r.Incompleto {
		t.Fatalf("JSON inválido: %+v err=%v", r, err)
	}
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.Write([]byte(`{}`)) }))
	defer s.Close()
	l2, _ := nuevoL3Test(t, s, nil)
	if r, err := l2.Decidir(context.Background(), pregL3(KindChoice, "a", "b")); err != nil || !r.Incompleto {
		t.Fatalf("sin choices: %+v err=%v", r, err)
	}
}
