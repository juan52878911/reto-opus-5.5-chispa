package chispamovil

import (
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"sync"

	"chispa/format/chispa3"
)

// CALIB visible: los valores efectivos por capa y tipo (CalibJSON), cuántas decisiones usaron los de por defecto (CalibDefectoJSON) y un aviso
// al abrir con los tipos sin CALIB (Avisos). Mismos nombres y semántica que chispa_calib* de /metrics del servidor.

const (
	origenFichero = "fichero"
	origenTiposL2 = "tipos_l2"
	origenDefecto = "default"
	origenCalib   = "calib" // origen de un τ: sale de la CALIB del .chispa
)

var tiposBase = []string{"choice", "noul", "score", "multi"}

type entradaCalib struct {
	Capa   string  `json:"capa"`
	Tipo   string  `json:"tipo"`
	Origen string  `json:"origen"`
	T      float64 `json:"T"`
	A      float64 `json:"a"`
	B      float64 `json:"b"`
	Theta  float64 `json:"theta"`
}

type tauCalib struct {
	Capa   string  `json:"capa"`
	Clave  string  `json:"clave"`
	Valor  float64 `json:"valor"`
	Origen string  `json:"origen"`
}

type vistaCalib struct {
	Capa     string         `json:"capa"`
	Entradas []entradaCalib `json:"entradas"`
	Taus     []tauCalib     `json:"taus"`
	SinCalib []string       `json:"sin_calib"`
}

func paramsDefecto() chispa3.ParamsTipo {
	return chispa3.ParamsTipo{T: tDefecto, A: 4, B: -2, Theta: 0.5}
}

// vistaCalibCapa es la CALIB efectiva de una capa; c ya es la que lee la capa (L2: ParaL2) y origen de dónde salen sus tipos.
func vistaCalibCapa(capa string, c chispa3.Calib, origen string, conCalib bool) vistaCalib {
	v := vistaCalib{Capa: capa, Entradas: []entradaCalib{}, Taus: []tauCalib{}, SinCalib: []string{}}
	claves := make([]string, 0, len(c.Tipos))
	for k := range c.Tipos {
		claves = append(claves, k)
	}
	sort.Strings(claves)
	ent := func(k, or string, p chispa3.ParamsTipo) {
		v.Entradas = append(v.Entradas, entradaCalib{Capa: capa, Tipo: k, Origen: or, T: p.T, A: p.A, B: p.B, Theta: p.Theta})
	}
	for _, k := range claves {
		ent(k, origen, c.Tipos[k])
	}
	multi := "multi"
	if capa == "L2" {
		multi = "multi_l2"
	}
	for _, t := range tiposBase {
		hay := false
		switch t {
		case "choice", "noul":
			_, hay = c.Tipos[t]
			if !hay {
				ent(t, origenDefecto, paramsDefecto())
			}
		case "score":
			// L1 solo lee «score» exacto; L2 solo opina con «score<K>» (y sus «#j»).
			if capa == "L2" {
				for k := range c.Tipos {
					hay = hay || strings.HasPrefix(k, "score") && !strings.Contains(k, "#") && len(k) > len("score")
				}
			} else {
				_, hay = c.Tipos["score"]
			}
		case "multi":
			for k := range c.Tipos {
				hay = hay || k == multi || strings.HasPrefix(k, multi+"@") || strings.HasPrefix(k, multi+"#")
			}
		}
		if !hay {
			v.SinCalib = append(v.SinCalib, t)
		}
	}
	or := origenCalib
	if !conCalib {
		or = origenDefecto
	}
	v.Taus = append(v.Taus, tauCalib{capa, "tau_escalate", c.TauEscalate, or})
	return v
}

func (v vistaCalib) aviso() string {
	if len(v.SinCalib) == 0 {
		return ""
	}
	d := paramsDefecto()
	return fmt.Sprintf("CALIB de %s sin los tipos [%s]: la capa usa parámetros por defecto (T=%g, a=%g, b=%g, θ=%g) en choice/noul, y en score y multi no opina o aproxima con noul (CalibDefectoJSON cuenta las decisiones afectadas)",
		v.Capa, strings.Join(v.SinCalib, " "), d.T, d.A, d.B, d.Theta)
}

// origenTipos dice de dónde salen los tipos de L2.
func (c *Chispa) origenTipos() string {
	if c.calib.TiposL2 != nil {
		return origenTiposL2
	}
	return origenFichero
}

func (c *Chispa) vistasCalib() []vistaCalib {
	conCalib := c.f == nil || c.f.Tiene(chispa3.CALIB) // sin fichero (pruebas) la CALIB de c.calib es la que hay
	var out []vistaCalib
	if c.f == nil || c.f.Tiene(chispa3.L1) {
		out = append(out, vistaCalibCapa("L1", c.calib, origenFichero, conCalib))
	}
	if c.tieneL2 {
		out = append(out, vistaCalibCapa("L2", c.calib.ParaL2(), c.origenTipos(), conCalib))
	}
	if c.tieneL2 {
		// τ de esquema nuevo en servicio (el que lee la cascada de Kotlin/Swift); −1 tras SinTauEsquemaNuevo(true): no hay τ propio.
		if t := c.TauL2EsquemaNuevo(); t >= 0 {
			or := origenDefecto
			if c.calib.TauL2EsquemaNuevo != nil {
				or = origenCalib
			}
			for i := range out {
				if out[i].Capa == "L2" {
					out[i].Taus = append(out[i].Taus, tauCalib{"L2", "tau_l2_esquema_nuevo", t, or})
				}
			}
		}
		// con CONJ, la cabeza conjunta decide con tau_l2c si CALIB lo trae
		if t := c.TauL2c(); t >= 0 {
			for i := range out {
				if out[i].Capa == "L2" {
					out[i].Taus = append(out[i].Taus, tauCalib{"L2", "tau_l2c", t, origenCalib})
				}
			}
		}
	}
	return out
}

// avisarCalib añade a Avisos los tipos que faltan en la CALIB de cada capa montada. Lo llama montar.
func (c *Chispa) avisarCalib() {
	for _, v := range c.vistasCalib() {
		if a := v.aviso(); a != "" {
			c.avisos = append(c.avisos, a)
		}
	}
}

// CalibJSON devuelve la CALIB efectiva por capa (L1 y L2, las que tiene el .chispa): para cada tipo T, a, b, θ y el origen
// ("fichero", "tipos_l2" o "default" = la capa usa los de por defecto), los τ y los tipos base sin CALIB.
func (c *Chispa) CalibJSON() string {
	b, err := json.Marshal(c.vistasCalib())
	if err != nil {
		return "[]"
	}
	return string(b)
}

// contadorDefecto cuenta las decisiones que usaron los parámetros por defecto de un tipo en una capa.
type contadorDefecto struct {
	mu sync.Mutex
	n  map[[2]string]int64
}

func (d *contadorDefecto) sube(capa, tipo string) {
	d.mu.Lock()
	if d.n == nil {
		d.n = map[[2]string]int64{}
	}
	d.n[[2]string{capa, tipo}]++
	d.mu.Unlock()
}

// CalibDefectoJSON devuelve [{"capa","tipo","n"}] con las decisiones que usaron parámetros por defecto por falta de CALIB.
func (c *Chispa) CalibDefectoJSON() string {
	c.defecto.mu.Lock()
	type fila struct {
		Capa string `json:"capa"`
		Tipo string `json:"tipo"`
		N    int64  `json:"n"`
	}
	out := []fila{}
	for k, n := range c.defecto.n {
		out = append(out, fila{k[0], k[1], n})
	}
	c.defecto.mu.Unlock()
	sort.Slice(out, func(i, j int) bool {
		return out[i].Capa < out[j].Capa || out[i].Capa == out[j].Capa && out[i].Tipo < out[j].Tipo
	})
	b, _ := json.Marshal(out)
	return string(b)
}

// paramsCapa es paramsTipo contando cuando la capa cae al defecto.
func (c *Chispa) paramsCapa(capa string, tipos map[string]chispa3.ParamsTipo, tipo string) chispa3.ParamsTipo {
	if _, ok := tipos[tipo]; !ok {
		c.defecto.sube(capa, tipo)
	}
	return paramsTipo(tipos, tipo)
}
