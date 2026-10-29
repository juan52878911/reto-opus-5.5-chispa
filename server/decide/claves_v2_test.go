package decide

import (
	"context"
	"testing"

	"chispa/format/chispa3"
)

func esqV2(t *testing.T, p Pregunta) *chispa3.Esquemas {
	var es []chispa3.EntradaEsquema2
	for i, o := range p.Opciones {
		eje := []int8{0, 0}
		eje[i%2] = 1
		es = append(es, chispa3.EntradaEsquema2{Hash: chispa3.HashEsquema2(p.Texto, p.Kind, clavesDe([]Opcion{o})), Escala: 1, Vec: eje})
	}
	b, err := chispa3.CodificarEsquemas2(2, es)
	if err != nil {
		t.Fatal(err)
	}
	esq, err := chispa3.DecodificarEsquemas(b)
	if err != nil {
		t.Fatal(err)
	}
	return esq
}

// Con ESQUEMAS v2 la clave incluye descripción y kind: la misma pregunta con otra descripción es un esquema nuevo
// (torres al vuelo); con las mismas, sale de ESQUEMAS sin llamar al codificador de torres.
func TestESQUEMASV2OtraDescripcionEsEsquemaNuevo(t *testing.T) {
	p := Pregunta{Texto: "¿de qué trata?", Kind: KindChoice, Estado: "x",
		Opciones: []Opcion{{ID: "quejas", Description: "reclamos"}, {ID: "ventas", Description: "compras"}}}
	l := NuevoL2Con(sesionFalsa{[][]float32{{3, 0}}}, esqV2(t, p), chispa3.Calib{}, tokFalso{})
	tf := &torreFalsa{}
	l.ConTorres(tf, 16)

	r, err := l.Decidir(context.Background(), p)
	if err != nil || r.Answer != "quejas" || r.EsquemaNuevo || tf.n != 0 {
		t.Fatalf("mismas descripciones: %+v %v (%d torres al vuelo)", r, err, tf.n)
	}
	p2 := p
	p2.Opciones = []Opcion{{ID: "quejas", Description: "otra"}, {ID: "ventas", Description: "compras"}}
	r, err = l.Decidir(context.Background(), p2)
	if err != nil || !r.EsquemaNuevo || tf.n == 0 {
		t.Fatalf("otra descripción: %+v %v (%d torres al vuelo)", r, err, tf.n)
	}
	// Otro kind con las mismas opciones también es otro esquema.
	p3 := p
	p3.Kind = KindMulti
	if !l.esquemaNuevo(p3) {
		t.Fatal("multi con las torres de choice no debía salir de ESQUEMAS v2")
	}
	// Una clave v1 no entra en una sección v2.
	if _, _, ok := l.esq.Buscar(chispa3.HashEsquema(p.Texto, []string{"quejas"})); ok {
		t.Fatal("mezcla de claves")
	}
}

// El mismo esquema en v1 (clave sin descripción) sigue valiendo con otra descripción: compatibilidad intacta.
func TestESQUEMASV1SigueIgnorandoLaDescripcion(t *testing.T) {
	b, _ := chispa3.CodificarEsquemas(2, []chispa3.EntradaEsquema{ent("q", []string{"a"}, 1, 1, 0), ent("q", []string{"b"}, 1, 0, 1)})
	esq, _ := chispa3.DecodificarEsquemas(b)
	l := NuevoL2Con(sesionFalsa{[][]float32{{3, 0}}}, esq, chispa3.Calib{}, tokFalso{})
	p := Pregunta{Texto: "q", Kind: KindChoice, Estado: "x", Opciones: []Opcion{{ID: "a", Description: "d1"}, {ID: "b", Description: "d2"}}}
	if l.esquemaNuevo(p) {
		t.Fatal("v1 no encontró su clave")
	}
}

func TestCONJV2BuscaPorClaveV2(t *testing.T) {
	p := Pregunta{Texto: "¿q?", Kind: KindChoice, Opciones: []Opcion{{ID: "b", Description: "db"}, {ID: "a", Description: "da"}}}
	e := chispa3.EntradaConj{Hash2: chispa3.ClaveConj2(p.Texto, p.Kind, clavesDe(p.Opciones)), Cabeza: chispa3.CabezaLR, K: 1, D: 2,
		T: 0.05, Beta: 1, Esc: [3]float32{1, 1, 1}, W: make([]float32, chispa3.ConjPesosLR), Clases: []string{"a", "b"},
		Escala: make([]float32, 2), Proto: make([]byte, 4)}
	b, err := chispa3.CodificarConj2([]chispa3.EntradaConj{e})
	if err != nil {
		t.Fatal(err)
	}
	conj, err := chispa3.DecodificarConj(b)
	if err != nil {
		t.Fatal(err)
	}
	l := NuevoL2cCon(&L2{}, nil, conj)
	if _, ok := l.buscarConj(p); !ok {
		t.Fatal("CONJ v2 no encuentra su esquema (en otro orden de opciones)")
	}
	p.Opciones[0].Description = "otra"
	if _, ok := l.buscarConj(p); ok {
		t.Fatal("otra descripción debía ser otro esquema")
	}
}
