package decide

import (
	"sync"
	"testing"
)

// resultadoDorado serializa lo que decide una petición (capa suelta o cascada) para comparar sin tolerancia.
func resultadoDorado(t testing.TB, a *armadoDorado, p PeticionDorada) string {
	e, c := a.decidir(t, p)
	if p.Capa == "cascada" {
		return mustJSON(c)
	}
	return mustJSON(e)
}

// 64 goroutines con las mismas peticiones dan exactamente (bit a bit) las respuestas de 1, con las cachés frías (todas
// las goroutines arrancan a la vez sobre un armado nuevo) y calientes, y con una caché de esquemas de 2 entradas (desalojos).
func TestDoradosConcurrencia(t *testing.T) {
	var ps []PeticionDorada
	leerJSON(t, "peticiones.json", &ps)
	ref := make([]string, len(ps))
	a1 := armarDorados(t)
	for i, p := range ps {
		ref[i] = resultadoDorado(t, a1, p)
	}
	for _, c := range []struct {
		nombre string
		cola   int // 0: armado normal; >0: cachés de esquemas de ese tamaño
		rondas int
	}{{"frio", 0, 1}, {"caliente", 0, 3}, {"cache-minima", 2, 3}} {
		t.Run(c.nombre, func(t *testing.T) {
			a := armarDorados(t)
			if c.cola > 0 {
				a = armarDoradosCache(t, c.cola)
			}
			const N = 64
			var wg sync.WaitGroup
			errs := make(chan string, N*len(ps)*c.rondas)
			ini := make(chan struct{})
			for g := 0; g < N; g++ {
				wg.Add(1)
				go func(g int) {
					defer wg.Done()
					<-ini
					for r := 0; r < c.rondas; r++ {
						for k := range ps { // cada goroutine las recorre desde un punto distinto: choca con otras en las mismas claves de caché
							i := (k + g*7) % len(ps)
							if got := resultadoDorado(t, a, ps[i]); got != ref[i] {
								errs <- ps[i].ID + ": " + got + " ≠ " + ref[i]
							}
						}
					}
				}(g)
			}
			close(ini)
			wg.Wait()
			close(errs)
			n := 0
			for e := range errs {
				if n++; n <= 5 {
					t.Error(e)
				}
			}
			if n > 0 {
				t.Fatalf("%d respuestas distintas de las de 1 goroutine", n)
			}
		})
	}
}
