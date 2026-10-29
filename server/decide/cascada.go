package decide

import (
	"context"
	"fmt"
	"time"
)

// Resultado es la decisión final de una pregunta.
type Resultado struct {
	ID       string             `json:"id"`
	Kind     string             `json:"kind"`
	Answer   string             `json:"answer"`
	Probs    map[string]float64 `json:"probs"`
	Layer    string             `json:"layer"`
	Escalate bool               `json:"escalate"`
	Ms       float64            `json:"ms"`
	Nonce    string             `json:"nonce,omitempty"`
	// Incompleto: una capa falló o el ctx se canceló; no debe guardarse bajo un nonce.
	Incompleto bool `json:"-"`
}

// CapaEscalar es el valor de «layer» cuando ninguna capa acepta: no contestó ninguna, así que no se atribuye a la última.
const CapaEscalar = "escalar"

type capa struct {
	d   Decisor
	tau float64
	// tauNuevo, si no es nil, sustituye a tau cuando la respuesta de la capa trae EsquemaNuevo.
	tauNuevo *float64
}

// Cascada pasa por las capas en orden mientras la confianza top-1 sea < τ.
type Cascada struct {
	capas []capa
	met   *Metricas
	// tauNuevo es el τ de esquema nuevo de la config; el gauge lo fija Recargar al hacer el cambio (nuevoVivo), no el armado.
	tauNuevo *float64
}

// NuevaCascada empareja decisores y umbrales por posición y nombre.
func NuevaCascada(cfg []Capa, ds []Decisor, met *Metricas) (*Cascada, error) {
	return NuevaCascadaConTauNuevo(cfg, ds, met, nil)
}

// NuevaCascadaConTauNuevo es NuevaCascada con un τ propio para L2 cuando la pregunta no estaba en ESQUEMAS
// (tauNuevo nil = el de la capa, como antes).
func NuevaCascadaConTauNuevo(cfg []Capa, ds []Decisor, met *Metricas, tauNuevo *float64) (*Cascada, error) {
	if len(cfg) != len(ds) || len(ds) == 0 {
		return nil, fmt.Errorf("cascada: %d capas en la config y %d decisores", len(cfg), len(ds))
	}
	c := &Cascada{met: met, tauNuevo: tauNuevo}
	for i, d := range ds {
		if u, ok := d.(UsaMetricas); ok && met != nil {
			u.UsaMetricas(met)
		}
		if d.Nombre() != cfg[i].Nombre {
			return nil, fmt.Errorf("cascada: la capa %d es %s pero la config dice %s", i, d.Nombre(), cfg[i].Nombre)
		}
		cp := capa{d: d, tau: cfg[i].Tau}
		if cfg[i].Nombre == "L2" {
			cp.tauNuevo = tauNuevo
		}
		c.capas = append(c.capas, cp)
	}
	return c, nil
}

// Decidir recorre las capas. Si una falla o no opina, se pasa a la siguiente.
// Si ninguna alcanza su τ, la cascada escala con layer «escalar»: la respuesta es la de mayor
// confianza vista (pista para quien reciba la escalada).
func (c *Cascada) Decidir(ctx context.Context, p Pregunta) Resultado {
	t0 := time.Now()
	res := Resultado{ID: p.ID, Kind: p.Kind, Nonce: p.Nonce, Probs: map[string]float64{}}
	var mejor Respuesta
	previas := Previas{}
	ctx = conPresupuesto(ctx)
	for _, l := range c.capas {
		if ctx.Err() != nil {
			res.Incompleto = true
			break
		}
		t := time.Now()
		var r Respuesta
		var err error
		if cp, ok := l.d.(DecisorConPrevias); ok {
			r, err = cp.DecidirCon(ctx, p, previas)
		} else {
			r, err = l.d.Decidir(ctx, p)
		}
		c.met.ObservaCapa(l.d.Nombre(), time.Since(t), err)
		if err != nil || ctx.Err() != nil {
			res.Incompleto = true
			r = Respuesta{}
		}
		previas[l.d.Nombre()] = r
		if r.Conf > mejor.Conf {
			mejor = r
		}
		tau := l.tau
		if r.EsquemaNuevo {
			c.met.EsquemaNuevoPreguntas.Add(1)
			if l.tauNuevo != nil {
				tau = *l.tauNuevo
			}
		}
		if r.Conf > 0 && r.Conf >= tau {
			if r.EsquemaNuevo {
				c.met.EsquemaNuevoDecididas.Add(1)
			}
			res.Answer, res.Probs, res.Layer = r.Answer, r.Probs, l.d.Nombre()
			c.met.Decidida(res.Layer, false)
			res.Ms = ms(time.Since(t0))
			return res
		}
	}
	res.Escalate = true
	res.Layer = CapaEscalar
	res.Answer = mejor.Answer
	if mejor.Probs != nil {
		res.Probs = mejor.Probs
	}
	c.met.Decidida(res.Layer, true)
	res.Ms = ms(time.Since(t0))
	return res
}

func ms(d time.Duration) float64 { return float64(d.Microseconds()) / 1000 }
