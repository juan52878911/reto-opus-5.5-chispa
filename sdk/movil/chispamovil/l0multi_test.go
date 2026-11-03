package chispamovil

import (
	"os"
	"strings"
	"testing"

	"chispa/format/chispa3"
)

func entradasL0Movil(t *testing.T, nombres ...string) []chispa3.EntradaL0 {
	t.Helper()
	var es []chispa3.EntradaL0
	for _, n := range nombres {
		b, err := os.ReadFile("../../../server/testdata/" + n)
		if err != nil {
			t.Skip("falta server/testdata/" + n)
		}
		es = append(es, chispa3.EntradaL0{Nombre: n, Tipo: chispa3.L0, Datos: b})
	}
	return es
}

// Un .chispa con L0MULTI: cada pregunta few-shot la contesta su L0.
func TestAbrirL0Multi(t *testing.T) {
	b, err := chispa3.CodificarL0Multi(entradasL0Movil(t, "urgencia.chispa", "intencion.chispa", "injection.chispa"))
	if err != nil {
		t.Fatal(err)
	}
	c, err := Abrir(escribirV3(t, append(metaYCalib(t), chispa3.Seccion{Tipo: chispa3.L0MULTI, Datos: b})))
	if err != nil {
		t.Fatal(err)
	}
	defer c.Cerrar()
	if len(c.l0) != 3 || c.Capas() != `["L0"]` {
		t.Fatalf("modelos %d, capas %s", len(c.l0), c.Capas())
	}
	for _, m := range c.l0 {
		ops := make([]string, len(m.m.Labels))
		for i, l := range m.m.Labels {
			ops[i] = `{"id":"` + l + `"}`
		}
		q := `{"question":"¿?","kind":"choice","options":[` + strings.Join(ops, ",") + `]}`
		r := leer(t, c.DecidirL0("necesito ayuda urgente, se me cae el techo", q))
		if !r.Ok || !r.Opina || len(r.Probs) != len(ops) {
			t.Fatalf("%v: %+v", m.m.Labels, r)
		}
	}
}

func TestAbrirL0MultiEtiquetasRepetidas(t *testing.T) {
	b, err := chispa3.CodificarL0Multi(entradasL0Movil(t, "urgencia.chispa", "urgencia.chispa"))
	if err != nil {
		t.Fatal(err)
	}
	_, err = Abrir(escribirV3(t, append(metaYCalib(t), chispa3.Seccion{Tipo: chispa3.L0MULTI, Datos: b})))
	if err == nil || !strings.Contains(err.Error(), "mismas etiquetas") {
		t.Fatalf("error: %v", err)
	}
}
