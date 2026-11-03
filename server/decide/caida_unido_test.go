package decide

import (
	"context"
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"testing"

	"chispa/format/chispa3"
)

// Equivalencia de Caída: las tres preguntas few-shot (colocacion, riesgo, completa), cada una con su L0 entrenado con el
// entrenador Go sobre ejemplos de demos/caida/entrenar_fewshot (n=60), se sirven (i) como «-modelo» base + «modelos» de tres
// ficheros y (ii) como un único .chispa unido (L0MULTI). Mismas respuestas en los 30 turnos de testdata/caida/turnos.json.
//
// Los fixtures se regeneran con la receta de testdata/caida/README.md.
func turnosCaida(t *testing.T) []Pregunta {
	t.Helper()
	b, err := os.ReadFile("../testdata/caida/turnos.json")
	if err != nil {
		t.Fatal(err)
	}
	var raw []struct {
		Pregunta
		Estado string `json:"estado"`
	}
	if err := json.Unmarshal(b, &raw); err != nil {
		t.Fatal(err)
	}
	out := make([]Pregunta, len(raw))
	for i, r := range raw {
		out[i] = r.Pregunta
		out[i].Estado = r.Estado
	}
	return out
}

func rutasCaida() []string {
	var rs []string
	for _, q := range []string{"colocacion", "riesgo", "completa"} {
		rs = append(rs, filepath.Join("..", "testdata", "caida", q+".chispa"))
	}
	return rs
}

func cascadaCaida(t *testing.T, f *chispa3.Fichero, l0 *L0) *Cascada {
	t.Helper()
	cfg := ConfigPorDefecto()
	mt, err := ArmarDesde(f, l0, &cfg, false, nil)
	if err != nil {
		t.Fatal(err)
	}
	casc, err := NuevaCascada(cfg.Capas, []Decisor{l0, mt.L1, mt.L2, NuevoL3()}, NuevasMetricas())
	if err != nil {
		t.Fatal(err)
	}
	return casc
}

// unido arma el fichero del cliente como lo hace «mkmodelo -unir»: las secciones del base, salvo sus L0, y los L0 de todos.
func unidoCaida(t *testing.T, base *chispa3.Fichero) *chispa3.Fichero {
	t.Helper()
	var secs []chispa3.Seccion
	es, err := base.EntradasL0("base")
	if err != nil {
		t.Fatal(err)
	}
	for _, tp := range base.Tipos() {
		if tp == chispa3.L0 || tp == chispa3.L0TF || tp == chispa3.L0MULTI {
			continue
		}
		b, err := base.Bytes(tp)
		if err != nil {
			t.Fatal(err)
		}
		secs = append(secs, chispa3.Seccion{Tipo: tp, Datos: b})
	}
	for _, r := range rutasCaida() {
		b, err := os.ReadFile(r)
		if err != nil {
			t.Fatal(err)
		}
		f, err := chispa3.Desde(b, chispa3.Limites{})
		if err != nil {
			t.Fatal(err)
		}
		e, err := f.EntradasL0(filepath.Base(r))
		if err != nil {
			t.Fatal(err)
		}
		es = append(es, e...)
	}
	s0, err := chispa3.SeccionesL0(es)
	if err != nil || len(s0) != 1 || s0[0].Tipo != chispa3.L0MULTI {
		t.Fatalf("unión: %v %v", s0, err)
	}
	secs = append(secs, s0...)
	return escribirYAbrir(t, secs)
}

func TestCaidaUnidoEquivaleAModelos(t *testing.T) {
	// (i) -modelo base + modelos de tres ficheros
	l0a := NuevoL0(64)
	if err := l0a.Cargar(rutasCaida()...); err != nil {
		t.Fatal(err)
	}
	base := v3Tiny(t, calibTiny())
	ca := cascadaCaida(t, base, l0a)
	// (ii) un solo fichero unido
	l0b := NuevoL0(64)
	cb := cascadaCaida(t, unidoCaida(t, v3Tiny(t, calibTiny())), l0b)
	if l0a.NumModelos() != 4 || l0b.NumModelos() != 4 {
		t.Fatalf("modelos en L0: %d y %d (se esperan 4: injection del base + 3 de Caída)", l0a.NumModelos(), l0b.NumModelos())
	}
	turnos := turnosCaida(t)
	if len(turnos) < 20 {
		t.Fatalf("turnos: %d", len(turnos))
	}
	enL0 := map[string]int{}
	for i, p := range turnos {
		ra, rb := ca.Decidir(context.Background(), p), cb.Decidir(context.Background(), p)
		if ra.Answer != rb.Answer || ra.Layer != rb.Layer || ra.Escalate != rb.Escalate || ra.EscalateReason != rb.EscalateReason || len(ra.Probs) != len(rb.Probs) {
			t.Fatalf("turno %d (%s): %+v frente a %+v", i, p.ID, ra, rb)
		}
		for k, v := range ra.Probs {
			if w, ok := rb.Probs[k]; !ok || math.Abs(v-w) > 1e-6 {
				t.Fatalf("turno %d (%s) prob %q: %v frente a %v", i, p.ID, k, v, w)
			}
		}
		// y el L0 solo, también donde la cascada escala (colocacion): mismas probabilidades
		da, _ := l0a.Decidir(context.Background(), p)
		db, _ := l0b.Decidir(context.Background(), p)
		if da.Answer == "" || da.Answer != db.Answer || len(da.Probs) != len(db.Probs) {
			t.Fatalf("turno %d (%s): L0 %+v frente a %+v", i, p.ID, da, db)
		}
		for k, v := range da.Probs {
			if math.Abs(v-db.Probs[k]) > 1e-6 {
				t.Fatalf("turno %d (%s) L0 prob %q: %v frente a %v", i, p.ID, k, v, db.Probs[k])
			}
		}
		if ra.Layer == "L0" {
			enL0[p.ID]++
		}
	}
	// que la comparación diga algo: L0 contesta en alguna de cada pregunta que no sea el hueco noul/score ya escalado
	if enL0["colocacion"] == 0 && enL0["riesgo"] == 0 && enL0["completa"] == 0 {
		t.Fatalf("L0 no contestó ningún turno: la equivalencia no prueba nada")
	}
	t.Logf("%d turnos iguales; respuestas de L0 por pregunta: %v", len(turnos), enL0)
}
