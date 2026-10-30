package decide

import (
	"context"
	"encoding/json"
	"fmt"
	"time"
)

// Resultado es la decisión final de una pregunta.
type Resultado struct {
	ID     string             `json:"id"`
	Kind   string             `json:"kind"`
	Answer string             `json:"answer"`
	Probs  map[string]float64 `json:"probs"`
	// Answers: solo en multi, las opciones activas (puede ir vacía); en los demás tipos no sale.
	Answers  []string `json:"answers,omitempty"`
	Layer    string   `json:"layer"`
	Escalate bool     `json:"escalate"`
	Ms       float64  `json:"ms"`
	Nonce    string   `json:"nonce,omitempty"`
	// Incompleto: una capa falló o el ctx se canceló; no debe guardarse bajo un nonce.
	Incompleto bool `json:"-"`
}

// MarshalJSON añade «answers» solo en multi (y siempre, aunque vacía: [] = ninguna opción activa).
func (r Resultado) MarshalJSON() ([]byte, error) {
	type plano Resultado // sin métodos: evita la recursión
	out := struct {
		plano
		Answers *[]string `json:"answers,omitempty"`
	}{plano: plano(r)}
	if r.Kind == KindMulti {
		a := r.Answers
		if a == nil {
			a = []string{}
		}
		out.Answers = &a
	}
	return json.Marshal(out)
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
	// vistas son las vistas de CALIB (con los τ efectivos) preparadas al armar; PublicaCalib las pone en /metrics.
	vistas map[string]VistaCalib
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
	// Las vistas de CALIB se preparan aparte: /metrics sigue mostrando las del modelo en servicio hasta PublicaCalib.
	met.iniciaPrepCalib()
	cerrada := false
	defer func() {
		if !cerrada {
			met.cierraPrepCalib()
		}
	}()
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
	c.publicaTaus(cfg)
	c.vistas = met.cierraPrepCalib()
	cerrada = true
	return c, nil
}

// PublicaCalib pone en /metrics la CALIB y los τ de esta cascada, y quita las series de las capas que ya no están. Se llama
// cuando la cascada ya está en servicio (arranque y Recargar tras sustituir el modelo), nunca al armarla.
func (c *Cascada) PublicaCalib() {
	if c == nil || c.met == nil {
		return
	}
	c.met.publicaCalib(c.vistas)
}

// publicaTaus pone en chispa_calib_tau los τ efectivos de L1 y L2 (config > CALIB > default) con su origen, y el τ de esquema nuevo.
func (c *Cascada) publicaTaus(cfg []Capa) {
	if c.met == nil {
		return
	}
	defecto := map[string]float64{}
	for _, d := range ConfigPorDefecto().Capas {
		defecto[d.Nombre] = d.Tau
	}
	vistas := c.met.calibPrep()
	for _, k := range cfg {
		v, ok := vistas[k.Nombre]
		if !ok || (k.Nombre != "L1" && k.Nombre != "L2") {
			continue
		}
		// candidatos de CALIB: los que la vista trae con origen calib
		var calib []float64
		for _, t := range v.Taus {
			if t.Origen == OrigenCalib {
				calib = append(calib, t.Valor)
			}
		}
		taus := []TauCalib{{Capa: k.Nombre, Clave: "tau_escalate", Valor: k.Tau, Origen: origenTau(k.Tau, defecto[k.Nombre], calib)}}
		// L2c con tau_l2c en servicio: k.Tau es el de la cabeza conjunta y tau_escalate es el de respaldo (L2 base).
		if k.Nombre == "L2" {
			for _, cp := range c.capas {
				if cr, ok := cp.d.(DecisorConRespaldo); ok && cp.d.Nombre() == "L2" {
					if tr, tc, ok := cr.TauRespaldo(); ok && cp.tau == tc {
						taus = []TauCalib{
							{Capa: k.Nombre, Clave: "tau_escalate", Valor: tr, Origen: origenTau(tr, defecto[k.Nombre], calib)},
							{Capa: k.Nombre, Clave: "tau_l2c", Valor: tc, Origen: OrigenCalib},
						}
					}
				}
			}
		}
		if k.Nombre == "L2" && c.tauNuevo != nil {
			var cn []float64
			for _, t := range v.Taus {
				if t.Clave == "tau_l2_esquema_nuevo" && t.Origen == OrigenCalib {
					cn = append(cn, t.Valor)
				}
			}
			taus = append(taus, TauCalib{Capa: k.Nombre, Clave: "tau_l2_esquema_nuevo", Valor: *c.tauNuevo, Origen: origenTau(*c.tauNuevo, TauL2EsquemaNuevoPorDefecto, cn)})
		}
		c.met.fijaTaus(k.Nombre, taus)
	}
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
		respaldo := false
		if cr, ok := l.d.(DecisorConRespaldo); ok {
			r, respaldo, err = cr.DecidirConOrigen(ctx, p, previas)
		} else if cp, ok := l.d.(DecisorConPrevias); ok {
			r, err = cp.DecidirCon(ctx, p, previas)
		} else {
			r, err = l.d.Decidir(ctx, p)
		}
		c.met.ObservaCapa(l.d.Nombre(), time.Since(t), err)
		if err != nil || ctx.Err() != nil {
			res.Incompleto = true
			r = Respuesta{}
		}
		if r.Incompleto {
			res.Incompleto = true
		}
		previas[l.d.Nombre()] = r
		if r.Conf > mejor.Conf {
			mejor = r
		}
		tau := l.tau
		if cr, ok := l.d.(DecisorConRespaldo); ok && respaldo && !(r.EsquemaNuevo && l.tauNuevo != nil) {
			// respaldo de L2c: τ de L2 base (tau_escalate_l2) salvo esquema nuevo con τ de esquema nuevo (igual que Kotlin/Swift), solo si el τ de la capa es el de la cabeza (tau_l2c de CALIB)
			if tr, tc, ok := cr.TauRespaldo(); ok && l.tau == tc {
				tau = tr
			}
		}
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
			res.Answer, res.Answers, res.Probs, res.Layer = r.Answer, r.Answers, r.Probs, l.d.Nombre()
			c.met.Decidida(res.Layer, false)
			res.Ms = ms(time.Since(t0))
			return res
		}
	}
	res.Escalate = true
	res.Layer = CapaEscalar
	res.Answer, res.Answers = mejor.Answer, mejor.Answers
	if mejor.Probs != nil {
		res.Probs = mejor.Probs
	}
	c.met.Decidida(res.Layer, true)
	res.Ms = ms(time.Since(t0))
	return res
}

func ms(d time.Duration) float64 { return float64(d.Microseconds()) / 1000 }
