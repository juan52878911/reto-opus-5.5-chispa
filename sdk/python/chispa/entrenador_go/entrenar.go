package main

import (
	"bytes"
	"fmt"
	"os"
	"time"

	"chispa/format/chispa3"
	"chispa/runtime/l1"

	"github.com/juan52878911/kindling/pkg/chispa"
	"github.com/juan52878911/kindling/pkg/chispa/train"
)

// Informe de `entrenar`. Los tiempos son de reloj, en segundos.
type Informe struct {
	Salida    string             `json:"salida"`
	Secciones []string           `json:"secciones"`
	Omitidas  map[string]string  `json:"omitidas"` // sección → por qué falta
	NTrain    int                `json:"n_train"`
	NValid    int                `json:"n_valid"`
	L0Valid   float64            `json:"l0_valid_acc"`
	L1Valid   float64            `json:"l1_valid_acc,omitempty"`
	L1TauOK   bool               `json:"l1_tau_alcanza_objetivo"`
	Calib     chispa3.Calib      `json:"calib"`
	Tiempos   map[string]float64 `json:"tiempos_s"`
	Bytes     int                `json:"bytes"`
}

// embebeOpciones devuelve el embedding L1 de cada opción, en el orden del plan.
func embebeOpciones(m *l1.Modelo, p pregunta) [][]float32 {
	out := make([][]float32, len(p.Opciones))
	for i, o := range p.Opciones {
		out[i] = make([]float32, m.Dim())
		m.Embed(textoOpcion(p, o), out[i])
	}
	return out
}

// cosenos devuelve el coseno del mensaje con cada opción (nil si L1 no ve tokens).
func cosenos(m *l1.Modelo, ops [][]float32, texto string) []float64 {
	msg := make([]float32, m.Dim())
	if !m.Embed(texto, msg) {
		return nil
	}
	s := make([]float64, len(ops))
	for j, o := range ops {
		for k := range msg {
			s[j] += float64(msg[k]) * float64(o[k])
		}
	}
	return s
}

func indiceDe(p pregunta, id string) int {
	for i, o := range p.Opciones {
		if o.ID == id {
			return i
		}
	}
	return -1
}

func entrenar(p *Plan) (*Informe, error) {
	t0 := time.Now()
	inf := &Informe{Salida: p.Salida, Omitidas: map[string]string{}, Tiempos: map[string]float64{}}
	if p.Pregunta.Kind != "choice" && p.Pregunta.Kind != "noul" && p.Pregunta.Kind != "score" {
		return nil, fmt.Errorf("kind %q no válido", p.Pregunta.Kind)
	}
	exs, err := leerEjemplos(p.Ejemplos, idsDe(p.Pregunta))
	if err != nil {
		return nil, err
	}
	tr, va := train.SplitValidation(exs, p.FracValid, p.Semilla)
	inf.NTrain, inf.NValid = len(tr), len(va)
	if len(tr) == 0 || len(va) == 0 {
		return nil, fmt.Errorf("partición vacía (train %d, validación %d): faltan ejemplos", len(tr), len(va))
	}

	// L0: lineal sobre los ejemplos; la validación fija el τ propio del modelo.
	t := time.Now()
	res, err := train.Train(tr, va, train.Config{Spec: chispa.DefaultSpec(), Seed: p.Semilla})
	if err != nil {
		return nil, fmt.Errorf("L0: %w", err)
	}
	l0, err := res.Model.Marshal()
	if err != nil {
		return nil, err
	}
	inf.Tiempos["l0"] = time.Since(t).Seconds()
	if res.Valid != nil {
		inf.L0Valid = res.Valid.Accuracy
	}

	secs := []chispa3.Seccion{{Tipo: chispa3.L0, Datos: l0}}
	calib := chispa3.Calib{Tipos: map[string]chispa3.ParamsTipo{}, TauEscalate: 1}

	// L1: potion exportado; se calibra con la validación.
	if p.L1 == "" {
		inf.Omitidas["L1"] = "sin --l1 (.chispa-l1)"
	} else {
		t = time.Now()
		m, err := l1.Abrir(p.L1)
		if err != nil {
			return nil, fmt.Errorf("L1: %w", err)
		}
		datos, err := os.ReadFile(p.L1)
		if err != nil {
			return nil, err
		}
		if err := chispa3.ValidarL1(datos); err != nil {
			return nil, err
		}
		secs = append(secs, chispa3.Seccion{Tipo: chispa3.L1, Datos: datos})
		if p.Pregunta.Kind == "score" {
			inf.Omitidas["L1.calib"] = "score: L1 no opina"
		} else {
			calibrarL1(m, p, va, &calib, inf)
		}
		inf.Tiempos["l1"] = time.Since(t).Seconds()
	}

	// L2 y ESQUEMAS: solo si hay un .chispa de exportar.py.
	if p.L2Chispa == "" {
		inf.Omitidas["L2"] = "sin checkpoint de L2 (--l2): solo L0 y L1"
		inf.Omitidas["ESQUEMAS"] = "sin checkpoint de L2"
	} else {
		f, err := chispa3.Abrir(p.L2Chispa)
		if err != nil {
			return nil, fmt.Errorf("--l2: %w", err)
		}
		defer f.Close()
		for _, tp := range []chispa3.Tipo{chispa3.L2, chispa3.ESQUEMAS} {
			if !f.Tiene(tp) {
				return nil, fmt.Errorf("--l2: falta la sección %v", tp)
			}
			b, err := f.Bytes(tp)
			if err != nil {
				return nil, err
			}
			secs = append(secs, chispa3.Seccion{Tipo: tp, Datos: b})
		}
	}

	if p.Conj != "" {
		if p.L2Chispa == "" {
			return nil, fmt.Errorf("conj: la cabeza conjunta necesita L2 y ESQUEMAS (--l2)")
		}
		b, err := os.ReadFile(p.Conj)
		if err != nil {
			return nil, err
		}
		if _, err := chispa3.DecodificarConj(b); err != nil {
			return nil, err
		}
		secs = append(secs, chispa3.Seccion{Tipo: chispa3.CONJ, Datos: b})
	}

	cb, err := calib.Codificar()
	if err != nil {
		return nil, err
	}
	mb, err := chispa3.Meta(p.Meta).Codificar()
	if err != nil {
		return nil, err
	}
	secs = append(secs, chispa3.Seccion{Tipo: chispa3.CALIB, Datos: cb}, chispa3.Seccion{Tipo: chispa3.META, Datos: mb})
	var buf bytes.Buffer
	if err := chispa3.Escribir(&buf, secs); err != nil {
		return nil, err
	}
	// ida y vuelta antes de escribir
	f, err := chispa3.Desde(buf.Bytes(), chispa3.Limites{})
	if err != nil {
		return nil, err
	}
	if err := f.Verificar(); err != nil {
		return nil, err
	}
	for _, tp := range f.Tipos() {
		inf.Secciones = append(inf.Secciones, tp.String())
	}
	tmp := p.Salida + ".tmp"
	if err := os.WriteFile(tmp, buf.Bytes(), 0o644); err != nil {
		return nil, err
	}
	if err := os.Rename(tmp, p.Salida); err != nil {
		return nil, err
	}
	inf.Bytes = buf.Len()
	inf.Calib = calib
	inf.Tiempos["total"] = time.Since(t0).Seconds()
	return inf, nil
}

// calibrarL1 ajusta T (choice) o a, b, θ (noul) y el τ de escalate con las similitudes de L1 en la validación.
func calibrarL1(m *l1.Modelo, p *Plan, va []chispa.Example, calib *chispa3.Calib, inf *Informe) {
	ops := embebeOpciones(m, p.Pregunta)
	var sims [][]float64
	var y []int
	for _, e := range va {
		if s := cosenos(m, ops, e.Text); s != nil {
			sims = append(sims, s)
			y = append(y, indiceDe(p.Pregunta, e.Label))
		}
	}
	if len(sims) == 0 {
		inf.Omitidas["L1.calib"] = "L1 no ve tokens en la validación"
		return
	}
	var conf []float64
	var ok []bool
	if p.Pregunta.Kind == "noul" {
		it := indiceDe(p.Pregunta, "true")
		s := make([]float64, len(sims))
		yb := make([]int, len(sims))
		for i := range sims {
			s[i] = sims[i][it]
			if y[i] == it {
				yb[i] = 1
			}
		}
		a, b := ajustarPlatt(s, yb)
		pt := make([]float64, len(s))
		for i := range s {
			pt[i] = sigmoid(a*s[i] + b)
		}
		th := umbralF1(pt, yb)
		calib.Tipos["noul"] = chispa3.ParamsTipo{T: 1, A: a, B: b, Theta: th}
		for i := range pt {
			c, acierto := pt[i], yb[i] == 1
			if pt[i] < th {
				c, acierto = 1-pt[i], yb[i] == 0
			}
			conf, ok = append(conf, c), append(ok, acierto)
		}
	} else {
		T := ajustarT(sims, y)
		calib.Tipos["choice"] = chispa3.ParamsTipo{T: T, Theta: 0.5}
		for i, s := range sims {
			pr := softmax(s, T)
			k := argmax(pr)
			conf, ok = append(conf, pr[k]), append(ok, k == y[i])
		}
	}
	var n int
	for _, a := range ok {
		if a {
			n++
		}
	}
	inf.L1Valid = float64(n) / float64(len(ok))
	calib.TauEscalate, inf.L1TauOK = tauEscalate(conf, ok, p.TauObj, 10)
}
