package chispamovil

import (
	"bytes"
	"encoding/binary"
	"encoding/json"
	"hash/fnv"
	"math"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"chispa/format/chispa3"
)

// falso es un embebedor de bolsa de palabras con hash a 16 dimensiones, unitario; determinista y sin modelo.
type falso struct{}

func (falso) Dim() int { return 16 }
func (falso) Embed(t string, out []float32) bool {
	for i := range out {
		out[i] = 0
	}
	n := 0
	for _, w := range strings.Fields(strings.ToLower(t)) {
		h := fnv.New32a()
		h.Write([]byte(w))
		out[h.Sum32()%16]++
		n++
	}
	if n == 0 {
		return false
	}
	var s float64
	for _, x := range out {
		s += float64(x) * float64(x)
	}
	for i := range out {
		out[i] /= float32(math.Sqrt(s))
	}
	return true
}

const preguntaCompra = `{"question":"¿Qué quiere?","kind":"choice","options":[
 {"id":"compra","description":"quiere comprar un producto"},{"id":"soporte","description":"pide ayuda con algo"}]}`

func conFalso() *Chispa { return &Chispa{e: falso{}, cache: map[string][][]float32{}} }

func leer(t *testing.T, js string) respuesta {
	t.Helper()
	var r respuesta
	if err := json.Unmarshal([]byte(js), &r); err != nil {
		t.Fatalf("no es JSON: %v: %s", err, js)
	}
	return r
}

func TestDecidirChoice(t *testing.T) {
	c := conFalso()
	r := leer(t, c.Decidir("quiero comprar un producto", preguntaCompra))
	if !r.Ok || !r.Opina || r.Answer != "compra" {
		t.Fatalf("respuesta inesperada: %+v", r)
	}
	var z float64
	for _, p := range r.Probs {
		z += p
	}
	if math.Abs(z-1) > 1e-9 || r.Conf != r.Probs["compra"] {
		t.Fatalf("probs %v suman %v, conf %v", r.Probs, z, r.Conf)
	}
	// la caché de torres no cambia el resultado
	if r2 := c.Decidir("quiero comprar un producto", preguntaCompra); r2 != c.Decidir("quiero comprar un producto", preguntaCompra) || leer(t, r2).Conf != r.Conf {
		t.Fatal("la segunda llamada difiere")
	}
}

func TestDecidirTemperaturaDeCalib(t *testing.T) {
	a, b := conFalso(), conFalso()
	b.calib = chispa3.Calib{TauEscalate: 0.5, Tipos: map[string]chispa3.ParamsTipo{"choice": {T: 1, A: 1, B: 0, Theta: 0.5}}}
	ra := leer(t, a.Decidir("ayuda con algo", preguntaCompra))
	rb := leer(t, b.Decidir("ayuda con algo", preguntaCompra))
	if ra.Answer != rb.Answer || !(rb.Conf < ra.Conf) {
		t.Fatalf("T=1 debía ablandar la confianza: %v frente a %v", rb.Conf, ra.Conf)
	}
}

func TestDecidirSinOpinionYErrores(t *testing.T) {
	c := conFalso()
	if r := leer(t, c.Decidir("   ", preguntaCompra)); !r.Ok || r.Opina || r.Conf != 0 {
		t.Fatalf("sin tokens debía no opinar: %+v", r)
	}
	score := `{"question":"q","kind":"score","options":[{"id":"1"},{"id":"2"}]}`
	if r := leer(t, c.Decidir("   ", score)); !r.Ok || r.Opina {
		t.Fatalf("score sin tokens no opina: %+v", r)
	}
	for _, mal := range []string{`no es json`, `{"question":"q","options":[]}`, `{"question":"q","kind":"raro","options":[{"id":"a"}]}`} {
		if r := leer(t, c.Decidir("hola", mal)); r.Ok || r.Error == "" {
			t.Fatalf("debía fallar con %q: %+v", mal, r)
		}
	}
	if r := leer(t, (&Chispa{}).Decidir("hola", preguntaCompra)); r.Ok {
		t.Fatal("sin L1 debía fallar")
	}
}

func TestDecidirNoul(t *testing.T) {
	c := conFalso()
	q := `{"question":"¿es urgente?","kind":"noul","options":[{"id":"true","description":"urgente ya"},{"id":"false"}]}`
	r := leer(t, c.Decidir("urgente ya", q))
	if !r.Ok || !r.Opina || (r.Answer != "true" && r.Answer != "false") || math.Abs(r.Probs["true"]+r.Probs["false"]-1) > 1e-9 {
		t.Fatalf("noul: %+v", r)
	}
}

// esquemasDePrueba arma ESQUEMAS con una torre por opción de la pregunta de compra (dim 4).
func esquemasDePrueba(t *testing.T) *chispa3.Esquemas {
	t.Helper()
	b, err := chispa3.CodificarEsquemas(4, []chispa3.EntradaEsquema{
		{Hash: chispa3.HashEsquema("¿Qué quiere?", []string{"compra"}), Escala: 0.1, Vec: []int8{100, 0, 0, 0}},
		{Hash: chispa3.HashEsquema("¿Qué quiere?", []string{"soporte"}), Escala: 0.1, Vec: []int8{0, 100, 0, 0}},
		{Hash: chispa3.HashEsquema("¿urgente?", []string{"false", "true"}), Escala: 0.1, Vec: []int8{0, 0, 100, 0}},
	})
	if err != nil {
		t.Fatal(err)
	}
	e, err := chispa3.DecodificarEsquemas(b)
	if err != nil {
		t.Fatal(err)
	}
	return e
}

func ranuras(vs ...[]float32) []byte {
	var b []byte
	for _, v := range vs {
		for _, x := range v {
			b = binary.LittleEndian.AppendUint32(b, math.Float32bits(x))
		}
	}
	return b
}

func TestPuntuarL2Choice(t *testing.T) {
	c := &Chispa{esq: esquemasDePrueba(t), tieneL2: true}
	if !c.TorresL2(preguntaCompraL2) {
		t.Fatal("debía haber torres")
	}
	// dos ranuras: la segunda apunta a «soporte»
	r := leer(t, c.PuntuarL2(preguntaCompraL2, ranuras([]float32{0, 0, 0, 1}, []float32{0, 3, 0, 0}), 2))
	if !r.Ok || !r.Opina || r.Answer != "soporte" {
		t.Fatalf("L2: %+v", r)
	}
	// a mano: MaxSim(soporte) = softplus(100·3·0.1) = 30, MaxSim(compra) = softplus(0) = ln2; T = 0,05 → conf ≈ 1
	if r.Conf < 0.999 {
		t.Fatalf("conf %v", r.Conf)
	}
	if r := leer(t, c.PuntuarL2(preguntaCompraL2, ranuras([]float32{1, 0, 0, 0}), 1)); r.Answer != "compra" {
		t.Fatalf("debía ser compra: %+v", r)
	}
}

const preguntaCompraL2 = `{"question":"¿Qué quiere?","kind":"choice","options":[{"id":"compra"},{"id":"soporte"}]}`

func TestPuntuarL2SinTorresYForma(t *testing.T) {
	c := &Chispa{esq: esquemasDePrueba(t), tieneL2: true}
	otra := `{"question":"otra","kind":"choice","options":[{"id":"a"},{"id":"b"}]}`
	if c.TorresL2(otra) {
		t.Fatal("no debía haber torres")
	}
	if r := leer(t, c.PuntuarL2(otra, nil, 0)); !r.Ok || r.Opina {
		t.Fatalf("sin torres no opina: %+v", r)
	}
	if r := leer(t, c.PuntuarL2(preguntaCompraL2, make([]byte, 7), 1)); r.Ok {
		t.Fatal("forma mala debía fallar")
	}
	if r := leer(t, (&Chispa{}).PuntuarL2(preguntaCompraL2, nil, 1)); r.Ok {
		t.Fatal("sin L2 debía fallar")
	}
}

func TestPuntuarL2NoulYScore(t *testing.T) {
	calib := chispa3.Calib{TauEscalate: 0.4, Tipos: map[string]chispa3.ParamsTipo{
		"noul":     {T: 1, A: 2, B: -1, Theta: 0.5},
		"score3":   {T: 1, A: 1, B: 0, Theta: 0.5},
		"score3#2": {T: 1, A: 1, B: 0, Theta: 0.5},
	}}
	c := &Chispa{esq: esquemasDePrueba(t), tieneL2: true, calib: calib}
	q := `{"question":"¿urgente?","kind":"noul","options":[{"id":"true"},{"id":"false"}]}`
	r := leer(t, c.PuntuarL2(q, ranuras([]float32{0, 0, 1, 0}), 1))
	// s = softplus(100·1·0,1) ≈ 10; z = 2·10 − 1 → P(true) ≈ 1
	if !r.Ok || r.Answer != "true" || r.Conf < 0.999 {
		t.Fatalf("noul: %+v", r)
	}
	// score sin torre registrada → sin opinión (no hay torre para ese esquema)
	sc := `{"question":"¿urgente?","kind":"score","options":[{"id":"1"},{"id":"2"},{"id":"3"}]}`
	if r := leer(t, c.PuntuarL2(sc, ranuras([]float32{0, 0, 1, 0}), 1)); !r.Ok || r.Opina {
		t.Fatalf("score: %+v", r)
	}
}

func TestScoreCoral(t *testing.T) {
	c := &Chispa{calib: chispa3.Calib{Tipos: map[string]chispa3.ParamsTipo{
		"score3": {T: 1, A: 2, B: 1, Theta: .5}, "score3#2": {T: 1, A: 1, B: 0, Theta: .5}}}}
	p := pregunta{Kind: "score", Opciones: []opcion{{ID: "1"}, {ID: "2"}, {ID: "3"}}}
	r := c.score(p, 3)
	s1 := 1 / (1 + math.Exp(-(2*3 - 1))) // P(y>1)
	s2 := 1 / (1 + math.Exp(-(2*3 - 2))) // b2 = 1 + a(score3#2) = 2
	if math.Abs(r.Probs["1"]-(1-s1)) > 1e-12 || math.Abs(r.Probs["2"]-(s1-s2)) > 1e-12 || math.Abs(r.Probs["3"]-s2) > 1e-12 {
		t.Fatalf("CORAL: %+v", r.Probs)
	}
	p.Opciones[0].ID = "x"
	if c.score(p, 3).Opina {
		t.Fatal("ids que no son 1..K no opinan")
	}
}

// ---- ficheros .chispa v3 ----

func escribirV3(t *testing.T, secs []chispa3.Seccion) string {
	t.Helper()
	var buf bytes.Buffer
	if err := chispa3.Escribir(&buf, secs); err != nil {
		t.Fatal(err)
	}
	ruta := filepath.Join(t.TempDir(), "m.chispa")
	if err := os.WriteFile(ruta, buf.Bytes(), 0o600); err != nil {
		t.Fatal(err)
	}
	return ruta
}

func metaYCalib(t *testing.T) []chispa3.Seccion {
	meta, err := chispa3.Meta{Version: 1, Tareas: []string{"x"}, Licencias: map[string]string{"x": "MIT"},
		Dorado: strings.Repeat("0", 64)}.Codificar()
	if err != nil {
		t.Fatal(err)
	}
	calib, err := chispa3.Calib{TauEscalate: 0.42, Tipos: map[string]chispa3.ParamsTipo{"choice": {T: 0.1, A: 1, B: 0, Theta: .5}}}.Codificar()
	if err != nil {
		t.Fatal(err)
	}
	return []chispa3.Seccion{{Tipo: chispa3.META, Datos: meta}, {Tipo: chispa3.CALIB, Datos: calib}}
}

func TestAbrirSoloCalibYL2(t *testing.T) {
	esq, err := chispa3.CodificarEsquemas(4, []chispa3.EntradaEsquema{
		{Hash: chispa3.HashEsquema("¿Qué quiere?", []string{"compra"}), Escala: 0.1, Vec: []int8{100, 0, 0, 0}},
		{Hash: chispa3.HashEsquema("¿Qué quiere?", []string{"soporte"}), Escala: 0.1, Vec: []int8{0, 100, 0, 0}},
	})
	if err != nil {
		t.Fatal(err)
	}
	secs := append(metaYCalib(t), chispa3.Seccion{Tipo: chispa3.L2, Datos: []byte("ONNX-falso")}, chispa3.Seccion{Tipo: chispa3.ESQUEMAS, Datos: esq})
	c, err := Abrir(escribirV3(t, secs))
	if err != nil {
		t.Fatal(err)
	}
	defer c.Cerrar()
	if c.Capas() != `["L2"]` || !c.TieneCalib() || math.Abs(c.TauEscalate()-0.42) > 1e-12 {
		t.Fatalf("capas %s tau %v", c.Capas(), c.TauEscalate())
	}
	dest := filepath.Join(t.TempDir(), "l2.onnx")
	if err := c.ExtraerL2(dest); err != nil {
		t.Fatal(err)
	}
	if b, _ := os.ReadFile(dest); string(b) != "ONNX-falso" {
		t.Fatalf("ONNX extraído: %q", b)
	}
	if r := leer(t, c.PuntuarL2(preguntaCompraL2, ranuras([]float32{0, 1, 0, 0}), 1)); r.Answer != "soporte" || !r.Opina {
		t.Fatalf("%+v", r)
	}
	if r := leer(t, c.Decidir("hola", preguntaCompra)); r.Ok {
		t.Fatal("sin L1 debía fallar")
	}
	if r := leer(t, c.DecidirL0("hola", preguntaCompra)); !r.Ok || r.Opina {
		t.Fatalf("sin L0 no opina: %+v", r)
	}
}

func TestAbrirErrores(t *testing.T) {
	if _, err := Abrir(filepath.Join(t.TempDir(), "no-existe.chispa")); err == nil {
		t.Fatal("fichero inexistente debía fallar")
	}
	basura := filepath.Join(t.TempDir(), "x.chispa")
	os.WriteFile(basura, []byte("esto no es un chispa v3, ni de lejos, ni con 256 bytes de relleno"), 0o600)
	if _, err := Abrir(basura); err == nil {
		t.Fatal("basura debía fallar")
	}
	// una sección L1 con cabecera válida pero cuerpo roto no se abre
	l1roto := make([]byte, 256+9*16)
	copy(l1roto, "CHL1")
	binary.LittleEndian.PutUint32(l1roto[8:], 1)
	binary.LittleEndian.PutUint32(l1roto[12:], 4)
	binary.LittleEndian.PutUint32(l1roto[16:], 2)
	for i := 0; i < 9; i++ {
		binary.LittleEndian.PutUint64(l1roto[36+16*i:], uint64(256+16*i))
		binary.LittleEndian.PutUint64(l1roto[44+16*i:], 16)
	}
	if _, err := Abrir(escribirV3(t, append(metaYCalib(t), chispa3.Seccion{Tipo: chispa3.L1, Datos: l1roto}))); err == nil {
		t.Fatal("L1 roto debía fallar")
	}
}

func TestAbrirL0(t *testing.T) {
	l0, err := os.ReadFile("../../../server/testdata/urgencia.chispa")
	if err != nil {
		t.Skip("falta server/testdata/urgencia.chispa")
	}
	c, err := Abrir(escribirV3(t, append(metaYCalib(t), chispa3.Seccion{Tipo: chispa3.L0, Datos: l0})))
	if err != nil {
		t.Fatal(err)
	}
	defer c.Cerrar()
	if c.Capas() != `["L0"]` {
		t.Fatalf("capas %s", c.Capas())
	}
	labels := c.l0[0].m.Labels
	ops := make([]string, len(labels))
	for i, l := range labels {
		ops[i] = `{"id":"` + l + `"}`
	}
	q := `{"question":"¿urgencia?","kind":"choice","options":[` + strings.Join(ops, ",") + `]}`
	r := leer(t, c.DecidirL0("necesito ayuda urgente, se me cae el techo", q))
	if !r.Ok || !r.Opina || r.Answer == "" || len(r.Probs) != len(labels) {
		t.Fatalf("L0: %+v", r)
	}
	// con otras etiquetas, no hay modelo → no opina
	if r := leer(t, c.DecidirL0("hola", preguntaCompra)); !r.Ok || r.Opina {
		t.Fatalf("L0 con otro esquema no opina: %+v", r)
	}
}

const preguntaScore = `{"question":"¿Qué tan urgente?","kind":"score","options":[
 {"id":"1","description":"puede esperar sin problema"},{"id":"2","description":"conviene atenderlo pronto"},{"id":"3","description":"urgente ya"}]}`

func TestDecidirScoreNiveles(t *testing.T) {
	c := conFalso()
	for texto, want := range map[string]string{"puede esperar sin problema": "1", "conviene atenderlo pronto": "2", "urgente ya": "3"} {
		r := leer(t, c.Decidir(texto, preguntaScore))
		var z float64
		for _, p := range r.Probs {
			z += p
		}
		if !r.Ok || !r.Opina || r.Answer != want || len(r.Probs) != 3 || math.Abs(z-1) > 1e-9 || r.Conf != r.Probs[want] {
			t.Fatalf("%q: %+v", texto, r)
		}
	}
	// la T de «score» de CALIB manda sobre la de choice
	b := conFalso()
	b.calib = chispa3.Calib{Tipos: map[string]chispa3.ParamsTipo{"score": {T: 5}}}
	ra, rb := leer(t, c.Decidir("urgente ya", preguntaScore)), leer(t, b.Decidir("urgente ya", preguntaScore))
	if !(rb.Probs["3"] < ra.Probs["3"]) {
		t.Fatalf("T=5 debía ablandar: %v frente a %v", rb.Probs, ra.Probs)
	}
	// mediana: masa repartida entre extremos → gana el central con su probabilidad
	p, _ := leerPregunta(preguntaScore)
	r := puntuarNiveles(p, []float64{0.4, 0.4 + 0.05*math.Log(.5), 0.4}, 0.05)
	if r.Answer != "2" || r.Conf != r.Probs["2"] || r.Conf > 0.25 {
		t.Fatalf("mediana: %+v", r)
	}
}
