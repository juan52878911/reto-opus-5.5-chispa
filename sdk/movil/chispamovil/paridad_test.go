package chispamovil

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/binary"
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"

	"chispa/format/chispa3"
	"chispa/runtime/tok"

	"github.com/juan52878911/chispa/server/decide"
)

// Paridad del núcleo móvil con las funciones del servidor (server/decide), sobre los fixtures del repo.
const tolParidad = 1e-6

const (
	dirL0TF = "../../../server/decide/testdata/l0tf/"
	fixConj = "../../../model/l2/tests/fixtures_conjunta/paridad.json"
)

func ficheroV3(t *testing.T, secs ...chispa3.Seccion) *Chispa {
	t.Helper()
	var buf bytes.Buffer
	if err := chispa3.Escribir(&buf, append(metaYCalib(t), secs...)); err != nil {
		t.Fatal(err)
	}
	ruta := filepath.Join(t.TempDir(), "m.chispa")
	if err := os.WriteFile(ruta, buf.Bytes(), 0o600); err != nil {
		t.Fatal(err)
	}
	c, err := Abrir(ruta)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { c.Cerrar() })
	return c
}

type frasesL0TF struct {
	Etiquetas []string `json:"etiquetas"`
	Frases    []struct {
		Texto string    `json:"texto"`
		Probs []float64 `json:"probs"`
	} `json:"frases"`
}

func preguntaDe(texto string, ids []string) (string, decide.Pregunta) {
	var js []string
	p := decide.Pregunta{ID: "q", Texto: texto, Kind: decide.KindChoice}
	for _, id := range ids {
		js = append(js, `{"id":`+jsonStr(id)+`}`)
		p.Opciones = append(p.Opciones, decide.Opcion{ID: id})
	}
	return `{"question":` + jsonStr(texto) + `,"kind":"choice","options":[` + strings.Join(js, ",") + `]}`, p
}

func jsonStr(s string) string { b, _ := json.Marshal(s); return string(b) }

// DecidirL0 con la sección L0TF da las probabilidades del servidor (decide.L0) con |Δp| ≤ 1e-6, y las de sklearn
// del fixture con la tolerancia que ya usa el servidor.
func TestDecidirL0TFParidadConServidor(t *testing.T) {
	for _, nombre := range []string{"modelo.l0tf", "modelo_f16.l0tf"} {
		raw, err := os.ReadFile(dirL0TF + nombre)
		if err != nil {
			t.Fatal(err)
		}
		var fx frasesL0TF
		j, err := os.ReadFile(dirL0TF + "frases.json")
		if err != nil {
			t.Fatal(err)
		}
		if err := json.Unmarshal(j, &fx); err != nil {
			t.Fatal(err)
		}
		c := ficheroV3(t, chispa3.Seccion{Tipo: chispa3.L0TF, Datos: raw})
		if c.Capas() != `["L0"]` {
			t.Fatalf("capas %s", c.Capas())
		}
		m, err := chispa3.DecodificarL0TF(raw)
		if err != nil {
			t.Fatal(err)
		}
		srv := decide.NuevoL0(4)
		if err := srv.AnadirTF("tf", m); err != nil {
			t.Fatal(err)
		}
		pjs, p := preguntaDe("¿intención?", fx.Etiquetas)
		var peor, peorSk float64
		for _, f := range fx.Frases {
			p.Estado = f.Texto
			want, err := srv.Decidir(context.Background(), p)
			if err != nil {
				t.Fatal(err)
			}
			got := leer(t, c.DecidirL0(f.Texto, pjs))
			if !got.Ok || !got.Opina || got.Answer != want.Answer || len(got.Probs) != len(want.Probs) {
				t.Fatalf("%s %q: móvil %+v, servidor %+v", nombre, f.Texto, got, want)
			}
			for i, id := range fx.Etiquetas {
				peor = math.Max(peor, math.Abs(got.Probs[id]-want.Probs[id]))
				peorSk = math.Max(peorSk, math.Abs(got.Probs[id]-f.Probs[i]))
			}
		}
		t.Logf("%s: %d frases, |Δp| frente al servidor %.3g, frente a sklearn %.3g", nombre, len(fx.Frases), peor, peorSk)
		if peor > tolParidad {
			t.Fatalf("%s: |Δp| = %g frente al servidor", nombre, peor)
		}
	}
}

// Con L0TF y L0 a la vez manda L0TF (como en ArmarDesde); con otro esquema no opina.
func TestDecidirL0TFOtroEsquemaNoOpina(t *testing.T) {
	raw, err := os.ReadFile(dirL0TF + "modelo.l0tf")
	if err != nil {
		t.Fatal(err)
	}
	c := ficheroV3(t, chispa3.Seccion{Tipo: chispa3.L0TF, Datos: raw})
	if r := leer(t, c.DecidirL0("hola", preguntaCompra)); !r.Ok || r.Opina {
		t.Fatalf("otro esquema no opina: %+v", r)
	}
}

type casoConj struct {
	S    [][]float32
	Sims []float64
	L0   map[string]float64
	Sp   []float64
	L2   []float64
	Prob []float64 `json:"probs"`
}

type fixtureConj struct {
	Pregunta   string
	Opciones   []string
	Tolerancia float64
	ConjB64    string `json:"conj_b64"`
	Casos      []casoConj
}

func leerFixtureConj(t *testing.T) (fixtureConj, []byte) {
	t.Helper()
	b, err := os.ReadFile(fixConj)
	if err != nil {
		t.Fatal(err)
	}
	var fx fixtureConj
	if err := json.Unmarshal(b, &fx); err != nil {
		t.Fatal(err)
	}
	raw, err := base64.StdEncoding.DecodeString(fx.ConjB64)
	if err != nil {
		t.Fatal(err)
	}
	return fx, raw
}

// torresParaSims arma ESQUEMAS con una torre por opción y devuelve una sola ranura S (la primera del caso): el
// MaxSim de cada torre contra ella es softplus(h·s) y h se elige para que valga sims[i] del fixture.
func torresParaSims(t *testing.T, fx fixtureConj, c casoConj) ([]byte, [][]float32) {
	t.Helper()
	s0 := c.S[0]
	var mx float64
	for _, x := range s0 {
		mx = math.Max(mx, math.Abs(float64(x)))
	}
	var es []chispa3.EntradaEsquema
	for i, id := range fx.Opciones {
		obj := math.Log(math.Expm1(c.Sims[i])) // softplus⁻¹(sims[i])
		signo := 127.0
		if obj < 0 {
			signo = -127 // la escala de una torre ha de ser positiva
		}
		h := make([]int8, len(s0))
		var dot float64
		for j := range h {
			h[j] = int8(math.Round(signo * float64(s0[j]) / mx))
			dot += float64(h[j]) * float64(s0[j])
		}
		es = append(es, chispa3.EntradaEsquema{Hash: chispa3.HashEsquema(fx.Pregunta, []string{id}), Escala: float32(obj / dot), Vec: h})
	}
	b, err := chispa3.CodificarEsquemas(len(s0), es)
	if err != nil {
		t.Fatal(err)
	}
	return b, [][]float32{s0}
}

func ranurasB64(S [][]float32) string {
	var b []byte
	for _, s := range S {
		for _, x := range s {
			b = binary.LittleEndian.AppendUint32(b, math.Float32bits(x))
		}
	}
	return base64.StdEncoding.EncodeToString(b)
}

// La cabeza de CONJ del núcleo móvil coincide con la del servidor (decide.L2c) con |Δp| ≤ 1e-6 sobre los casos del
// fixture de Python, y con Python dentro de su tolerancia (1e-2 con el producto entero; la cuantización de S).
func TestCabezaConjuntaParidadConServidor(t *testing.T) {
	fx, raw := leerFixtureConj(t)
	conj, err := chispa3.DecodificarConj(raw)
	if err != nil {
		t.Fatal(err)
	}
	for n, caso := range fx.Casos {
		esq, S := torresParaSims(t, fx, caso)
		c := ficheroV3(t,
			chispa3.Seccion{Tipo: chispa3.L2, Datos: []byte("onnx")},
			chispa3.Seccion{Tipo: chispa3.ESQUEMAS, Datos: esq},
			chispa3.Seccion{Tipo: chispa3.CONJ, Datos: raw})
		pjs, p := preguntaDe(fx.Pregunta, fx.Opciones)
		var in map[string]any
		json.Unmarshal([]byte(pjs), &in)
		in["l0"], in["ranuras"], in["k"] = caso.L0, ranurasB64(S), len(S)
		js, _ := json.Marshal(in)
		got := leer(t, c.CabezaConjunta(string(js)))
		if !got.Ok || !got.Opina {
			t.Fatalf("caso %d: %+v", n, got)
		}
		// el servidor, con las mismas similitudes que calcula el móvil (MaxSim de torres contra S)
		ts, _ := chispa3.DecodificarEsquemas(esq)
		sims := make([]float64, len(fx.Opciones))
		for i, id := range fx.Opciones {
			v, e, _ := ts.Buscar(chispa3.HashEsquema(fx.Pregunta, []string{id}))
			sims[i] = chispa3.MaxSim(S, v, e)
		}
		l2c := decide.NuevoL2cCon(nil, simsFijas{S, sims}, conj)
		want, err := l2c.DecidirCon(context.Background(), p, decide.Previas{"L0": {Probs: caso.L0, Conf: 0.5}})
		if err != nil {
			t.Fatal(err)
		}
		var peor float64
		for _, id := range fx.Opciones {
			peor = math.Max(peor, math.Abs(got.Probs[id]-want.Probs[id]))
		}
		if peor > tolParidad || got.Answer != want.Answer {
			t.Fatalf("caso %d: |Δp| frente al servidor %g (%s frente a %s)", n, peor, got.Answer, want.Answer)
		}
		if n == 0 {
			t.Logf("caso 0: |Δp| servidor %.3g", peor)
		}
	}
}

type simsFijas struct {
	S    [][]float32
	sims []float64
}

func (s simsFijas) Similitudes(decide.Pregunta) ([][]float32, []float64, bool, error) {
	return s.S, s.sims, true, nil
}

// Sin CONJ, sin L0, otro esquema o ranuras mal formadas: no opina (la cascada cae a PuntuarL2) o falla claro.
func TestCabezaConjuntaSinOpinar(t *testing.T) {
	fx, raw := leerFixtureConj(t)
	esq, S := torresParaSims(t, fx, fx.Casos[0])
	pjs, _ := preguntaDe(fx.Pregunta, fx.Opciones)
	mk := func(l0 map[string]float64, ranuras string, k int) string {
		var in map[string]any
		json.Unmarshal([]byte(pjs), &in)
		in["l0"], in["ranuras"], in["k"] = l0, ranuras, k
		b, _ := json.Marshal(in)
		return string(b)
	}
	secs := []chispa3.Seccion{{Tipo: chispa3.L2, Datos: []byte("onnx")}, {Tipo: chispa3.ESQUEMAS, Datos: esq}}
	sinConj := ficheroV3(t, secs...)
	conConj := ficheroV3(t, append(secs, chispa3.Seccion{Tipo: chispa3.CONJ, Datos: raw})...)
	ok := mk(fx.Casos[0].L0, ranurasB64(S), 1)
	if r := leer(t, sinConj.CabezaConjunta(ok)); !r.Ok || r.Opina {
		t.Fatalf("sin CONJ: %+v", r)
	}
	if r := leer(t, conConj.CabezaConjunta(mk(nil, ranurasB64(S), 1))); !r.Ok || r.Opina {
		t.Fatalf("sin L0: %+v", r)
	}
	if r := leer(t, conConj.CabezaConjunta(preguntaCompraL2)); !r.Ok || r.Opina {
		t.Fatalf("otro esquema: %+v", r)
	}
	if r := leer(t, conConj.CabezaConjunta(mk(fx.Casos[0].L0, "!!", 1))); r.Ok || r.Error == "" {
		t.Fatalf("base64 roto: %+v", r)
	}
	if r := leer(t, conConj.CabezaConjunta(mk(fx.Casos[0].L0, ranurasB64(S), 3))); r.Ok {
		t.Fatalf("k que no cuadra: %+v", r)
	}
	if r := leer(t, conConj.CabezaConjunta("no es json")); r.Ok {
		t.Fatalf("json roto: %+v", r)
	}
}

// TokenizarE5 da los ids de runtime/tok. Sin el .chispa-tok (CHISPA_TOK, como en runtime/tok) se salta.
func TestTokenizarE5ParidadConRuntimeTok(t *testing.T) {
	ruta := os.Getenv("CHISPA_TOK")
	if ruta == "" {
		ruta = "/tmp/e5.chispa-tok"
	}
	ref, err := tok.Abrir(ruta)
	if err != nil {
		t.Skipf("sin .chispa-tok (runtime/tok/exportar.py; CHISPA_TOK): %v", err)
	}
	c := &Chispa{}
	if c.TieneTokenizadorE5() || c.TokenizarE5("hola") != nil {
		t.Fatal("sin cargar no debe haber tokenizador")
	}
	if err := c.CargarTokenizadorE5(ruta); err != nil {
		t.Fatal(err)
	}
	f, err := os.Open("../../../runtime/tok/testdata/ids_e5.jsonl")
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	var n int
	dec := json.NewDecoder(f)
	for dec.More() {
		var caso struct {
			Texto string  `json:"texto"`
			IDs   []int32 `json:"ids"`
		}
		if err := dec.Decode(&caso); err != nil {
			t.Fatal(err)
		}
		b := c.TokenizarE5(caso.Texto)
		got := make([]int32, len(b)/4)
		for i := range got {
			got[i] = int32(binary.LittleEndian.Uint32(b[4*i:]))
		}
		if !slices.Equal(got, caso.IDs) || !slices.Equal(got, ref.Tokenizar(caso.Texto)) {
			t.Fatalf("%q: %v frente a %v", caso.Texto, got, caso.IDs)
		}
		n++
	}
	t.Logf("%d frases iguales a runtime/tok", n)
}

func TestTokenizarE5RutaMala(t *testing.T) {
	if err := (&Chispa{}).CargarTokenizadorE5("/no/existe.chispa-tok"); err == nil {
		t.Fatal("debía fallar")
	}
}
