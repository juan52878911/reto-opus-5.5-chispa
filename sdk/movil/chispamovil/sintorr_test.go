package chispamovil

import (
	"testing"

	"chispa/format/chispa3"
)

// Un .chispa sin sección TORR (L2 + ESQUEMAS): un esquema nuevo no tiene torres, no se instalan solas y L2 no opina.
func TestSinTORREsquemaNuevoNoInstalaTorresNiOpina(t *testing.T) {
	esq, err := chispa3.CodificarEsquemas(4, []chispa3.EntradaEsquema{
		{Hash: chispa3.HashEsquema("¿Qué quiere?", []string{"compra"}), Escala: 0.1, Vec: []int8{100, 0, 0, 0}},
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

	nuevo := `{"question":"esquema que no está en el fichero","kind":"choice","options":[{"id":"a"},{"id":"b"}]}`
	if c.TieneTorre() || c.OnnxTorre() != nil || c.DimTorre() != 0 {
		t.Fatal("sin TORR no debía haber torre")
	}
	if c.TorresL2(nuevo) {
		t.Fatal("esquema nuevo sin TORR ni InstalarTorresL2: TorresL2 debía ser false")
	}
	if r := leer(t, c.PuntuarL2(nuevo, make([]byte, 4*4*2), 2)); r.Opina {
		t.Fatalf("L2 sin torres no debía opinar: %+v", r)
	}
	if c.TextosTorreL2(nuevo) == "[]" {
		t.Fatal("los textos sí se piden: la app decide si puede calcularlos")
	}

	// n que no cuadra con los textos, o bytes mal dimensionados: false, sin pánico y sin dejar torres
	ok := torresBytes([]string{"a", "b"})
	for nombre, caso := range map[string]struct {
		b []byte
		n int
	}{"n de más": {ok, 3}, "n de menos": {ok, 1}, "n cero": {ok, 0}, "n negativo": {ok, -1}, "bytes sueltos": {ok[:len(ok)-1], 2}, "nil": {nil, 2}, "demasiado corto": {ok[:3], 2}} {
		if c.InstalarTorresL2(nuevo, caso.b, caso.n) || c.TorresL2(nuevo) {
			t.Fatalf("%s: debía rechazar", nombre)
		}
	}
}
