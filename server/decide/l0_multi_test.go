package decide

import (
	"bytes"
	"context"
	"strings"
	"testing"

	"chispa/format/chispa3"
)

func entradaL0(t *testing.T, nombre string) chispa3.EntradaL0 {
	t.Helper()
	s := l0DeTestdata(t, nombre)
	return chispa3.EntradaL0{Nombre: nombre, Tipo: s.Tipo, Datos: s.Datos}
}

// Un -modelo con L0MULTI (intención + urgencia, más el L0 de injection del propio fichero): ArmarDesde las añade todas al L0 y cada pregunta usa la suya.
func TestArmarDesdeL0Multi(t *testing.T) {
	secs, err := chispa3.SeccionesL0([]chispa3.EntradaL0{entradaL0(t, "intencion.chispa"), entradaL0(t, "urgencia.chispa")})
	if err != nil || len(secs) != 1 || secs[0].Tipo != chispa3.L0MULTI {
		t.Fatalf("secciones: %v %v", secs, err)
	}
	l0 := NuevoL0(8)
	cfg := ConfigPorDefecto()
	mt, err := ArmarDesde(v3Tiny(t, calibTiny(), secs...), l0, &cfg, false, nil)
	if err != nil {
		t.Fatal(err)
	}
	if l0.NumModelos() != 3 {
		t.Fatalf("modelos en L0: %d", l0.NumModelos())
	}
	casc, err := NuevaCascada(cfg.Capas, []Decisor{l0, mt.L1, mt.L2, NuevoL3()}, NuevasMetricas())
	if err != nil {
		t.Fatal(err)
	}
	r := casc.Decidir(context.Background(), preguntaIntencion())
	if r.Layer != "L0" || r.Answer != "soporte" || r.Escalate {
		t.Fatalf("respuesta: %+v", r)
	}
}

// v3Tiny ya trae un L0 (injection): un L0MULTI con las mismas etiquetas choca, nombrando los dos orígenes.
func TestArmarDesdeL0MultiRepetidoContraElL0(t *testing.T) {
	b, err := chispa3.CodificarL0Multi([]chispa3.EntradaL0{entradaL0(t, "injection.chispa"), entradaL0(t, "intencion.chispa")})
	if err != nil {
		t.Fatal(err)
	}
	cfg := ConfigPorDefecto()
	_, err = ArmarDesde(v3Tiny(t, calibTiny(), chispa3.Seccion{Tipo: chispa3.L0MULTI, Datos: b}), NuevoL0(8), &cfg, false, nil)
	if err == nil || !strings.Contains(err.Error(), "sección L0") || !strings.Contains(err.Error(), "injection.chispa") {
		t.Fatalf("error: %v", err)
	}
}

// Un fichero de «modelos» con L0MULTI aporta todas sus L0; choca con las del -modelo o con otro «modelos».
func TestModelosL0Multi(t *testing.T) {
	b, err := chispa3.CodificarL0Multi([]chispa3.EntradaL0{entradaL0(t, "intencion.chispa"), entradaL0(t, "urgencia.chispa")})
	if err != nil {
		t.Fatal(err)
	}
	ruta := escribirV3(t, "cliente.chispa", chispa3.Seccion{Tipo: chispa3.L0MULTI, Datos: b})
	l0 := NuevoL0(8)
	if err := l0.CargarCon(chispa3.Limites{}, ruta); err != nil {
		t.Fatal(err)
	}
	if l0.NumModelos() != 2 || len(l0.Avisos) != 0 {
		t.Fatalf("modelos %d, avisos %v", l0.NumModelos(), l0.Avisos)
	}
	// contra otro «modelos»
	otro := escribirV3(t, "urg.chispa", l0DeTestdata(t, "urgencia.chispa"))
	err = l0.CargarCon(chispa3.Limites{}, otro)
	if err == nil || !strings.Contains(err.Error(), "cliente.chispa") || !strings.Contains(err.Error(), "urg.chispa") {
		t.Fatalf("modelos repetidos: %v", err)
	}
	// contra el -modelo (v3Tiny trae injection) cuando «modelos» ya lo tiene dentro de un L0MULTI
	b2, _ := chispa3.CodificarL0Multi([]chispa3.EntradaL0{entradaL0(t, "injection.chispa"), entradaL0(t, "urgencia.chispa")})
	l02 := NuevoL0(8)
	if err := l02.CargarCon(chispa3.Limites{}, escribirV3(t, "m.chispa", chispa3.Seccion{Tipo: chispa3.L0MULTI, Datos: b2})); err != nil {
		t.Fatal(err)
	}
	cfg := ConfigPorDefecto()
	if _, err := ArmarDesde(v3Tiny(t, calibTiny()), l02, &cfg, false, nil); err == nil || !strings.Contains(err.Error(), "m.chispa") {
		t.Fatalf("contra -modelo: %v", err)
	}
	// con L1 dentro sigue siendo un error de «modelos», como antes
	if err := NuevoL0(8).CargarCon(chispa3.Limites{}, escribirV3(t, "x.chispa", chispa3.Seccion{Tipo: chispa3.L0MULTI, Datos: b}, chispa3.Seccion{Tipo: chispa3.L1, Datos: []byte{1}})); err == nil {
		t.Fatal("L1 en modelos")
	}
}

// escribirYAbrir serializa las secciones y abre el fichero en memoria.
func escribirYAbrir(t *testing.T, secs []chispa3.Seccion) *chispa3.Fichero {
	t.Helper()
	var buf bytes.Buffer
	if err := chispa3.Escribir(&buf, secs); err != nil {
		t.Fatal(err)
	}
	f, err := chispa3.Desde(buf.Bytes(), chispa3.Limites{})
	if err != nil {
		t.Fatal(err)
	}
	return f
}
