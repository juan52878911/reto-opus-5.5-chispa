package decide

import (
	"context"
	"math"
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
	cfg := Config{CacheEsquemas: 16, CacheRespuestas: 16, L1ShrinkageLambda: lambda}
	mt, err := ArmarDesde(v3Tiny(t, calibTiny(), extra...), NuevoL0(8), &cfg, false, nil)
	if err != nil {
		t.Fatal(err)
	}
	return mt.L1.(*L1)
}

func floatPtr(x float64) *float64 { return &x }

func TestL1SoporteLambdaInfinitoNoCambiaNada(t *testing.T) {
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
	if c.L1ShrinkageLambda != nil || c.L2ShrinkageLambda != nil {
		t.Fatal("por defecto ∞ (nil)")
	}
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
