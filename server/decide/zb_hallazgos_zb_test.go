package decide

import (
	"bytes"
	"context"
	"errors"
	"log"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"chispa/format/chispa3"
)

func configZB(t *testing.T, cuerpo string) (Config, error) {
	t.Helper()
	p := filepath.Join(t.TempDir(), "c.json")
	if err := os.WriteFile(p, []byte(cuerpo), 0o600); err != nil {
		t.Fatal(err)
	}
	return CargarConfig(p)
}

// ZB-3: torres_por_segundo es una clave de la config (antes: «unknown field»), con defecto distinto de 0 y 0 = sin tope.
func TestZBConfigTorresPorSegundo(t *testing.T) {
	base := `{"capas":[{"nombre":"L1","tau":0.5}],"modelos":[]`
	c, err := configZB(t, base+`,"torres_por_segundo":50}`)
	if err != nil || c.TorresPorSegundo != 50 {
		t.Fatalf("%v %v", c.TorresPorSegundo, err)
	}
	if c, err = configZB(t, base+`}`); err != nil || c.TorresPorSegundo != TorresPorSegundoPorDefecto || c.TorresPorSegundo <= 0 {
		t.Fatalf("defecto %v %v", c.TorresPorSegundo, err)
	}
	if c, err = configZB(t, base+`,"torres_por_segundo":0}`); err != nil || c.TorresPorSegundo != 0 {
		t.Fatalf("0 = sin tope: %v %v", c.TorresPorSegundo, err)
	}
	if _, err = configZB(t, base+`,"torres_por_segundo":-1}`); err == nil || !strings.Contains(err.Error(), "torres_por_segundo") {
		t.Fatalf("negativo: %v", err)
	}
}

func armarTorreZB(t *testing.T, meta, texto string, cfg Config) Montaje {
	t.Helper()
	f := conTorreSeccion(t)
	secs := []chispa3.Seccion{{Tipo: chispa3.META, Datos: []byte(meta)}}
	for _, tp := range []chispa3.Tipo{chispa3.L2, chispa3.ESQUEMAS} {
		d, _ := f.Bytes(tp)
		secs = append(secs, chispa3.Seccion{Tipo: tp, Datos: d})
	}
	tr, err := chispa3.CodificarTORR(chispa3.Torre{Dim: 2, MaxLen: 128, Prefijo: "passage: ", TextoTorre: texto, ONNX: []byte("onnx-torre")})
	if err != nil {
		t.Fatal(err)
	}
	secs = append(secs, chispa3.Seccion{Tipo: chispa3.TORR, Datos: tr})
	mt, err := ArmarDesde(v3Tiny(t, calibTiny(), secs...), NuevoL0(8), &cfg, false, tokFalso{}, ConSesionS(sesionFalsa{[][]float32{{3, 0}}}), ConCodificadorTorre(&codificadorPorTexto{clave: "x"}))
	if err != nil {
		t.Fatal(err)
	}
	return mt
}

// ZB-3: al montar las torres se aplica cfg.TorresPorSegundo y el tope corta con sin_presupuesto_torres.
func TestZBArranqueAplicaTorresPorSegundo(t *testing.T) {
	mt := armarTorreZB(t, `{"version":1}`, chispa3.TextoTorreV1, Config{CacheEsquemas: 64, TorresPorSegundo: 2})
	l2 := mt.L2.(*L2)
	if l2.cuboTasa != 2 {
		t.Fatalf("cuboTasa %v, quería 2", l2.cuboTasa)
	}
	m := NuevasMetricas()
	c, err := NuevaCascada([]Capa{{Nombre: "L2", Tau: 0.0001}}, []Decisor{mt.L2}, m)
	if err != nil {
		t.Fatal(err)
	}
	r := c.Decidir(context.Background(), preguntaConOpciones(6))
	if !r.Escalate || r.EscalateReason != MotivoSinPresupuestoTorres {
		t.Fatalf("el tope no cortó: %+v", r)
	}
	// Sin tope (0) la misma pregunta opina.
	mt0 := armarTorreZB(t, `{"version":1}`, chispa3.TextoTorreV1, Config{CacheEsquemas: 64})
	if mt0.L2.(*L2).cuboTasa != 0 {
		t.Fatalf("cuboTasa %v, quería 0", mt0.L2.(*L2).cuboTasa)
	}
	c0, _ := NuevaCascada([]Capa{{Nombre: "L2", Tau: 0.0001}}, []Decisor{mt0.L2}, NuevasMetricas())
	if r := c0.Decidir(context.Background(), preguntaConOpciones(6)); r.Incompleto || len(r.Probs) == 0 {
		t.Fatalf("sin tope: %+v", r)
	}
}

// ZB-4: carga degradada: aviso en Avisos y en el log, /healthz con el motivo y gauge en /metrics (se reinicia al cargar otro modelo).
func TestZBCargaDegradadaHealthzMetricaLog(t *testing.T) {
	var buf bytes.Buffer
	log.SetOutput(&buf)
	defer log.SetOutput(os.Stderr)
	mt := armarTorreZB(t, `{"version":1,"texto_torre":"v2_sin_id"}`, chispa3.TextoTorreV1, Config{CacheEsquemas: 64})
	if !strings.Contains(buf.String(), "texto_torre_inconsistente") || !strings.Contains(strings.Join(mt.Avisos, "\n"), "texto_torre_inconsistente") {
		t.Fatalf("log %q avisos %q", buf.String(), mt.Avisos)
	}
	met := NuevasMetricas()
	c, err := NuevaCascada([]Capa{{Nombre: "L2", Tau: 0.5}}, []Decisor{mt.L2}, met)
	if err != nil {
		t.Fatal(err)
	}
	rec := httptest.NewRecorder()
	NuevoServidor(c, met, 8).Handler().ServeHTTP(rec, httptest.NewRequest("GET", "/healthz", nil))
	if b := rec.Body.String(); !strings.Contains(b, `"torre_al_vuelo":false`) || !strings.Contains(b, `"torre_al_vuelo_motivo":"texto_torre_inconsistente"`) {
		t.Fatal(b)
	}
	var sb strings.Builder
	met.Escribe(&sb)
	if !strings.Contains(sb.String(), `chispa_torre_al_vuelo_desactivada{motivo="texto_torre_inconsistente"} 1`) {
		t.Fatalf("métrica:\n%s", sb.String())
	}
	// Un modelo coherente apaga el gauge y no trae motivo.
	ok := armarTorreZB(t, `{"version":1}`, chispa3.TextoTorreV1, Config{CacheEsquemas: 64})
	c2, _ := NuevaCascada([]Capa{{Nombre: "L2", Tau: 0.5}}, []Decisor{ok.L2}, met)
	sb.Reset()
	met.Escribe(&sb)
	if !strings.Contains(sb.String(), `chispa_torre_al_vuelo_desactivada{motivo="texto_torre_inconsistente"} 0`) || c2.Capacidades().TorreAlVueloMotivo != "" || !c2.Capacidades().TorreAlVuelo {
		t.Fatalf("modelo coherente:\n%s %+v", sb.String(), c2.Capacidades())
	}
	if len(ok.Avisos) != 0 {
		t.Fatalf("avisos de un modelo coherente: %q", ok.Avisos)
	}
}

// ZB-9: si otra capa falló por error o plazo, el motivo es «incompleta» aunque L2 se quedara sin presupuesto de torres.
func TestZBPrioridadIncompletaSobreSinPresupuesto(t *testing.T) {
	p := Pregunta{ID: "q", Kind: KindChoice, Texto: "x", Opciones: []Opcion{{ID: "a"}, {ID: "b"}}}
	sinPres := &falso{n: "L2", r: Respuesta{Incompleto: true, SinPresupuestoTorres: true}}
	for nombre, otra := range map[string]*falso{
		"error":             {n: "L3", err: errors.New("boom")},
		"plazo":             {n: "L3", err: context.DeadlineExceeded},
		"incompleta propia": {n: "L3", r: Respuesta{Incompleto: true}},
	} {
		r := cascadaDe(t, NuevasMetricas(), sinPres, otra).Decidir(context.Background(), p)
		if !r.Escalate || r.EscalateReason != MotivoIncompleta {
			t.Errorf("%s: %+v", nombre, r)
		}
	}
	// Solo el presupuesto: sigue siendo sin_presupuesto_torres.
	ok := &falso{n: "L3", r: Respuesta{}}
	if r := cascadaDe(t, NuevasMetricas(), sinPres, ok).Decidir(context.Background(), p); r.EscalateReason != MotivoSinPresupuestoTorres {
		t.Errorf("solo presupuesto: %+v", r)
	}
}
