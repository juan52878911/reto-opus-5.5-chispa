package decide

import (
	"context"
	"strings"
	"testing"

	"chispa/format/chispa3"
)

// armarSinTorreZE monta un .chispa sin sección TORR (L2 + ESQUEMAS).
func armarSinTorreZE(t *testing.T, cfg Config) Montaje {
	t.Helper()
	esq, err := chispa3.CodificarEsquemas(2, []chispa3.EntradaEsquema{ent("solo en ESQUEMAS", []string{"a"}, 1, 1, 0)})
	if err != nil {
		t.Fatal(err)
	}
	f := v3Tiny(t, calibTiny(), chispa3.Seccion{Tipo: chispa3.L2, Datos: []byte("onnx-l2")}, chispa3.Seccion{Tipo: chispa3.ESQUEMAS, Datos: esq})
	mt, err := ArmarDesde(f, NuevoL0(8), &cfg, false, tokFalso{}, ConSesionS(sesionFalsa{[][]float32{{3, 0}}}))
	if err != nil {
		t.Fatal(err)
	}
	return mt
}

func tieneAvisoCache(av []string) bool {
	for _, a := range av {
		if strings.Contains(a, "cache_torres") {
			return true
		}
	}
	return false
}

// ZE: cache_torres 64 sin TORR arranca sin aviso ni ajuste.
func TestZECacheTorresSinTorrNoExigeNada(t *testing.T) {
	cfg := ConfigPorDefecto()
	cfg.CacheTorres = 64
	if err := cfg.Validar(); err != nil {
		t.Fatal(err)
	}
	buf := capturaLog(t)
	mt := armarSinTorreZE(t, cfg)
	if tieneAvisoCache(mt.Avisos) || strings.Contains(buf.String(), "cache_torres") {
		t.Fatalf("sin TORR no debe avisar: %q %q", mt.Avisos, buf.String())
	}
	c, _ := NuevaCascada([]Capa{{Nombre: "L2", Tau: 0.5}}, []Decisor{mt.L2}, NuevasMetricas())
	if cp := c.Capacidades(); cp.CacheTorresEfectiva != 0 || cp.CacheTorresAviso != "" {
		t.Fatalf("sin TORR no hay caché de torres: %+v", cp)
	}
}

// ZE: con TORR y cache_torres 64 sube a 384, con aviso en log, /healthz y métrica; no falla.
func TestZECacheTorresConTorrSube(t *testing.T) {
	buf := capturaLog(t)
	met := NuevasMetricas()
	mt := armarTorreZB(t, `{"version":1}`, chispa3.TextoTorreV1, Config{CacheEsquemas: 64, CacheTorres: 64})
	if !tieneAvisoCache(mt.Avisos) || !strings.Contains(buf.String(), "se sube a 384") {
		t.Fatalf("faltan avisos: %q log=%q", mt.Avisos, buf.String())
	}
	if ef, pe := mt.L2.(*L2).CacheTorresEfectiva(); ef != 384 || pe != 64 {
		t.Fatalf("efectiva=%d pedida=%d", ef, pe)
	}
	c, _ := NuevaCascada([]Capa{{Nombre: "L2", Tau: 0.5}}, []Decisor{mt.L2}, met)
	cp := c.Capacidades()
	if cp.CacheTorresEfectiva != 384 || !strings.Contains(cp.CacheTorresAviso, "64") {
		t.Fatalf("healthz: %+v", cp)
	}
	NuevoServidor(c, met, 8)
	var sb strings.Builder
	met.Escribe(&sb)
	for _, w := range []string{"chispa_cache_torres_efectiva 384", "chispa_cache_torres_ajustada 1"} {
		if !strings.Contains(sb.String(), w) {
			t.Errorf("falta %q en /metrics", w)
		}
	}
}

// ZE: con TORR y cache_torres suficiente (o por defecto) no hay ajuste.
func TestZECacheTorresConTorrSuficienteNoAvisa(t *testing.T) {
	for _, ct := range []int{0, 384, 1000} {
		mt := armarTorreZB(t, `{"version":1}`, chispa3.TextoTorreV1, Config{CacheEsquemas: 64, CacheTorres: ct})
		ef, pe := mt.L2.(*L2).CacheTorresEfectiva()
		if tieneAvisoCache(mt.Avisos) || pe != 0 || ef < 384 {
			t.Errorf("cache_torres=%d: avisos=%q ef=%d pe=%d", ct, mt.Avisos, ef, pe)
		}
	}
}

// ZE: con cache_torres 64, una pregunta de 256 opciones nuevas acaba opinando (la segunda vez sale de la caché).
func TestZEPregunta256ConCache64Opina(t *testing.T) {
	mt := armarTorreZB(t, `{"version":1}`, chispa3.TextoTorreV1, Config{CacheEsquemas: 64, CacheTorres: 64, MaxTorresNuevas: 256})
	l2 := mt.L2.(*L2)
	p := preguntaConOpciones(256)
	var r Respuesta
	for i := 0; i < 4 && (r.Conf == 0 || r.Incompleto); i++ {
		var err error
		if r, err = l2.Decidir(context.Background(), p); err != nil {
			t.Fatal(err)
		}
	}
	if r.Conf == 0 || r.Incompleto {
		t.Fatalf("256 opciones nuevas no acabaron opinando: %+v", r)
	}
}
