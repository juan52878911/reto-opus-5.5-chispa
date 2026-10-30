package decide

import (
	"sync"
	"testing"
)

// resultadoDorado serializa lo que decide una petición (capa suelta o cascada) para comparar sin tolerancia.
func resultadoDorado(t testing.TB, a *armadoDorado, p PeticionDorada) string {
	t.Helper()
	s, err := resultadoDoradoErr(a, p)
	if err != nil {
		t.Fatalf("%s: %v", p.ID, err)
	}
	return s
}

// resultadoDoradoErr devuelve el error en vez de abortar: apto para goroutines (sin t.Fatal fuera de la del test).
func resultadoDoradoErr(a *armadoDorado, p PeticionDorada) (string, error) {
	e, c, err := a.decidirErr(p)
	if err != nil {
		return "", err
	}
	if p.Capa == "cascada" {
		return mustJSON(c), nil
	}
	return mustJSON(e), nil
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
							got, err := resultadoDoradoErr(a, ps[i])
							if err != nil {
								errs <- ps[i].ID + ": error: " + err.Error()
							} else if got != ref[i] {
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
