package chispamovil

import (
	"context"
	"encoding/binary"
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"

	"chispa/format/chispa3"
	"chispa/runtime/l1"
	"chispa/runtime/tok"

	"github.com/juan52878911/chispa/server/decide"
)

// abrirLargo abre el mismo .chispa con AbrirConTextoLargo.
func abrirLargo(t *testing.T, tl string, secs ...chispa3.Seccion) *Chispa {
	t.Helper()
	c, err := AbrirConTextoLargo(escribirV3(t, append(metaYCalib(t), secs...)), SoporteL1PorDefecto, SoporteApagado, true, tl)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { c.Cerrar() })
	return c
}

func opsL1() []decide.Opcion {
	return []decide.Opcion{{ID: "facturacion", Description: "factura cobro pago dinero reembolso"}, {ID: "logistica", Description: "envio paquete retraso pedido"}}
}

func preguntaJS(t *testing.T, kind string, ops []decide.Opcion) string {
	t.Helper()
	js, _ := json.Marshal(ops)
	return `{"question":"¿Qué área?","kind":"` + kind + `","options":` + string(js) + `}`
}

func comparaResp(t *testing.T, ctx string, got respuestaPlana, want decide.Respuesta) {
	t.Helper()
	if !got.Ok || got.Answer != want.Answer || math.Abs(got.Conf-want.Conf) > tolParidad || got.Opina != (want.Conf > 0) {
		t.Fatalf("%s: móvil %+v, servidor %+v", ctx, got, want)
	}
	for id, pr := range want.Probs {
		if math.Abs(got.Probs[id]-pr) > tolParidad {
			t.Fatalf("%s opción %s: móvil %v, servidor %v", ctx, id, got.Probs[id], pr)
		}
	}
}

type respuestaPlana = respuesta

// Sin texto_largo, con "" / "{}" / cabeza (con cualquier otro parámetro) y con una estrategia sobre un texto que cabe, Decidir
// da exactamente lo mismo que Abrir, también con textos que pasan de max_tokens.
func TestTextoLargoMovilNoRegresion(t *testing.T) {
	sec := chispa3.Seccion{Tipo: chispa3.L1, Datos: l1Diminuto(palabrasTiny)}
	base := ficheroV3(t, sec)
	variantes := []*Chispa{abrirLargo(t, "", sec), abrirLargo(t, "{}", sec), abrirLargo(t, `{"estrategia":"cabeza","agregacion":"max","solape":3,"max_trozos":2,"ventana_l1":4}`, sec),
		abrirLargo(t, `{"estrategia":"cabeza_cola"}`, sec), abrirLargo(t, `{"estrategia":"trozos","agregacion":"max"}`, sec)}
	for _, estado := range []string{"factura cobro", "paquete retraso envio", "", strings.Repeat("pedido dinero pago ", 150), strings.Repeat("pedido dinero pago ", 400)} {
		for _, kind := range []string{"choice", "score", "noul"} {
			ops := opsL1()
			if kind == "noul" {
				ops = []decide.Opcion{{ID: "true"}, {ID: "false"}}
			}
			js := preguntaJS(t, kind, ops)
			want := base.Decidir(estado, js)
			for i, v := range variantes {
				if i >= 3 && len(estado) > 2000 { // más de 512 tokens: cabeza_cola y trozos sí cambian
					continue
				}
				if got := v.Decidir(estado, js); got != want {
					t.Fatalf("variante %d, %s, %.20q: %s ≠ %s", i, kind, estado, got, want)
				}
			}
		}
	}
	if base.TextoLargoSuperados() == 0 {
		t.Fatal("el texto de 1200 tokens debía contarse como largo")
	}
}

func TestAbrirConTextoLargoRechazaMalos(t *testing.T) {
	ruta := escribirV3(t, metaYCalib(t))
	for _, js := range []string{`{"estrategia":"mitad"}`, `{"agregacion":"min"}`, `{"solape":-1}`, `{"max_trozos":999}`, `{"trozos":3}`, `no es json`} {
		if c, err := AbrirConTextoLargo(ruta, SoporteL1PorDefecto, SoporteApagado, true, js); err == nil {
			c.Cerrar()
			t.Fatalf("%s debería fallar", js)
		}
	}
}

// L1 del móvil con cabeza_cola y trozos (max y media) = L1 del servidor, mismas preguntas y mismo texto largo.
func TestTextoLargoL1ParidadConServidor(t *testing.T) {
	l1b := l1Diminuto(palabrasTiny)
	sec := chispa3.Seccion{Tipo: chispa3.L1, Datos: l1b}
	ruta := filepath.Join(t.TempDir(), "m.chispa-l1")
	if err := os.WriteFile(ruta, l1b, 0o600); err != nil {
		t.Fatal(err)
	}
	m, err := l1.Abrir(ruta)
	if err != nil {
		t.Fatal(err)
	}
	defer m.Cerrar()
	largo := "factura cobro pago dinero hola gracias hola gracias envio paquete retraso pedido factura reembolso pago cobro"
	for _, tl := range []tok.TextoLargo{
		{Estrategia: "cabeza_cola", VentanaL1: 4}, {Estrategia: "trozos", Agregacion: "max", VentanaL1: 4}, {Estrategia: "trozos", Agregacion: "media", VentanaL1: 4},
		{Estrategia: "trozos", Agregacion: "media", VentanaL1: 6, Solape: 2, MaxTrozos: 3}, {Estrategia: "trozos", VentanaL1: 5, MaxTrozos: 2},
	} {
		js, _ := json.Marshal(tl)
		c := abrirLargo(t, string(js), sec)
		srv := decide.NuevoL1Modelo(m, c.calib, 4).ConTextoLargo(tl)
		for _, kind := range []string{decide.KindChoice, decide.KindScore, decide.KindNoul} {
			ops := opsL1()
			if kind == decide.KindNoul {
				ops = []decide.Opcion{{ID: "true"}, {ID: "false"}}
			}
			for _, estado := range []string{largo, "factura cobro", "zzz"} {
				want, err := srv.Decidir(context.Background(), decide.Pregunta{ID: "q", Texto: "¿Qué área?", Kind: kind, Estado: estado, Opciones: ops})
				if err != nil {
					t.Fatal(err)
				}
				got := leer(t, c.Decidir(estado, preguntaJS(t, kind, ops)))
				comparaResp(t, string(js)+" "+kind, got, want)
			}
		}
	}
}

// --- L2 ---

func tokE5(t *testing.T) *tok.Tokenizador {
	t.Helper()
	ruta := os.Getenv("CHISPA_TOK")
	if ruta == "" {
		ruta = rutaTokPorDefecto()
	}
	if _, err := os.Stat(ruta); err != nil && os.Getenv("CHISPA_TOK") == "" {
		t.Skipf("sin .chispa-tok: %v", err)
	}
	tk, err := tok.Abrir(ruta)
	if err != nil {
		t.Fatal(err)
	}
	return tk
}

// sesionMarca da S = {1,0} si algún id es la marca y {0,0} (sin señal) si no.
type sesionMarca struct{ marca int64 }

func (s sesionMarca) Ranuras(ids []int64) ([][]float32, error) {
	for _, id := range ids {
		if id == s.marca {
			return [][]float32{{1, 0}}, nil
		}
	}
	return [][]float32{{0, 0}}, nil
}

func floatsBytes(S [][]float32) []byte {
	var b []byte
	for _, r := range S {
		for _, v := range r {
			b = binary.LittleEndian.AppendUint32(b, math.Float32bits(v))
		}
	}
	return b
}

// parsea TrozosE5: [n][len][ids…]…
func leerTrozos(t *testing.T, b []byte) [][]int64 {
	t.Helper()
	n := int(binary.LittleEndian.Uint32(b))
	b = b[4:]
	out := make([][]int64, n)
	for i := range out {
		l := int(binary.LittleEndian.Uint32(b))
		for j := 0; j < l; j++ {
			out[i] = append(out[i], int64(binary.LittleEndian.Uint32(b[4+4*j:])))
		}
		b = b[4+4*l:]
	}
	if len(b) != 0 {
		t.Fatalf("sobran %d bytes", len(b))
	}
	return out
}

// Paridad servidor ↔ móvil en L2: el servidor tokeniza y decide cada ventana; el móvil da las ventanas (TrozosE5), la app corre ONNX
// (aquí, la sesión falsa) y PuntuarL2Trozos agrega. Mismas ventanas, mismas probabilidades. Con trozos, la señal solo al final decide.
func TestTextoLargoL2ParidadConServidor(t *testing.T) {
	tk := tokE5(t)
	esqB, err := chispa3.CodificarEsquemas(2, []chispa3.EntradaEsquema{
		{Hash: chispa3.HashEsquema("¿q?", []string{"a"}), Escala: 1, Vec: []int8{1, 0}}, {Hash: chispa3.HashEsquema("¿q?", []string{"b"}), Escala: 1, Vec: []int8{0, 1}}})
	if err != nil {
		t.Fatal(err)
	}
	esq, err := chispa3.DecodificarEsquemas(esqB)
	if err != nil {
		t.Fatal(err)
	}
	ids := tk.Tokenizar("zqxjvk")
	ses := sesionMarca{int64(ids[len(ids)-2])}
	secs := []chispa3.Seccion{{Tipo: chispa3.L2, Datos: []byte("ONNX-falso")}, {Tipo: chispa3.ESQUEMAS, Datos: esqB}}
	relleno := strings.Repeat("palabra · ", 500)
	pj := `{"question":"¿q?","kind":"choice","options":[{"id":"a"},{"id":"b"}]}`
	cab := abrirLargo(t, "", secs...)
	if err := cab.CargarTokenizadorE5(os.Getenv("CHISPA_TOK")); err != nil && os.Getenv("CHISPA_TOK") != "" {
		t.Fatal(err)
	}
	for _, c := range []struct {
		js     string
		decide bool
	}{
		{"", false}, {`{"estrategia":"cabeza"}`, false},
		{`{"estrategia":"cabeza_cola"}`, true},
		{`{"estrategia":"trozos","agregacion":"max","max_trozos":64}`, true},
		{`{"estrategia":"trozos","agregacion":"media","solape":8,"max_trozos":64}`, true},
		{`{"estrategia":"trozos","agregacion":"max","max_trozos":2}`, false}, // el tope de trozos deja fuera el final
	} {
		var tl tok.TextoLargo
		if c.js != "" {
			json.Unmarshal([]byte(c.js), &tl)
		}
		mov := abrirLargo(t, c.js, secs...)
		mov.tok = tk
		srv := decide.NuevoL2Con(ses, esq, mov.calib.ParaL2(), decide.NuevoTokenizadorE5(tk)).ConTextoLargo(tl)
		for _, estado := range []string{relleno + "zqxjvk", relleno, "zqxjvk hola"} {
			want, err := srv.Decidir(context.Background(), decide.Pregunta{ID: "q", Texto: "¿q?", Kind: decide.KindChoice, Estado: estado,
				Opciones: []decide.Opcion{{ID: "a"}, {ID: "b"}}})
			if err != nil {
				t.Fatal(err)
			}
			ws := leerTrozos(t, mov.TrozosE5(estado))
			var ranuras []byte
			var ks []int
			for _, w := range ws {
				S, _ := ses.Ranuras(w)
				ranuras, ks = append(ranuras, floatsBytes(S)...), append(ks, len(S))
			}
			ksJS, _ := json.Marshal(ks)
			got := leer(t, mov.PuntuarL2Trozos(pj, ranuras, string(ksJS)))
			comparaResp(t, c.js+" "+estado[:min(len(estado), 12)], got, want)
			if first := idsU32(mov.TokenizarE5(estado)); len(first) != len(ws[0]) {
				t.Fatalf("TokenizarE5 debe ser la primera ventana: %d ≠ %d ids", len(first), len(ws[0]))
			}
			if estado == relleno+"zqxjvk" && c.decide != (got.Answer == "a" && got.Conf > 0.5) {
				t.Fatalf("%s: %+v", c.js, got)
			}
		}
	}
	// sin estrategia, PuntuarL2Trozos con una ventana = PuntuarL2 y TokenizarE5 = lo de siempre
	cab.tok = tk
	S, _ := ses.Ranuras(nil)
	if a, b := cab.PuntuarL2(pj, floatsBytes(S), 1), cab.PuntuarL2Trozos(pj, floatsBytes(S), "[1]"); a != b {
		t.Fatalf("%s ≠ %s", a, b)
	}
	if !reflect.DeepEqual(cab.TokenizarE5(relleno), idsABytes(tk.TokenizarMax(tok.Prefijo, relleno, 128))) {
		t.Fatal("TokenizarE5 con cabeza difiere de runtime/tok")
	}
	if cab.TextoLargoSuperados() == 0 {
		t.Fatal("no se contó el texto largo")
	}
	if r := leer(t, cab.PuntuarL2Trozos(pj, nil, "[]")); r.Ok {
		t.Fatal("ks vacío debe fallar")
	}
}

// L2c del móvil con ks (varias ventanas): cada ventana por la cabeza conjunta y las probabilidades agregadas, como el servidor;
// con una sola ventana (o sin ks) es lo de siempre.
func TestTextoLargoCabezaConjuntaVentanas(t *testing.T) {
	fx, raw := leerFixtureConj(t)
	caso := fx.Casos[0]
	esq, S := torresParaSims(t, fx, caso)
	secs := []chispa3.Seccion{{Tipo: chispa3.L2, Datos: []byte("onnx")}, {Tipo: chispa3.ESQUEMAS, Datos: esq}, {Tipo: chispa3.CONJ, Datos: raw}}
	pjs, _ := preguntaDe(fx.Pregunta, fx.Opciones)
	entrada := func(ranuras []float32, extra map[string]any) string {
		var in map[string]any
		json.Unmarshal([]byte(pjs), &in)
		in["l0"], in["ranuras"], in["k"] = caso.L0, ranuras, len(S)
		for k, v := range extra {
			in[k] = v
		}
		js, _ := json.Marshal(in)
		return string(js)
	}
	S2 := make([][]float32, len(S))
	for i, r := range S {
		S2[i] = make([]float32, len(r))
		for j, v := range r {
			S2[i][j] = v * 0.5
		}
	}
	for _, agg := range []string{"max", "media"} {
		c := abrirLargo(t, `{"estrategia":"trozos","agregacion":"`+agg+`"}`, secs...)
		a := leer(t, c.CabezaConjunta(entrada(planas(S), nil)))
		b := leer(t, c.CabezaConjunta(entrada(planas(S2), nil)))
		if !a.Opina || !b.Opina {
			t.Fatalf("%+v %+v", a, b)
		}
		if one := leer(t, c.CabezaConjunta(entrada(planas(S), map[string]any{"ks": []int{len(S)}}))); !reflect.DeepEqual(one, a) {
			t.Fatalf("ks de una ventana debe ser lo de siempre: %+v ≠ %+v", one, a)
		}
		got := leer(t, c.CabezaConjunta(entrada(append(planas(S), planas(S2)...), map[string]any{"ks": []int{len(S), len(S)}})))
		probs, ans, conf, ok := tok.AgregarProbs("choice", fx.Opciones, []map[string]float64{a.Probs, b.Probs}, agg, 0.5)
		if !ok || !got.Opina || got.Answer != ans || math.Abs(got.Conf-conf) > 1e-12 {
			t.Fatalf("%s: %+v, esperaba %s/%v", agg, got, ans, conf)
		}
		for id, p := range probs {
			if math.Abs(got.Probs[id]-p) > 1e-12 {
				t.Fatalf("%s %s: %v ≠ %v", agg, id, got.Probs[id], p)
			}
		}
	}
	// ks que no casa con las ranuras
	c := abrirLargo(t, "", secs...)
	if r := leer(t, c.CabezaConjunta(entrada(planas(S), map[string]any{"ks": []int{len(S), len(S)}}))); r.Ok {
		t.Fatal("ks que no casa con las ranuras debía fallar")
	}
}

// explicito=false es Abrir: los λ que se pasen no cuentan.
func TestAbrirConTextoLargoNoExplicitoEsAbrir(t *testing.T) {
	ruta := escribirV3(t, append(metaYCalib(t), chispa3.Seccion{Tipo: chispa3.L1, Datos: l1Diminuto(palabrasTiny)}))
	a, err := Abrir(ruta)
	if err != nil {
		t.Fatal(err)
	}
	defer a.Cerrar()
	b, err := AbrirConTextoLargo(ruta, 0, 0, false, "")
	if err != nil {
		t.Fatal(err)
	}
	defer b.Cerrar()
	if !reflect.DeepEqual(a.lambdaL1, b.lambdaL1) || a.explicitoL1 != b.explicitoL1 || !reflect.DeepEqual(a.lambdaL2, b.lambdaL2) {
		t.Fatalf("λ: %v/%v ≠ %v/%v", a.lambdaL1, a.lambdaL2, b.lambdaL1, b.lambdaL2)
	}
}
