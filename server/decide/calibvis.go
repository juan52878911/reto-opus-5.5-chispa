package decide

import (
	"fmt"
	"io"
	"sort"
	"strings"
	"sync"

	"chispa/format/chispa3"
)

// Origen de los parámetros de CALIB que ve una capa.
const (
	OrigenFichero = "fichero"  // clave de «tipos» del .chispa
	OrigenTiposL2 = "tipos_l2" // clave de «tipos_l2» (solo L2 y L2c)
	OrigenDefecto = "default"  // la capa no la encuentra y usa los parámetros por defecto
	OrigenCalib   = "calib"    // origen de un τ: sale de la CALIB del .chispa
	OrigenConfig  = "config"   // origen de un τ: lo fija la config (-config)
)

// TiposBase son los tipos cuya ausencia en CALIB hace que la capa use parámetros por defecto (choice, noul) o no opine / use otros (score, multi).
var TiposBase = []string{"choice", "noul", "score", "multi"}

// ParamsDefecto son los parámetros que usa una capa cuando CALIB no trae el tipo.
func ParamsDefecto() chispa3.ParamsTipo {
	return chispa3.ParamsTipo{T: tDefecto, A: 4, B: -2, Theta: 0.5}
}

// EntradaCalib es una clave de CALIB tal como la ve una capa.
type EntradaCalib struct {
	Capa   string `json:"capa"`
	Tipo   string `json:"tipo"`
	Origen string `json:"origen"`
	chispa3.ParamsTipo
}

// TauCalib es un τ de CALIB visible desde fuera.
type TauCalib struct {
	Capa   string  `json:"capa"`
	Clave  string  `json:"clave"`
	Valor  float64 `json:"valor"`
	Origen string  `json:"origen"`
}

// VistaCalib es la CALIB efectiva de una capa: lo que /metrics publica.
type VistaCalib struct {
	Capa     string
	Entradas []EntradaCalib
	Taus     []TauCalib
	SinCalib []string // tipos base sin ninguna clave en la CALIB de la capa
}

// VistaCalibCapa calcula la CALIB efectiva de una capa. c es la CALIB tal como la ve la capa (L2: ya con ParaL2); origen es
// OrigenFichero u OrigenTiposL2 (de dónde sale c.Tipos). L1 y L2 comparten forma: solo cambia qué hace la capa sin la clave.
func VistaCalibCapa(capa string, c chispa3.Calib, origen string, conCalib bool) VistaCalib {
	v := VistaCalib{Capa: capa}
	claves := make([]string, 0, len(c.Tipos))
	for k := range c.Tipos {
		claves = append(claves, k)
	}
	sort.Strings(claves)
	for _, k := range claves {
		v.Entradas = append(v.Entradas, EntradaCalib{Capa: capa, Tipo: k, Origen: origen, ParamsTipo: c.Tipos[k]})
	}
	prefijoMulti := claveMultiL1
	if capa == "L2" {
		prefijoMulti = claveMultiL2
	}
	for _, t := range TiposBase {
		hay := false
		switch t {
		case "choice", "noul":
			_, hay = c.Tipos[t]
			if !hay {
				v.Entradas = append(v.Entradas, EntradaCalib{Capa: capa, Tipo: t, Origen: OrigenDefecto, ParamsTipo: ParamsDefecto()})
			}
		case "score":
			// L1 solo lee «score» exacto; L2 solo opina con «score<K>» (y sus «#j»).
			if capa == "L2" {
				for k := range c.Tipos {
					if strings.HasPrefix(k, "score") && !strings.Contains(k, "#") && len(k) > len("score") {
						hay = true
					}
				}
			} else {
				_, hay = c.Tipos["score"]
			}
		case "multi":
			for k := range c.Tipos {
				if k == prefijoMulti || strings.HasPrefix(k, prefijoMulti+"@") || strings.HasPrefix(k, prefijoMulti+"#") {
					hay = true
				}
			}
		}
		if !hay {
			v.SinCalib = append(v.SinCalib, t)
		}
	}
	or := OrigenCalib
	if !conCalib {
		or = OrigenDefecto
	}
	v.Taus = append(v.Taus, TauCalib{Capa: capa, Clave: "tau_escalate", Valor: c.TauEscalate, Origen: or})
	if capa == "L2" {
		if c.TauL2c != nil {
			v.Taus = append(v.Taus, TauCalib{Capa: capa, Clave: "tau_l2c", Valor: *c.TauL2c, Origen: or})
		}
		if c.TauL2EsquemaNuevo != nil {
			v.Taus = append(v.Taus, TauCalib{Capa: capa, Clave: "tau_l2_esquema_nuevo", Valor: *c.TauL2EsquemaNuevo, Origen: or})
		}
	}
	return v
}

// AvisoSinCalib es la línea de arranque / recarga con los tipos sin CALIB de la capa; "" si no falta ninguno.
// Un .chispa sin CALIB los tiene todos sin ella.
func (v VistaCalib) AvisoSinCalib() string {
	if len(v.SinCalib) == 0 {
		return ""
	}
	return fmt.Sprintf("AVISO: CALIB de %s sin los tipos [%s]: la capa usa parámetros por defecto (T=%g, a=%g, b=%g, θ=%g) en choice/noul, y en score y multi no opina o aproxima con noul; /metrics: chispa_calib_defecto_total",
		v.Capa, strings.Join(v.SinCalib, " "), ParamsDefecto().T, ParamsDefecto().A, ParamsDefecto().B, ParamsDefecto().Theta)
}

// fijaTaus sustituye los τ de la capa por los efectivos (los que usa la cascada). Sin vista registrada de la capa no hace nada.
func (m *Metricas) fijaTaus(capa string, taus []TauCalib) {
	prepMu.Lock()
	p, preparando := prepCalib[m]
	if preparando {
		if v, ok := p[capa]; ok {
			v.Taus = taus
			p[capa] = v
		}
	}
	prepMu.Unlock()
	if preparando {
		return
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	if v, ok := m.calibs[capa]; ok {
		v.Taus = taus
		m.calibs[capa] = v
	}
}

// iniciaPrepCalib abre un espacio aparte para las vistas de CALIB de la cascada que se está armando: FijaCalib escribe ahí y lo
// publicado en /metrics no cambia hasta publicaCalib (que llama Recargar tras sustituir el modelo en servicio).
func (m *Metricas) iniciaPrepCalib() {
	if m == nil {
		return
	}
	prepMu.Lock()
	prepCalib[m] = map[string]VistaCalib{}
	prepMu.Unlock()
}

// Espacio aparte de las vistas en preparación por Metricas (no cabe un campo en Metricas desde este fichero).
var (
	prepMu    sync.Mutex
	prepCalib = map[*Metricas]map[string]VistaCalib{}
)

// cierraPrepCalib cierra el espacio aparte y devuelve las vistas preparadas (nil si no había).
func (m *Metricas) cierraPrepCalib() map[string]VistaCalib {
	if m == nil {
		return nil
	}
	prepMu.Lock()
	defer prepMu.Unlock()
	p := prepCalib[m]
	delete(prepCalib, m)
	return p
}

// publicaCalib sustituye las vistas publicadas por las de una cascada que ya está en servicio: las capas que ya no están
// desaparecen.
func (m *Metricas) publicaCalib(vistas map[string]VistaCalib) {
	if m == nil {
		return
	}
	m.mu.Lock()
	m.calibs = vistas
	m.mu.Unlock()
}

// origenTau dice de dónde sale el τ efectivo e: calib si coincide con alguno de los de CALIB de la capa, default si es el
// del defecto y config en otro caso.
func origenTau(e, def float64, calib []float64) string {
	for _, c := range calib {
		if e == c {
			return OrigenCalib
		}
	}
	if e == def {
		return OrigenDefecto
	}
	return OrigenConfig
}

// FijaCalib registra la CALIB efectiva de una capa para /metrics; registrar de nuevo la capa (recarga) la sustituye.
func (m *Metricas) FijaCalib(v VistaCalib) {
	if m == nil {
		return
	}
	prepMu.Lock()
	p, preparando := prepCalib[m]
	if preparando {
		p[v.Capa] = v
	}
	prepMu.Unlock()
	if preparando {
		return
	}
	m.mu.Lock()
	if m.calibs == nil {
		m.calibs = map[string]VistaCalib{}
	}
	m.calibs[v.Capa] = v
	m.mu.Unlock()
}

// Calib devuelve las vistas de CALIB registradas, por capa (copia).
func (m *Metricas) Calib() map[string]VistaCalib {
	m.mu.Lock()
	defer m.mu.Unlock()
	return copiaVistas(m.calibs)
}

// calibPrep es Calib sobre el espacio aparte si está abierto.
func (m *Metricas) calibPrep() map[string]VistaCalib {
	prepMu.Lock()
	p, preparando := prepCalib[m]
	c := copiaVistas(p)
	prepMu.Unlock()
	if preparando {
		return c
	}
	return m.Calib()
}

func copiaVistas(src map[string]VistaCalib) map[string]VistaCalib {
	out := make(map[string]VistaCalib, len(src))
	for k, v := range src {
		out[k] = v
	}
	return out
}

// CalibDefecto cuenta una decisión que usó los parámetros por defecto de `tipo` en `capa` (nil-safe).
func (m *Metricas) CalibDefecto(capa, tipo string) {
	if m != nil {
		contador(&m.mu, m.calibDefecto, [2]string{capa, tipo}).Add(1)
	}
}

// paramsDeCapa es paramsDe contando en /metrics cuando cae al defecto.
func paramsDeCapa(m *Metricas, capa string, c chispa3.Calib, tipo string) chispa3.ParamsTipo {
	if _, ok := c.Tipos[tipo]; !ok {
		m.CalibDefecto(capa, tipo)
	}
	return paramsDe(c, tipo)
}

func (m *Metricas) escribeCalib(w io.Writer) {
	m.mu.Lock()
	vistas := make([]VistaCalib, 0, len(m.calibs))
	for _, v := range m.calibs {
		vistas = append(vistas, v)
	}
	m.mu.Unlock()
	sort.Slice(vistas, func(i, j int) bool { return vistas[i].Capa < vistas[j].Capa })
	fmt.Fprintln(w, "# HELP chispa_calib CALIB efectiva por capa y tipo: param = T, a, b o theta; origen = fichero, tipos_l2 o default (la capa usa los por defecto).")
	fmt.Fprintln(w, "# TYPE chispa_calib gauge")
	for _, v := range vistas {
		for _, e := range v.Entradas {
			for _, p := range []struct {
				n string
				x float64
			}{{"T", e.T}, {"a", e.A}, {"b", e.B}, {"theta", e.Theta}} {
				fmt.Fprintf(w, "chispa_calib{capa=\"%s\",tipo=\"%s\",origen=\"%s\",param=\"%s\"} %g\n",
					escapaEtiqueta(e.Capa), escapaEtiqueta(e.Tipo), e.Origen, p.n, p.x)
			}
		}
	}
	fmt.Fprintln(w, "# HELP chispa_calib_tau τ de CALIB en servicio por capa (tau_escalate, tau_l2c, tau_l2_esquema_nuevo).")
	fmt.Fprintln(w, "# TYPE chispa_calib_tau gauge")
	for _, v := range vistas {
		for _, t := range v.Taus {
			fmt.Fprintf(w, "chispa_calib_tau{capa=\"%s\",clave=\"%s\",origen=\"%s\"} %g\n", escapaEtiqueta(t.Capa), t.Clave, t.Origen, t.Valor)
		}
	}
	fmt.Fprintln(w, "# HELP chispa_calib_sin_tipo 1 si la CALIB de la capa no trae ningún parámetro del tipo base (choice, noul, score, multi).")
	fmt.Fprintln(w, "# TYPE chispa_calib_sin_tipo gauge")
	for _, v := range vistas {
		for _, t := range v.SinCalib {
			fmt.Fprintf(w, "chispa_calib_sin_tipo{capa=\"%s\",tipo=\"%s\"} 1\n", escapaEtiqueta(v.Capa), t)
		}
	}
	fmt.Fprintln(w, "# HELP chispa_calib_defecto_total Decisiones que usaron parámetros por defecto porque la CALIB de la capa no trae el tipo.")
	fmt.Fprintln(w, "# TYPE chispa_calib_defecto_total counter")
	m.mu.Lock()
	ks := make([][2]string, 0, len(m.calibDefecto))
	for k := range m.calibDefecto {
		ks = append(ks, k)
	}
	sort.Slice(ks, func(i, j int) bool { return ks[i][0] < ks[j][0] || ks[i][0] == ks[j][0] && ks[i][1] < ks[j][1] })
	for _, k := range ks {
		fmt.Fprintf(w, "chispa_calib_defecto_total{capa=\"%s\",tipo=\"%s\"} %d\n", escapaEtiqueta(k[0]), escapaEtiqueta(k[1]), m.calibDefecto[k].Load())
	}
	m.mu.Unlock()
}
