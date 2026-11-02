package decide

import (
	"context"
	"strings"
	"testing"
)

// ZY: una pregunta de 150 opciones nuevas opina con la config por defecto (antes: 150 > 64 ⇒ Incompleto para siempre).
func TestZY150OpcionesNuevasOpinan(t *testing.T) {
	enc := &codificadorContador{}
	l, m := l2Met(t, enc)
	c, err := NuevaCascada([]Capa{{Nombre: "L2", Tau: 0.0001}}, []Decisor{l}, m)
	if err != nil {
		t.Fatal(err)
	}
	r := c.Decidir(context.Background(), preguntaConOpciones(150))
	if r.Escalate && len(r.Probs) == 0 {
		t.Fatalf("150 opciones escalan sin probs: %+v", r)
	}
	if r.Incompleto || r.EscalateReason != "" && r.EscalateReason != MotivoBajaConfianza {
		t.Fatalf("%+v", r)
	}
	if len(r.Probs) != 150 || enc.n.Load() != 150 {
		t.Fatalf("probs=%d torres=%d", len(r.Probs), enc.n.Load())
	}
	// y el máximo permitido
	if r := c.Decidir(context.Background(), preguntaConOpciones(MaxOpciones)); r.Incompleto || len(r.Probs) != MaxOpciones {
		t.Fatalf("256 opciones: %+v", r)
	}
}

// ZY: con un presupuesto bajo escala con el motivo propio y la métrica; la caché hace que la siguiente petición acabe respondiendo.
func TestZYPresupuestoBajoMotivoYMetrica(t *testing.T) {
	enc := &codificadorContador{}
	l, m := l2Met(t, enc)
	l.ConMaxTorresNuevas(64)
	c, err := NuevaCascada([]Capa{{Nombre: "L2", Tau: 0.0001}}, []Decisor{l}, m)
	if err != nil {
		t.Fatal(err)
	}
	r := c.Decidir(context.Background(), preguntaConOpciones(150))
	if !r.Escalate || r.EscalateReason != MotivoSinPresupuestoTorres || len(r.Probs) != 0 {
		t.Fatalf("%+v", r)
	}
	var sb strings.Builder
	m.Escribe(&sb)
	if !strings.Contains(sb.String(), `chispa_capa_no_opina_total{capa="L2",causa="presupuesto_torres"} 1`) {
		t.Fatalf("falta la métrica:\n%s", sb.String())
	}
	if enc.n.Load() != 64 {
		t.Fatalf("torres cacheadas: %d", enc.n.Load())
	}
	for i := 0; i < 3 && r.Escalate && len(r.Probs) == 0; i++ { // 64 + 64 + 22
		r = c.Decidir(context.Background(), preguntaConOpciones(150))
	}
	if len(r.Probs) == 0 || enc.n.Load() != 150 {
		t.Fatalf("no avanzó: %+v torres=%d", r, enc.n.Load())
	}
}

// ZY: la protección contra peticiones gigantes sigue cortando (el tope es de toda la petición).
func TestZYPeticionGiganteSigueCortando(t *testing.T) {
	enc := &codificadorContador{}
	l, _ := l2Met(t, enc)
	ctx := conPresupuesto(context.Background())
	opinan := 0
	for i := 0; i < 20; i++ {
		p := preguntaConOpciones(100)
		p.Texto = strings.Repeat("x", i+1)
		if r, err := l.Decidir(ctx, p); err == nil && r.Conf > 0 {
			opinan++
		}
	}
	if n := enc.n.Load(); n > int64(MaxTorresNuevasPorDefecto) || opinan > 2 {
		t.Fatalf("torres=%d opinan=%d (tope %d)", n, opinan, MaxTorresNuevasPorDefecto)
	}
}
