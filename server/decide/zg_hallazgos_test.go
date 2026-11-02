package decide

import (
	"strings"
	"testing"
	"time"

	"chispa/format/chispa3"
)

// ZG-1: al recargar con otra tasa el cubo viejo apunta al nuevo; el total gastado no pasa de la ráfaga.
func TestZGCuboSucesorSinRafagaDoble(t *testing.T) {
	ahora := time.Unix(1000, 0)
	reloj := func() time.Time { return ahora }
	viejo := nuevoCuboTorresReloj(10, reloj)
	for i := 0; i < 1; i++ {
		viejo.toma(10) // llena y gasta una: quedan 9
	}
	nuevo := nuevoCuboTorresReloj(11, reloj)
	nuevo.hereda(viejo)
	total := 0
	for i := 0; i < 100; i++ {
		if viejo.toma(10) { // petición en vuelo: cobra del viejo
			total++
		}
		if nuevo.toma(11) {
			total++
		}
	}
	if total > 9 {
		t.Fatalf("gastó %d con 9 fichas heredadas (antes: 19)", total)
	}
	viejo.devuelve(10) // lo que deshace devuelve va a la cuenta vigente
	if !nuevo.toma(11) {
		t.Fatal("la ficha devuelta al cubo viejo debe verse en el nuevo")
	}
}

// ZG-1 (clave): lo mismo por clave de API al cambiar torres_por_segundo.
func TestZGCuboClaveSucesor(t *testing.T) {
	ahora := time.Unix(1000, 0)
	reloj := func() time.Time { return ahora }
	a := nuevoAutenticador([]ClaveAPI{{ID: "a", HashSHA256: "00", RPS: 1, TorresPorSegundo: 10}}, reloj)
	a.claves[0].torres.toma(10)
	b := nuevoAutenticadorDe([]ClaveAPI{{ID: "a", HashSHA256: "00", RPS: 1, TorresPorSegundo: 11}}, reloj, a)
	total := 0
	for i := 0; i < 100; i++ { // petición en vuelo con el cubo viejo + peticiones nuevas
		if a.claves[0].torres.toma(10) {
			total++
		}
		if b.claves[0].torres.toma(11) {
			total++
		}
	}
	if total > 9 {
		t.Fatalf("gastó %d, quedaban 9 fichas", total)
	}
}

// ZG-2: sin TORR, cualquier max_opciones válido arranca; la config valida.
func TestZGMaxOpcionesSinTopeEnConfig(t *testing.T) {
	c := ConfigPorDefecto()
	c.Limites.MaxOpciones = MaxOpcionesTope * 3
	if err := c.Validar(); err != nil {
		t.Fatalf("ninguna config válida debe dejar de arrancar: %v", err)
	}
}

// ZG-2: con TORR y max_opciones > 4096, la torre al vuelo se desactiva con aviso y motivo, sin fallar.
func TestZGMaxOpcionesExcesivoDesactivaTorre(t *testing.T) {
	cfg := Config{CacheEsquemas: 64, Limites: Limites{MaxOpciones: MaxOpcionesTope + 1}}
	mt := armarTorreZB(t, `{"version":1}`, chispa3.TextoTorreV1, cfg)
	l2 := mt.L2.(*L2)
	if l2.torres != nil || l2.MotivoSinTorre() != MotivoMaxOpcionesExcesivo {
		t.Fatalf("torres=%v motivo=%q", l2.torres, l2.MotivoSinTorre())
	}
	if !strings.Contains(strings.Join(mt.Avisos, "\n"), MotivoMaxOpcionesExcesivo) {
		t.Fatalf("sin aviso: %v", mt.Avisos)
	}
	m := NuevasMetricas()
	m.FijaTorreMotivo(l2.MotivoSinTorre())
	var sb strings.Builder
	m.Escribe(&sb)
	if !strings.Contains(sb.String(), `chispa_torre_al_vuelo_desactivada{motivo="max_opciones_excesivo"} 1`) {
		t.Fatal("falta el gauge")
	}
	cfg.Limites.MaxOpciones = MaxOpcionesTope
	if l := armarTorreZB(t, `{"version":1}`, chispa3.TextoTorreV1, cfg).L2.(*L2); l.torres == nil || l.MotivoSinTorre() != "" {
		t.Fatal("en el máximo exacto la torre sigue activa")
	}
}

// ZG-5: con dim 1024 el tope de bytes de un fragmento admite una pregunta entera de max_opciones.
func TestZGCosteTorreConDimReal(t *testing.T) {
	const dim, maxOp = 1024, 2048
	b, err := chispa3.CodificarEsquemas(dim, []chispa3.EntradaEsquema{ent("zzz", []string{"a"}, 1, make([]int8, dim)...)})
	if err != nil {
		t.Fatal(err)
	}
	esq, _ := chispa3.DecodificarEsquemas(b)
	l := NuevoL2Con(sesionFalsa{[][]float32{{3, 0}}}, esq, chispa3.Calib{}, tokFalso{}).ConTorres(&codificadorHash{}, fragmentos*maxOp)
	f := l.cache.frag[0]
	if need := maxOp * (dim + 4 + 24 + 32 + sobreEntrada); f.maxBytes < need {
		t.Fatalf("tope de fragmento %d < %d de una pregunta entera", f.maxBytes, need)
	}
}
