package decide

import (
	"bytes"
	"strings"
	"testing"

	"chispa/format/chispa3"
)

// Fichero que escribió `chispa train --conjunta` (sdk/python/tests/test_conjunta_v2.py, CHISPA_REGENERAR=1): ESQUEMAS v2 y CONJ v2.
const ficheroConjV2 = "testdata/conj-v2.chispa"

func preguntaConjV2() Pregunta {
	return Pregunta{ID: "urg", Texto: "¿Qué tan urgente es?", Kind: KindChoice, Opciones: []Opcion{
		{ID: "baja", Description: "Puede esperar"}, {ID: "alta", Description: "Requiere atención inmediata"}}}
}

func armarConjV2(t *testing.T, f *chispa3.Fichero) Montaje {
	t.Helper()
	mt, err := ArmarDesde(f, NuevoL0(8), &Config{CacheEsquemas: 8}, false, tokFalso{}, ConSesionS(sesionFalsa{[][]float32{{1, 0}}}))
	if err != nil {
		t.Fatal(err)
	}
	return mt
}

func TestConjV2DeTrainEncuentraElEsquemaEnL2c(t *testing.T) {
	f, err := chispa3.Abrir(ficheroConjV2)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	esq, err := f.Esquemas()
	if err != nil {
		t.Fatal(err)
	}
	conj, err := f.Conj()
	if err != nil {
		t.Fatal(err)
	}
	if esq.Version() != 2 || conj.Version() != 2 {
		t.Fatalf("versiones ESQUEMAS v%d CONJ v%d, se esperaba v2 las dos", esq.Version(), conj.Version())
	}
	p := preguntaConjV2()
	if _, ok := conj.BuscarEsquema(p.Texto, p.Kind, clavesDe(p.Opciones)); !ok {
		t.Fatal("CONJ v2 no encuentra el esquema con HashEsquema2")
	}
	if _, _, ok := esq.BuscarEsquema(p.Texto, p.Kind, clavesDe(p.Opciones)); !ok {
		t.Fatal("ESQUEMAS v2 no encuentra el esquema con la misma clave")
	}
	mt := armarConjV2(t, f)
	for _, a := range mt.Avisos {
		if strings.Contains(a, "CONJ v") {
			t.Fatalf("aviso de versiones con ficheros consistentes: %q", a)
		}
	}
	l2c, ok := mt.L2.(*L2c)
	if !ok {
		t.Fatalf("L2 es %T, se esperaba *L2c", mt.L2)
	}
	if _, ok := l2c.buscarConj(p); !ok {
		t.Fatal("L2c no encuentra la cabeza del esquema")
	}
	p.Opciones[0].Description = "otra"
	if _, ok := l2c.buscarConj(p); ok {
		t.Fatal("otra descripción debía ser otro esquema")
	}
}

func TestAvisoSiEsquemasYConjDifierenDeVersion(t *testing.T) {
	f, err := chispa3.Abrir(ficheroConjV2)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	p := preguntaConjV2()
	ids := []string{"alta", "baja"}
	vec := make([]int8, 256)
	esq1, err := chispa3.CodificarEsquemas(256, []chispa3.EntradaEsquema{{Hash: chispa3.HashEsquema(p.Texto, ids), Escala: 1, Vec: vec}})
	if err != nil {
		t.Fatal(err)
	}
	var secs []chispa3.Seccion
	for _, tp := range f.Tipos() {
		b, err := f.Bytes(tp)
		if err != nil {
			t.Fatal(err)
		}
		if tp == chispa3.ESQUEMAS {
			b = esq1
		}
		secs = append(secs, chispa3.Seccion{Tipo: tp, Datos: b})
	}
	var buf bytes.Buffer
	if err := chispa3.Escribir(&buf, secs); err != nil {
		t.Fatal(err)
	}
	mixto, err := chispa3.Desde(buf.Bytes(), chispa3.Limites{})
	if err != nil {
		t.Fatal(err)
	}
	mt := armarConjV2(t, mixto)
	avisado := false
	for _, a := range mt.Avisos {
		avisado = avisado || strings.Contains(a, "ESQUEMAS v1 y CONJ v2")
	}
	if !avisado {
		t.Fatalf("sin aviso de versiones distintas: %q", mt.Avisos)
	}
}
