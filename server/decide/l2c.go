package decide

import (
	"context"
	"errors"

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

	sopl   *chispa3.Sopl1 // k por opción (SOPL1), o nil
	lambda *float64       // κ ≡ λ del encogimiento de L2; nil = apagado; 0 = solo ejemplos; +Inf = solo descripción
}

// ConSoporte activa el shrinkage de G.8 en L2c (κ ≡ λ; ver chispa3.SimprotoMezclado): con una pregunta presente en sopl, los
// prototipos de cada opción con k > 0 son Q_j = λ_c·torre + (1−λ_c)·ranura_j de CONJ, λ_c = λ/(λ+k) con el k de SOPL1,
// normalizados por ranura; solo cambia el simproto (sim_opción, el MaxSim de la torre, queda igual). Con SOPL1 v2 la media lleva
// la norma de cada ranura (como modelo.py). lambda nil = apagado (L2c como estaba); λ = 0 = solo ejemplos; λ = +Inf = solo descripción
// (antes +Inf apagaba). Antes de usarla.
func (l *L2c) ConSoporte(sopl *chispa3.Sopl1, lambda *float64) *L2c {
	l.sopl, l.lambda = sopl, lambda
	return l
}

// NuevoL2cCon monta L2c sobre cualquier fuente de similitudes (el ONNX real solo existe con la etiqueta ort).
func NuevoL2cCon(base *L2, sim Similitudes, conj *chispa3.Conj) *L2c {
	return &L2c{L2: base, sim: sim, conj: conj}
}

func (l *L2c) Nombre() string { return "L2" }

func (l *L2c) Decidir(ctx context.Context, p Pregunta) (Respuesta, error) {
	return l.DecidirCon(ctx, p, nil)
}

// buscarConj busca la cabeza del esquema con la clave de la versión de CONJ (v1: ids ordenados; v2: HashEsquema2).
func (l *L2c) buscarConj(p Pregunta) (*chispa3.EntradaConj, bool) {
	return l.conj.BuscarEsquema(p.Texto, p.Kind, clavesDe(p.Opciones))
}

// ClaveConj es la clave v1 del esquema en CONJ y la de SOPL1 (que no cambia): la pregunta y los ids de las opciones, ordenados.
func ClaveConj(p Pregunta) [32]byte {
	ids := make([]string, len(p.Opciones))
	for i, o := range p.Opciones {
		ids[i] = o.ID
	}
	return chispa3.ClaveConj(p.Texto, ids)
}

func (l *L2c) DecidirCon(ctx context.Context, p Pregunta, previas Previas) (Respuesta, error) {
	r, _, err := l.DecidirConOrigen(ctx, p, previas)
	return r, err
}

// DecisorConRespaldo es un decisor que dice si su respuesta es de respaldo: la de otra cabeza (L2 base) con otra
// calibración que la del τ de la capa. La cascada lo usa para aplicar TauRespaldo a esas respuestas.
type DecisorConRespaldo interface {
	DecisorConPrevias
	DecidirConOrigen(ctx context.Context, p Pregunta, previas Previas) (r Respuesta, respaldo bool, err error)
	// TauRespaldo es el τ de las respuestas de respaldo y el τ de la cabeza al que sustituye (la capa solo lo aplica si
	// su τ efectivo es ese: si el operador fijó otro τ en la config, vale para todas las respuestas).
	TauRespaldo() (tau, tauCabeza float64, ok bool)
}

// TauRespaldo: las respuestas de L2 base que L2c da cuando no hay cabeza (sin entrada en CONJ, sin probabilidades de L0,
// dimensión distinta o tipo ≠ choice) están calibradas por tipos_l2 y se cortan con tau_escalate_l2, no con tau_l2c.
// ok=false si CALIB no trae tau_l2c (entonces ya es el mismo τ).
func (l *L2c) TauRespaldo() (tau, tauCabeza float64, ok bool) {
	if l.L2 == nil || l.L2.calib.TauL2c == nil {
		return 0, 0, false
	}
	return l.L2.calib.TauEscalate, *l.L2.calib.TauL2c, true
}

// DecidirConOrigen es DecidirCon más si la respuesta es de respaldo (la dio L2 base y no la cabeza conjunta).
func (l *L2c) DecidirConOrigen(ctx context.Context, p Pregunta, previas Previas) (Respuesta, bool, error) {
	r, respaldo, err := l.decidirCon(ctx, p, previas)
	r, err = l.L2.marcarNuevo(p, r, err)
	return r, respaldo, err
}

func (l *L2c) decidirCon(ctx context.Context, p Pregunta, previas Previas) (Respuesta, bool, error) {
	if p.Kind != KindChoice || len(p.Opciones) == 0 {
		r, err := l.L2.Decidir(ctx, p)
		return r, true, err
	}
	e, ok := l.buscarConj(p)
	l0, hay := previas["L0"]
	if !ok || !hay || len(l0.Probs) == 0 {
		r, err := l.L2.Decidir(ctx, p)
		return r, true, err
	}
	var ts []torreDin // las torres con las que puntuó la fuente de similitudes, si las expone
	var vs []ventana
	var S [][]float32
	var sims []float64
	var err error
	if sv, conVentanas := l.sim.(interface {
		similitudesVentanas(context.Context, Pregunta) ([]ventana, []torreDin, bool, error)
	}); conVentanas {
		vs, ts, ok, err = sv.similitudesVentanas(ctx, p)
		if len(vs) > 0 {
			S, sims = vs[0].S, vs[0].sims
		}
	} else if st, conTorres := l.sim.(interface {
		similitudesTorres(context.Context, Pregunta) ([][]float32, []float64, []torreDin, bool, error)
	}); conTorres {
		S, sims, ts, ok, err = st.similitudesTorres(ctx, p)
	} else {
		S, sims, ok, err = l.sim.Similitudes(ctx, p)
	}
	if errors.Is(err, errSinPresupuestoTorres) { // como en L2.decidir: falta de presupuesto es Incompleto, no error de capa
		return Respuesta{Incompleto: true}, false, nil
	}
	if err != nil || !ok {
		return Respuesta{}, false, err
	}
	if len(S) == 0 || len(S[0]) != e.D {
		r, err := l.L2.Decidir(ctx, p)
		return r, true, err
	}
	if len(vs) <= 1 {
		return cabezaConj(p, e, S, sims, l.mezclarSimproto(p, S, ts), l0.Probs), false, nil
	}
	// texto largo con trozos: la cabeza conjunta decide cada ventana (con las mismas probabilidades de L0) y se agregan
	rs := make([]Respuesta, len(vs))
	for i, v := range vs {
		rs[i] = cabezaConj(p, e, v.S, v.sims, l.mezclarSimproto(p, v.S, ts), l0.Probs)
	}
	return agregarRespuestas(p, rs, l.L2.largo.Agg(), 0.5), false, nil
}

// torreDe devuelve la torre de la descripción de la opción: la de ESQUEMAS o, si el esquema es nuevo, la que L2 acaba de
// calcular al vuelo (sigue en la caché; si se desalojó, ok=false y esa opción no se mezcla).
func (l *L2c) torreDe(p Pregunta, o Opcion) (vec []byte, escala float32, ok bool) {
	if l.L2 == nil {
		return nil, 0, false
	}
	if v, esc, ok := buscarTorre(l.esq, p, []Opcion{o}); ok {
		return v, esc, true
	}
	if l.cache != nil {
		if t, ok := l.cache.Get(claveTorre(p.Texto, o)); ok {
			return t.v, t.e, true
		}
	}
	return nil, 0, false
}

// mezclarSimproto aplica chispa3.SimprotoMezclado (shrinkage de G.8 sobre los prototipos, κ ≡ λ) si hay λ y SOPL1 con la
// pregunta; si no, devuelve nil y la cabeza usa el simproto de CONJ: el comportamiento de antes.
func (l *L2c) mezclarSimproto(p Pregunta, S [][]float32, ts []torreDin) []float64 {
	if l.sopl == nil || l.lambda == nil {
		return nil
	}
	sop, ok := l.sopl.Buscar(ClaveConj(p))
	if !ok {
		return nil
	}
	e, ok := l.buscarConj(p)
	if !ok {
		return nil
	}
	ids := make([]string, len(p.Opciones))
	for i, o := range p.Opciones {
		ids[i] = o.ID
	}
	return chispa3.SimprotoMezclado(e, sop, l.lambda, ids, S, func(i int) ([]byte, float32, bool) {
		if len(ts) == len(p.Opciones) { // la misma torre que puntuó: determinista y como en el móvil
			return ts[i].v, ts[i].e, true
		}
		return l.torreDe(p, p.Opciones[i])
	})
}

// cabezaConj pone la cabeza de CONJ (chispa3.EntradaConj.ProbsCabeza, compartida con el SDK móvil) en una Respuesta.
func cabezaConj(p Pregunta, e *chispa3.EntradaConj, S [][]float32, sims, sp []float64, l0 map[string]float64) Respuesta {
	ids := make([]string, len(p.Opciones))
	for i, o := range p.Opciones {
		ids[i] = o.ID
	}
	pr := e.ProbsCabezaSp(ids, S, sims, l0, sp)
	r := Respuesta{Probs: make(map[string]float64, len(pr))}
	for i, id := range ids {
		r.Probs[id] = pr[i]
		if pr[i] > r.Conf {
			r.Conf, r.Answer = pr[i], id
		}
	}
	return r
}
