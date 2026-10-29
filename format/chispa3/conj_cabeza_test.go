package chispa3

import (
	"math"
	"math/rand/v2"
	"testing"
)

// dot3 y dot3x4 son exactos frente al producto entero ingenuo, también en los extremos (protos −128, S ±127).
func TestDot3Exacto(t *testing.T) {
	rnd := rand.New(rand.NewPCG(1, 2))
	for _, d := range []int{1, 2, 3, 4, 7, 256, 384, 1000} {
		w := (d + 2) / 3
		for _, modo := range []string{"azar", "max", "min"} {
			p, q := make([]int8, 4*d), make([][]int8, 4)
			for i := range p[:d] {
				switch modo {
				case "azar":
					p[i] = int8(rnd.IntN(256) - 128)
				case "max":
					p[i] = -128
				default:
					p[i] = 127
				}
			}
			var qp, qq [4][]int64
			qp[0] = make([]int64, w)
			for i := range qp[0] {
				var v [3]int8
				for k := 0; k < 3 && 3*i+k < d; k++ {
					v[k] = p[3*i+k]
				}
				qp[0][i] = empaquetar3(v[0], v[1], v[2])
			}
			var want [4]int64
			for s := range q {
				q[s] = make([]int8, d)
				for i := range q[s] {
					switch modo {
					case "azar":
						q[s][i] = int8(rnd.IntN(255) - 127)
					case "max":
						q[s][i] = -127
					default:
						q[s][i] = -127
					}
					want[s] += int64(p[i]) * int64(q[s][i])
				}
				qq[s] = make([]int64, w)
				for i := range qq[s] {
					g := func(k int) int8 {
						if k < d {
							return q[s][k]
						}
						return 0
					}
					qq[s][i] = empaquetar3(g(3*i+2), g(3*i+1), g(3*i))
				}
				if got := dot3(qp[0], qq[s]); got != want[s] {
					t.Fatalf("d=%d %s: dot3 %d, esperaba %d", d, modo, got, want[s])
				}
			}
			if got := dot3x4(qp[0], qq[0], qq[1], qq[2], qq[3]); got != want {
				t.Fatalf("d=%d %s: dot3x4 %v, esperaba %v", d, modo, got, want)
			}
		}
	}
}

// simproto cuantizado queda a ≤ 1e-2 (relativo a la escala de los valores) del cálculo en float, con y sin clases ausentes.
func TestSimprotoCercaDeLaReferencia(t *testing.T) {
	rnd := rand.New(rand.NewPCG(3, 4))
	for _, ns := range []int{1, 3, 4, 5, 16} {
		const C, K, D = 20, 8, 100
		e := EntradaConj{K: K, D: D}
		var ops []string
		for i := 0; i < C; i++ {
			id := string(rune('a' + i))
			e.Clases = append(e.Clases, id)
			ops = append(ops, id)
		}
		ops = append(ops, "zz")
		e.Escala, e.Proto = make([]float32, C*K), make([]byte, C*K*D)
		for i := range e.Escala {
			e.Escala[i] = 0.02 + rnd.Float32()*0.01
		}
		for i := range e.Proto {
			e.Proto[i] = byte(rnd.IntN(256))
		}
		S := make([][]float32, ns)
		for k := range S {
			S[k] = make([]float32, D)
			for j := range S[k] {
				S[k][j] = rnd.Float32()*2 - 1
			}
		}
		S[0][0] = 0 // incluye una ranura distinta de cero en todo lo demás
		got, want := Simproto(&e, S, ops), SimprotoRef(&e, S, ops)
		var maxv float64
		for _, v := range want {
			maxv = math.Max(maxv, math.Abs(v))
		}
		for i := range got {
			if math.Abs(got[i]-want[i]) > 1e-2*maxv {
				t.Fatalf("ns=%d opción %d: %v frente a %v", ns, i, got[i], want[i])
			}
		}
		if got[C] != 0 {
			t.Fatal("clase ausente debe valer 0")
		}
	}
}

// BenchmarkSimproto150 es el coste de simproto sola con 150 clases, K=16 prototipos, 16 ranuras de 256.
func BenchmarkSimproto150(b *testing.B) {
	const C, K, D = 150, 16, 256
	e := EntradaConj{K: K, D: D}
	var ops []string
	for i := 0; i < C; i++ {
		id := string(rune('A'+i/26)) + string(rune('a'+i%26))
		e.Clases = append(e.Clases, id)
		ops = append(ops, id)
	}
	e.Escala, e.Proto = make([]float32, C*K), make([]byte, C*K*D)
	for i := range e.Escala {
		e.Escala[i] = 0.01
	}
	for i := range e.Proto {
		e.Proto[i] = byte(i * 31)
	}
	S := make([][]float32, 16)
	for k := range S {
		S[k] = make([]float32, D)
		for j := range S[k] {
			S[k][j] = float32(j%5) / 5
		}
	}
	b.Run("entero", func(b *testing.B) {
		for i := 0; i < b.N; i++ {
			Simproto(&e, S, ops)
		}
	})
	b.Run("float", func(b *testing.B) {
		for i := 0; i < b.N; i++ {
			SimprotoRef(&e, S, ops)
		}
	})
}
