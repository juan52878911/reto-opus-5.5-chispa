package decide

import (
	"testing"
	"time"
)

// R22-5: recarga con la misma tasa reutiliza el cubo (y el de la clave); R22-6: el cubo de clave usa el reloj inyectado.
func TestR22CubosReutilizadosYRelojInyectado(t *testing.T) {
	g := nuevoCuboTorres(10)
	l := l2Torres(t, &codificadorContador{}, 64).ConTorresPorSegundo(10)
	l.adoptaCubo(g)
	if l.cubo != g {
		t.Fatal("misma tasa: debe reutilizarse el puntero del cubo global")
	}
	l = l2Torres(t, &codificadorContador{}, 64).ConTorresPorSegundo(20)
	l.adoptaCubo(g)
	if l.cubo == g {
		t.Fatal("otra tasa: cubo nuevo")
	}
	t0 := time.Unix(1000, 0)
	ahora := t0
	reloj := func() time.Time { return ahora }
	a := nuevoAutenticador([]ClaveAPI{{ID: "a", HashSHA256: "00", RPS: 1, TorresPorSegundo: 1}}, reloj)
	k := a.claves[0].torres
	if !k.toma(1) || k.toma(1) {
		t.Fatal("ráfaga 1: una ficha y luego vacío")
	}
	ahora = t0.Add(time.Second)
	if !k.toma(1) {
		t.Fatal("con el reloj inyectado, un segundo repone una ficha")
	}
	b := nuevoAutenticadorDe([]ClaveAPI{{ID: "a", HashSHA256: "00", RPS: 1, TorresPorSegundo: 1}}, nil, a)
	if b.claves[0].torres != k {
		t.Fatal("misma tasa: la clave reutiliza su cubo")
	}
}

// R22-2 (ZG-2): el máximo de max_opciones ya no está en la config (ver TestZGMaxOpcionesExcesivoDesactivaTorre): nada válido deja de arrancar.
func TestR22MaxOpcionesAcotado(t *testing.T) {
	c := ConfigPorDefecto()
	c.Limites.MaxOpciones = MaxOpcionesTope
	if err := c.Validar(); err != nil {
		t.Fatal(err)
	}
	c.Limites.MaxOpciones = MaxOpcionesTope + 1
	if err := c.Validar(); err != nil {
		t.Fatalf("por encima del máximo solo se desactiva la torre al vuelo: %v", err)
	}
}
