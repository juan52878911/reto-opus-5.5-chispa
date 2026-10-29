package decide

import (
	"context"

	"chispa/format/chispa3"
)

// Previas son las respuestas de las capas ya recorridas, por nombre de capa.
type Previas map[string]Respuesta

// DecisorConPrevias es un decisor que además usa lo que dijeron las capas anteriores (L2c lee las
// probabilidades de L0). La cascada llama a DecidirCon en vez de Decidir si el decisor lo implementa.
type DecisorConPrevias interface {
	Decisor
	DecidirCon(ctx context.Context, p Pregunta, previas Previas) (Respuesta, error)
}

// L2c es «L2 conjunta»: la cabeza lineal por esquema de la sección CONJ sobre las probabilidades de L0 y las
// similitudes de L2 con soporte (prototipos de los ejemplos del cliente). Sin entrada en CONJ para el esquema,
// sin probabilidades de L0 o fuera de choice, se comporta como L2. Se llama «L2» en la cascada y en la config.
type L2c struct {
	*L2
	sim  Similitudes
	conj *chispa3.Conj
}

// NuevoL2cCon monta L2c sobre cualquier fuente de similitudes (el ONNX real solo existe con la etiqueta ort).
func NuevoL2cCon(base *L2, sim Similitudes, conj *chispa3.Conj) *L2c {
	return &L2c{L2: base, sim: sim, conj: conj}
}

func (l *L2c) Nombre() string { return "L2" }

func (l *L2c) Decidir(ctx context.Context, p Pregunta) (Respuesta, error) {
	return l.DecidirCon(ctx, p, nil)
}

// ClaveConj es el hash del esquema en CONJ: la pregunta y los ids de las opciones, ordenados.
func ClaveConj(p Pregunta) [32]byte {
	ids := make([]string, len(p.Opciones))
	for i, o := range p.Opciones {
		ids[i] = o.ID
	}
	return chispa3.ClaveConj(p.Texto, ids)
}

func (l *L2c) DecidirCon(ctx context.Context, p Pregunta, previas Previas) (Respuesta, error) {
	if p.Kind != KindChoice || len(p.Opciones) == 0 {
		return l.L2.Decidir(ctx, p)
	}
	e, ok := l.conj.Buscar(ClaveConj(p))
	l0, hay := previas["L0"]
	if !ok || !hay || len(l0.Probs) == 0 {
		return l.L2.Decidir(ctx, p)
	}
	S, sims, ok, err := l.sim.Similitudes(ctx, p)
	if err != nil || !ok {
		return Respuesta{}, err
	}
	if len(S) == 0 || len(S[0]) != e.D {
		return l.L2.Decidir(ctx, p)
	}
	return cabezaConj(p, e, S, sims, l0.Probs), nil
}

// cabezaConj pone la cabeza de CONJ (chispa3.EntradaConj.ProbsCabeza, compartida con el SDK móvil) en una Respuesta.
func cabezaConj(p Pregunta, e *chispa3.EntradaConj, S [][]float32, sims []float64, l0 map[string]float64) Respuesta {
	ids := make([]string, len(p.Opciones))
	for i, o := range p.Opciones {
		ids[i] = o.ID
	}
	pr := e.ProbsCabeza(ids, S, sims, l0)
	r := Respuesta{Probs: make(map[string]float64, len(pr))}
	for i, id := range ids {
		r.Probs[id] = pr[i]
		if pr[i] > r.Conf {
			r.Conf, r.Answer = pr[i], id
		}
	}
	return r
}
