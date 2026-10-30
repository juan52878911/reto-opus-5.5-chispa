//go:build ort

package decide

import (
	"context"
	"math"
	"os"
	"sync"
	"testing"

	"chispa/format/chispa3"
)

// Dorado de L2 con ORT real (ONNX sintético de consulta y de torre): se genera con
// `CHISPA_ORT_LIB=… go test -tags ort ./decide -run DoradosORT -regenerar` y se comprueba con 1e-6 (float32 y ORT; las sumas
// de ORT dependen del hilo/CPU). Sin la bandera solo compara.
const tolDoradoORT = 1e-6

func armarL2DoradoORT(t *testing.T) Decisor {
	l2onnx, err := os.ReadFile("testdata/l2_sintetico.onnx")
	if err != nil {
		t.Fatal(err)
	}
	torreonnx, err := os.ReadFile("../torre/testdata/sintetico.onnx")
	if err != nil {
		t.Fatal(err)
	}
	vec := make([]int8, 256)
	vec[0] = 1
	esq, err := chispa3.CodificarEsquemas(256, []chispa3.EntradaEsquema{ent("solo en ESQUEMAS", []string{"a"}, 1, vec...)})
	if err != nil {
		t.Fatal(err)
	}
	tr, err := chispa3.CodificarTORR(chispa3.Torre{Dim: 256, MaxLen: 128, Prefijo: "passage: ", ONNX: torreonnx})
	if err != nil {
		t.Fatal(err)
	}
	f := v3Tiny(t, calibDorada(), chispa3.Seccion{Tipo: chispa3.L2, Datos: l2onnx},
		chispa3.Seccion{Tipo: chispa3.ESQUEMAS, Datos: esq}, chispa3.Seccion{Tipo: chispa3.TORR, Datos: tr})
	cfg := Config{CacheEsquemas: 64}
	mt, err := ArmarDesde(f, NuevoL0(8), &cfg, false, tokORT{})
	if err != nil || len(mt.Avisos) != 0 {
		t.Fatalf("%v %v", err, mt.Avisos)
	}
	if _, ok := mt.L2.(*L2); !ok {
		t.Fatalf("L2 %T", mt.L2)
	}
	return mt.L2
}

func peticionesORT() []PeticionDorada {
	var ps []PeticionDorada
	for i, q := range []string{"¿Cuál es el motivo?", "¿Qué área atiende?"} {
		n := string(rune('a' + i))
		ps = append(ps,
			PeticionDorada{ID: "ort-choice-" + n, Capa: "L2", Estado: "hola", Pregunta: q, Kind: KindChoice, Opciones: []Opcion{{ID: "queja", Description: "se queja del cobro"}, {ID: "duda"}, {ID: "baja", Description: "quiere irse"}}},
			PeticionDorada{ID: "ort-noul-" + n, Capa: "L2", Estado: "hola", Pregunta: q, Kind: KindNoul, Opciones: []Opcion{{ID: "false"}, {ID: "true", Description: "urgente ya"}}},
			PeticionDorada{ID: "ort-score-" + n, Capa: "L2", Estado: "hola", Pregunta: q, Kind: KindScore, Opciones: []Opcion{{ID: "1"}, {ID: "2", Description: "media"}, {ID: "3", Description: "alta"}}},
			PeticionDorada{ID: "ort-multi-" + n, Capa: "L2", Estado: "hola", Pregunta: q, Kind: KindMulti, Opciones: opsMulti()})
	}
	return ps
}

func TestDoradosORT(t *testing.T) {
	l2 := armarL2DoradoORT(t)
	ps := peticionesORT()
	dec := func(p PeticionDorada) EsperadoDorado {
		r, err := l2.Decidir(context.Background(), p.pregunta())
		if err != nil {
			t.Fatalf("%s: %v", p.ID, err)
		}
		if r.Probs == nil {
			r.Probs = map[string]float64{}
		}
		return EsperadoDorado{Opina: r.Conf > 0, Answer: r.Answer, Answers: r.Answers, Conf: r.Conf, Probs: r.Probs}
	}
	if *regenerar {
		m := map[string]EsperadoDorado{}
		for _, p := range ps {
			m[p.ID] = dec(p)
		}
		escribirJSON(t, "ort.json", m)
	}
	var want map[string]EsperadoDorado
	leerJSON(t, "ort.json", &want)
	var peor float64
	nOpina := 0
	for _, p := range ps {
		g, w := dec(p), want[p.ID]
		if g.Opina != w.Opina || g.Answer != w.Answer || len(g.Probs) != len(w.Probs) {
			t.Errorf("%s: %s ≠ %s", p.ID, mustJSON(g), mustJSON(w))
			continue
		}
		peor = math.Max(peor, math.Abs(g.Conf-w.Conf))
		for k, v := range w.Probs {
			peor = math.Max(peor, math.Abs(g.Probs[k]-v))
		}
		if g.Opina {
			nOpina++
		}
	}
	if peor > tolDoradoORT || nOpina < 6 {
		t.Errorf("|Δ| máxima %g (tolerancia %g); opinan %d de %d", peor, tolDoradoORT, nOpina, len(ps))
	}
	// 64 goroutines sobre la misma sesión ORT: las mismas respuestas que una sola (ORT serializa los turnos).
	var wg sync.WaitGroup
	for g := 0; g < 64; g++ {
		wg.Add(1)
		go func(g int) {
			defer wg.Done()
			for k := range ps {
				p := ps[(k+g)%len(ps)]
				if x, w := dec(p), want[p.ID]; x.Answer != w.Answer || math.Abs(x.Conf-w.Conf) > tolDoradoORT {
					t.Errorf("%s: concurrente %s ≠ %s", p.ID, mustJSON(x), mustJSON(w))
				}
			}
		}(g)
	}
	wg.Wait()
	t.Logf("%d peticiones con ORT real, |Δ| máxima %.3g (tolerancia %g), opinan %d", len(ps), peor, tolDoradoORT, nOpina)
}
