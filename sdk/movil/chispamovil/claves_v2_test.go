package chispamovil

import (
	"testing"

	"chispa/format/chispa3"
)

// Con ESQUEMAS v2 la clave incluye descripción y kind: otra descripción no encuentra las torres de ESQUEMAS.
func TestESQUEMASV2ClaveConDescripcion(t *testing.T) {
	ops := []opcion{{ID: "a", Description: "da"}, {ID: "b", Description: "db"}}
	var es []chispa3.EntradaEsquema2
	for _, o := range ops {
		es = append(es, chispa3.EntradaEsquema2{Hash: chispa3.HashEsquema2("¿q?", "choice", clavesDe([]opcion{o})), Escala: 1, Vec: []int8{1, 0}})
	}
	b, err := chispa3.CodificarEsquemas2(2, es)
	if err != nil {
		t.Fatal(err)
	}
	esq, err := chispa3.DecodificarEsquemas(b)
	if err != nil {
		t.Fatal(err)
	}
	c := &Chispa{esq: esq, tieneL2: true}
	p := pregunta{Texto: "¿q?", Kind: "choice", Opciones: ops}
	if ts, err := c.torresL2(p); err != nil || len(ts) != 2 {
		t.Fatalf("mismas descripciones: %v %v", ts, err)
	}
	p.Opciones = []opcion{{ID: "a", Description: "otra"}, {ID: "b", Description: "db"}}
	if _, err := c.torresL2(p); err == nil {
		t.Fatal("otra descripción debía ser un esquema nuevo (sin torres instaladas)")
	}
	p.Opciones, p.Kind = ops, "multi"
	if _, err := c.torresL2(p); err == nil {
		t.Fatal("otro kind debía ser un esquema nuevo")
	}
}
