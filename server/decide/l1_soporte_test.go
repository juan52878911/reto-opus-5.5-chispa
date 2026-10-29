package decide

import (
	"context"
	"math"
	"os"
	"path/filepath"
	"reflect"
	"testing"

	"chispa/format/chispa3"
)

// soplL1 arma la sección SOPL1 de pregunta p con la media de `textos[id]` (embebidos con el L1 del modelo) y k[id] ejemplos.
func soplL1(t *testing.T, l *L1, p Pregunta, textos map[string]string, k map[string]uint32) []byte {
	t.Helper()
	dim := l.m.Dim()
	e := chispa3.EntradaSopl1{Hash: ClaveConj(p)}
	for _, id := range []string{"facturacion", "logistica"} {
		e.Ids = append(e.Ids, id)
		v := make([]float32, dim)
		if tx, ok := textos[id]; ok {
			l.m.Embed(tx, v)
		}
		esc, q := chispa3.CuantizarMedia(v)
		e.K, e.Escala, e.Media = append(e.K, k[id]), append(e.Escala, esc), append(e.Media, q...)
	}
	b, err := chispa3.CodificarSopl1(dim, []chispa3.EntradaSopl1{e})
	if err != nil {
		t.Fatal(err)
	}
	return b
}

func l1Con(t *testing.T, sopl []byte, lambda *float64) *L1 {
	t.Helper()
	var extra []chispa3.Seccion
	if sopl != nil {
		extra = append(extra, chispa3.Seccion{Tipo: chispa3.SOPL1, Datos: sopl})
	}
	// lambda nil = apagado explícito (el comportamiento anterior al default 4); ver TestL1DefaultCuatro para el ausente.
	cfg := Config{CacheEsquemas: 16, CacheRespuestas: 16, L1ShrinkageLambda: lambda, L1ShrinkageApagado: lambda == nil}
	mt, err := ArmarDesde(v3Tiny(t, calibTiny(), extra...), NuevoL0(8), &cfg, false, nil)
	if err != nil {
		t.Fatal(err)
	}
	return mt.L1.(*L1)
}

func floatPtr(x float64) *float64 { return &x }

func TestL1SoporteNilEInfinitoNoCambianNada(t *testing.T) {
	p := Pregunta{Kind: KindChoice, Texto: "¿Qué área?", Opciones: opsReembolso()}
	base := l1Con(t, nil, nil)
	sopl := soplL1(t, base, p, map[string]string{"facturacion": "paquete retraso", "logistica": "factura cobro"}, map[string]uint32{"facturacion": 5, "logistica": 3})
	score := Pregunta{Kind: KindScore, Texto: "¿Qué área?", Opciones: opsReembolso()}
	noul := Pregunta{Kind: KindNoul, Texto: "¿Es de envíos?", Opciones: []Opcion{{ID: "true"}, {ID: "false"}}}
	inf := math.Inf(1)
	variantes := map[string]*L1{"sin lambda": l1Con(t, sopl, nil), "lambda inf": l1Con(t, sopl, &inf), "sin sección": l1Con(t, nil, floatPtr(1))}
	for _, estado := range []string{"factura cobro", "paquete retraso envio", "hola gracias", "pedido dinero pago"} {
		for _, q := range []Pregunta{p, score, noul} {
			q.Estado = estado
			want, err := base.Decidir(context.Background(), q)
			if err != nil {
				t.Fatal(err)
			}
			for n, l := range variantes {
				got, err := l.Decidir(context.Background(), q)
				if err != nil || !reflect.DeepEqual(got, want) {
					t.Fatalf("%s, %q (%s): %+v ≠ %+v (%v)", n, estado, q.Kind, got, want, err)
				}
			}
		}
	}
}

func TestL1SoporteMueveElPrototipoHaciaLosEjemplos(t *testing.T) {
	p := Pregunta{Kind: KindChoice, Texto: "¿Qué área?", Estado: "paquete retraso", Opciones: opsReembolso()}
	base := l1Con(t, nil, nil)
	r0, _ := base.Decidir(context.Background(), p)
	if r0.Answer != "logistica" {
		t.Fatalf("la descripción debería llevar a logística: %+v", r0)
	}
	// Los ejemplos de «facturacion» son mensajes de envíos (soporte contrario a su descripción).
	sopl := soplL1(t, base, p, map[string]string{"facturacion": "paquete retraso"}, map[string]uint32{"facturacion": 4})
	var prev = r0.Probs["facturacion"]
	for _, lambda := range []float64{16, 4, 1, 0.01} { // w = 0,2, 0,5, 0,8, ≈1: monótono hacia los ejemplos
		r, err := l1Con(t, sopl, floatPtr(lambda)).Decidir(context.Background(), p)
		if err != nil || r.Probs["facturacion"] <= prev {
			t.Fatalf("λ=%v: P(facturacion) %v no sube desde %v (%v)", lambda, r.Probs["facturacion"], prev, err)
		}
		prev = r.Probs["facturacion"]
		if lambda == 0.01 && r.Answer != "facturacion" {
			t.Fatalf("con w≈1 el prototipo es la media de los ejemplos: %+v", r)
		}
	}
	// La opción sin ejemplos (k=0) no se mueve: su embedding en caché es el de siempre.
	l := l1Con(t, sopl, floatPtr(1))
	l.Decidir(context.Background(), p)
	b := l.opciones(p)
	e0 := base.opciones(p)
	if !reflect.DeepEqual(b["logistica"], e0["logistica"]) || reflect.DeepEqual(b["facturacion"], e0["facturacion"]) {
		t.Fatal("solo la opción con k>0 debe cambiar")
	}
	var n float64
	for _, x := range b["facturacion"] {
		n += float64(x) * float64(x)
	}
	if math.Abs(n-1) > 1e-5 {
		t.Fatalf("el prototipo mezclado debe ser unitario, |p|²=%v", n)
	}
}

func TestL1SoportePreguntaAusenteNoCambia(t *testing.T) {
	p := Pregunta{Kind: KindChoice, Texto: "¿Qué área?", Estado: "paquete retraso", Opciones: opsReembolso()}
	base := l1Con(t, nil, nil)
	sopl := soplL1(t, base, p, map[string]string{"facturacion": "paquete retraso"}, map[string]uint32{"facturacion": 4})
	otra := Pregunta{Kind: KindChoice, Texto: "¿Otra pregunta?", Estado: "paquete retraso", Opciones: opsReembolso()}
	otraIds := Pregunta{Kind: KindChoice, Texto: "¿Qué área?", Estado: "paquete retraso", Opciones: []Opcion{{ID: "facturacion"}, {ID: "logistica"}, {ID: "otra"}}}
	l := l1Con(t, sopl, floatPtr(0.01))
	for _, q := range []Pregunta{otra, otraIds} {
		want, _ := base.Decidir(context.Background(), q)
		got, _ := l.Decidir(context.Background(), q)
		if !reflect.DeepEqual(got, want) {
			t.Fatalf("%q: %+v ≠ %+v", q.Texto, got, want)
		}
	}
}

func TestConfigShrinkageLambda(t *testing.T) {
	c := ConfigPorDefecto()
	if c.L1ShrinkageLambda != nil || c.L2ShrinkageLambda != nil || c.L1ShrinkageApagado {
		t.Fatal("la config por defecto no fija λ: L1 usa el default en LambdaL1, L2 apagado (nil)")
	}
	if l := c.LambdaL1(); l == nil || *l != 4 {
		t.Fatalf("λ de L1 ausente debe ser 4: %v", l)
	}
	c.L1ShrinkageApagado = true
	if c.LambdaL1() != nil || c.Validar() != nil {
		t.Fatal("apagado explícito: λ efectivo nil y config válida")
	}
	c.L1ShrinkageLambda = floatPtr(2)
	if c.Validar() == nil {
		t.Fatal("apagado + λ a la vez debe ser error")
	}
	c.L1ShrinkageApagado, c.L1ShrinkageLambda = false, nil
	for _, v := range []float64{-1, math.NaN()} {
		c.L1ShrinkageLambda = &v
		if c.Validar() == nil {
			t.Errorf("λ=%v debería ser inválida", v)
		}
	}
	c.L1ShrinkageLambda, c.L2ShrinkageLambda = floatPtr(0), floatPtr(3)
	if err := c.Validar(); err != nil {
		t.Fatal(err)
	}
}

// λ = 0 ⇒ solo ejemplos: el prototipo de la opción con k > 0 es la media de los ejemplos normalizada; λ = +∞ ⇒ solo descripción (el de siempre).
func TestL1SoporteLambdaCeroEInfinito(t *testing.T) {
	p := Pregunta{Kind: KindChoice, Texto: "¿Qué área?", Estado: "paquete retraso", Opciones: opsReembolso()}
	base := l1Con(t, nil, nil)
	sopl := soplL1(t, base, p, map[string]string{"facturacion": "paquete retraso"}, map[string]uint32{"facturacion": 4})
	ps, err := chispa3.DecodificarSopl1(sopl)
	if err != nil {
		t.Fatal(err)
	}
	ent, ok := ps.Buscar(ClaveConj(p))
	if !ok {
		t.Fatal("falta la entrada")
	}
	_, media, _ := ent.Opcion("facturacion", ps.Dim())
	want := chispa3.Mezclar(base.opciones(p)["facturacion"], media, 1)
	cero, inf := 0.0, math.Inf(1)
	if got := l1Con(t, sopl, &cero).opciones(p)["facturacion"]; !reflect.DeepEqual(got, want) {
		t.Fatal("λ=0 debe dar solo la media de los ejemplos")
	}
	if got := l1Con(t, sopl, &inf).opciones(p); !reflect.DeepEqual(got, base.opciones(p)) {
		t.Fatal("λ=∞ debe dar solo la descripción")
	}
}

// Sin λ en la config el default 4 se aplica; apagado explícito da exactamente lo de antes; un valor explícito manda; sin SOPL1 nada cambia.
func TestL1DefaultCuatro(t *testing.T) {
	p := Pregunta{Kind: KindChoice, Texto: "¿Qué área?", Estado: "paquete retraso", Opciones: opsReembolso()}
	base := l1Con(t, nil, nil)
	sopl := soplL1(t, base, p, map[string]string{"facturacion": "paquete retraso"}, map[string]uint32{"facturacion": 4})
	conSopl := func(cfg Config) *L1 {
		cfg.CacheEsquemas, cfg.CacheRespuestas = 16, 16
		extra := []chispa3.Seccion{{Tipo: chispa3.SOPL1, Datos: sopl}}
		calib := calibTiny()
		calib.L1LambdaCalib = floatPtr(4) // calibrado con el λ por defecto: el soporte se usa sin λ en la config
		mt, err := ArmarDesde(v3Tiny(t, calib, extra...), NuevoL0(8), &cfg, false, nil)
		if err != nil {
			t.Fatal(err)
		}
		return mt.L1.(*L1)
	}
	ausente, cuatro, apagado := conSopl(Config{}), l1Con(t, sopl, floatPtr(4)), conSopl(Config{L1ShrinkageApagado: true})
	if !reflect.DeepEqual(ausente.opciones(p), cuatro.opciones(p)) {
		t.Fatal("λ ausente debe equivaler a λ=4")
	}
	if reflect.DeepEqual(ausente.opciones(p)["facturacion"], base.opciones(p)["facturacion"]) {
		t.Fatal("con el default 4 y SOPL1 el prototipo de facturacion debe moverse")
	}
	if !reflect.DeepEqual(apagado.opciones(p), base.opciones(p)) {
		t.Fatal("apagado explícito: igualdad exacta con el comportamiento anterior (sin soporte)")
	}
	rA, _ := apagado.Decidir(context.Background(), p)
	rB, _ := base.Decidir(context.Background(), p)
	if !reflect.DeepEqual(rA, rB) {
		t.Fatalf("apagado: %+v ≠ %+v", rA, rB)
	}
	if reflect.DeepEqual(conSopl(Config{L1ShrinkageLambda: floatPtr(1)}).opciones(p), ausente.opciones(p)) {
		t.Fatal("un λ explícito debe mandar sobre el default")
	}
	// .chispa sin SOPL1: el default no cambia nada.
	sin := l1Con(t, nil, nil)
	mt, err := ArmarDesde(v3Tiny(t, calibTiny()), NuevoL0(8), &Config{CacheEsquemas: 16, CacheRespuestas: 16}, false, nil)
	if err != nil || !reflect.DeepEqual(mt.L1.(*L1).opciones(p), sin.opciones(p)) {
		t.Fatalf("sin SOPL1 no debe cambiar: %v", err)
	}
}

func TestConfigJSONShrinkageApagado(t *testing.T) {
	escribir := func(js string) string {
		f := filepath.Join(t.TempDir(), "c.json")
		os.WriteFile(f, []byte(js), 0o644)
		return f
	}
	c, err := CargarConfig(escribir(`{"l1_shrinkage_apagado": true}`))
	if err != nil || c.LambdaL1() != nil {
		t.Fatalf("apagado por JSON: %v %v", c.LambdaL1(), err)
	}
	if c, err = CargarConfig(escribir(`{}`)); err != nil || c.LambdaL1() == nil || *c.LambdaL1() != 4 {
		t.Fatalf("ausente = 4: %v", err)
	}
	if c, err = CargarConfig(escribir(`{"l1_shrinkage_lambda": 0}`)); err != nil || *c.LambdaL1() != 0 {
		t.Fatalf("0 explícito manda: %v", err)
	}
	if _, err = CargarConfig(escribir(`{"l1_shrinkage_apagado": true, "l1_shrinkage_lambda": 1}`)); err == nil {
		t.Fatal("apagado + λ debe fallar")
	}
}
