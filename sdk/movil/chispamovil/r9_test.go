package chispamovil

import (
	"encoding/json"
	"strings"
	"testing"

	"chispa/format/chispa3"
)

func esqDosOpciones(t *testing.T) *Chispa {
	t.Helper()
	b, err := chispa3.CodificarEsquemas(4, []chispa3.EntradaEsquema{
		{Hash: chispa3.HashEsquema("¿Qué quiere?", []string{"compra"}), Escala: 0.1, Vec: []int8{100, 0, 0, 0}},
		{Hash: chispa3.HashEsquema("¿Qué quiere?", []string{"baja"}), Escala: 0.1, Vec: []int8{0, 100, 0, 0}},
	})
	if err != nil {
		t.Fatal(err)
	}
	esq, err := chispa3.DecodificarEsquemas(b)
	if err != nil {
		t.Fatal(err)
	}
	return &Chispa{esq: esq, tieneL2: true, calib: calibTorre()}
}

// R9 #4: la marca de «esquema nuevo» sale del motor y mira solo ESQUEMAS, no la caché de torres al vuelo.
func TestL2MarcaEsquemaNuevoSoloPorESQUEMAS(t *testing.T) {
	c := esqDosOpciones(t)
	conocida := `{"question":"¿Qué quiere?","kind":"choice","options":[{"id":"compra"},{"id":"baja"}]}`
	nueva := preguntasTorre[0]
	nuevaOtroOrden := `{"question":"¿Cuál es el motivo?","kind":"choice","options":[{"id":"baja","description":"quiere irse"},{"id":"queja","description":"se queja del cobro"},{"id":"duda"}]}`

	r := leer(t, c.PuntuarL2(conocida, ranuras(ranurasTorre...), 2))
	if !r.Opina || r.EsquemaNuevo || !c.EsquemaEnEsquemas(conocida) {
		t.Fatalf("esquema de ESQUEMAS no es nuevo: %+v", r)
	}
	if c.EsquemaEnEsquemas(nueva) {
		t.Fatal("esquema ausente de ESQUEMAS")
	}
	var textos []string
	json.Unmarshal([]byte(c.TextosTorreL2(nueva)), &textos)
	if !c.InstalarTorresL2(nueva, torresBytes(textos), len(textos)) {
		t.Fatal("instalar")
	}
	// Con las torres ya cacheadas (y con otro orden de opciones, otro JSON) sigue siendo esquema nuevo.
	for _, q := range []string{nueva, nuevaOtroOrden} {
		if !c.TorresL2(q) {
			t.Fatalf("debía haber torres cacheadas: %s", q)
		}
		r := leer(t, c.PuntuarL2(q, ranuras(ranurasTorre...), 2))
		if !r.Opina || !r.EsquemaNuevo || c.EsquemaEnEsquemas(q) {
			t.Fatalf("%s: esquema_nuevo debía ser true: %+v", q, r)
		}
	}
	if !strings.Contains(c.PuntuarL2(nueva, ranuras(ranurasTorre...), 2), `"esquema_nuevo":true`) {
		t.Fatal("la marca no sale en el JSON")
	}
}

// R9 #5: en L2 multi no valen las cabezas «multi» (cosenos de L1): L2 usa «multi_l2#id» y «multi_l2», y sin ellas la de «noul» (como el servidor).
func TestMultiL2UsaCabezasPropias(t *testing.T) {
	q := `{"question":"¿Temas?","kind":"multi","options":[{"id":"a"},{"id":"b"},{"id":"c"}]}`
	c := movilL2(t)
	var textos []string
	json.Unmarshal([]byte(c.TextosTorreL2(q)), &textos)
	if !c.InstalarTorresL2(q, torresBytes(textos), len(textos)) {
		t.Fatal("instalar")
	}
	l1 := chispa3.ParamsTipo{T: 1, A: 12, B: -3, Theta: 0.5}
	c.calib.Tipos["multi"], c.calib.Tipos["multi#a"] = l1, l1
	// R10-5: sin multi_l2 L2 no opina en multi (ni usa la cabeza de L1 ni la de noul)
	c.calib.Tipos["noul"] = chispa3.ParamsTipo{T: 1, A: 0, B: -50, Theta: 0.5}
	if r := leer(t, c.PuntuarL2(q, ranuras(ranurasTorre...), 2)); !r.Ok || r.Opina || len(r.Probs) != 0 {
		t.Fatalf("sin multi_l2 L2 no debe opinar: %+v", r)
	}
	// a·s+b = +50 → activa; −50 → inactiva (b de ellas sobreescribe por opción)
	c.calib.Tipos["multi_l2"] = chispa3.ParamsTipo{A: 0, B: 50, Theta: 0.5}
	c.calib.Tipos["multi_l2#b"] = chispa3.ParamsTipo{A: 0, B: -50, Theta: 0.5}
	var r struct {
		Opina   bool     `json:"opina"`
		Answers []string `json:"answers"`
	}
	if err := json.Unmarshal([]byte(c.PuntuarL2(q, ranuras(ranurasTorre...), 2)), &r); err != nil || !r.Opina || strings.Join(r.Answers, ",") != "a,c" {
		t.Fatalf("multi_l2: %+v %v", r, err)
	}
	// L1 sigue con «multi»
	if got := c.multi(pregunta{Kind: "multi", Opciones: []opcion{{ID: "a"}, {ID: "b"}}}, []float64{1, 1}); strings.Join(got.Answers, ",") != "a,b" {
		t.Fatalf("L1: %+v", got)
	}
}

// R9 #11: 0x1d/0x1e/0x1f en pregunta, ids y descripciones se rechazan (HashEsquema2 no lleva prefijos de longitud).
func TestRechazaSeparadoresDeClave(t *testing.T) {
	c := movilL2(t)
	for nombre, q := range map[string]string{
		"pregunta":    `{"question":"a\u001db","kind":"choice","options":[{"id":"a"},{"id":"b"}]}`,
		"id":          `{"question":"q","kind":"choice","options":[{"id":"a\u001f"},{"id":"b"}]}`,
		"descripción": `{"question":"q","kind":"choice","options":[{"id":"a","description":"x\u001db\u001ey"},{"id":"b"}]}`,
	} {
		for _, f := range []func(string) string{
			func(s string) string { return c.PuntuarL2(s, nil, 0) },
			func(s string) string { return c.Decidir("x", s) }, func(s string) string { return c.DecidirL0("x", s) },
		} {
			r := leer(t, f(q))
			if r.Ok || !strings.Contains(r.Error, "invalid_characters") {
				t.Errorf("%s: debía rechazarse: %+v", nombre, r)
			}
		}
	}
	if r := leer(t, c.PuntuarL2(preguntasTorre[0], ranuras(ranurasTorre...), 2)); strings.Contains(r.Error, "invalid_characters") {
		t.Fatal("pregunta normal rechazada")
	}
}
