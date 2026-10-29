package main

import (
	"bytes"
	"fmt"
	"math"
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
	L0MacroF1 float64            `json:"l0_valid_macro_f1"`
	L0Buckets int                `json:"l0_buckets"`
	L0Bytes   int                `json:"l0_bytes"`
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
	return cosenosCon(msg, ops)
}

func cosenosCon(msg []float32, ops [][]float32) []float64 {
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
	var tr, va []chispa.Example
	var secs []chispa3.Seccion
	if p.SinL0 {
		// Few-shot: un lineal con k ejemplos por opción no sirve. Todos los ejemplos calibran L1 (que no entrena con ellos).
		va = exs
		inf.NValid = len(va)
		inf.Omitidas["L0"] = "pocos ejemplos por opción (few-shot): L0 necesita más"
	} else {
		tr, va = train.SplitValidation(exs, p.FracValid, p.Semilla)
		inf.NTrain, inf.NValid = len(tr), len(va)
		if len(tr) == 0 || len(va) == 0 {
			return nil, fmt.Errorf("partición vacía (train %d, validación %d): faltan ejemplos", len(tr), len(va))
		}

		// L0: lineal sobre los ejemplos; la validación fija el τ propio del modelo.
		t := time.Now()
		spec := chispa.DefaultSpec()
		spec.Buckets = uint32(bucketsParaL0(len(p.Pregunta.Opciones), p.L0MaxMB))
		inf.L0Buckets = int(spec.Buckets)
		res, err := train.Train(tr, va, train.Config{Spec: spec, Seed: p.Semilla})
		if err != nil {
			return nil, fmt.Errorf("L0: %w", err)
		}
		l0, err := res.Model.Marshal()
		if err != nil {
			return nil, err
		}
		inf.L0Bytes = len(l0)
		inf.Tiempos["l0"] = time.Since(t).Seconds()
		if res.Valid != nil {
			inf.L0Valid = res.Valid.Accuracy
			inf.L0MacroF1 = res.Valid.MacroF1
		}
		secs = append(secs, chispa3.Seccion{Tipo: chispa3.L0, Datos: l0})
	}
	t := time.Now()

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
			calibrarL1(m, p, exs, va, &calib, inf)
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
		// De la CALIB de l2.chispa pasan a la final los campos de L2 (L2 y L2c los leen en lugar de tipos y tau_escalate); la de L1 no se toca.
		if f.Tiene(chispa3.CALIB) {
			c2, err := f.Calib()
			if err != nil {
				return nil, fmt.Errorf("--l2: %w", err)
			}
			calib.TiposL2 = c2.Tipos
			tau := c2.TauEscalate
			calib.TauEscalateL2 = &tau
			calib.TauL2c = c2.TauL2c
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
		calib.TauL2c = p.TauL2c
	}

	if p.L0TF != "" {
		b, err := os.ReadFile(p.L0TF)
		if err != nil {
			return nil, err
		}
		if _, err := chispa3.DecodificarL0TF(b); err != nil {
			return nil, err
		}
		secs = append(secs, chispa3.Seccion{Tipo: chispa3.L0TF, Datos: b})
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
// Con p.L1Lambda el prototipo de cada opción es el de runtime (chispa3.Mezclar con PesoSoporte): el soporte (SOPL1) son todos los
// ejemplos `exs`, y a cada ejemplo de validación se le quita de su clase (leave-one-out) para no calibrar contra sí mismo.
func calibrarL1(m *l1.Modelo, p *Plan, exs, va []chispa.Example, calib *chispa3.Calib, inf *Informe) {
	ops := embebeOpciones(m, p.Pregunta)
	lam := p.L1Lambda
	if lam != nil && (math.IsInf(*lam, 0) || math.IsNaN(*lam) || *lam < 0) {
		lam = nil // λ = ∞ es solo la descripción: lo mismo que sin encogimiento
	}
	var suma [][]float64
	var kc []int
	if lam != nil {
		suma, kc = make([][]float64, len(ops)), make([]int, len(ops))
		for i := range suma {
			suma[i] = make([]float64, m.Dim())
		}
		for _, e := range exs {
			v, c := make([]float32, m.Dim()), indiceDe(p.Pregunta, e.Label)
			if c >= 0 && m.Embed(e.Text, v) {
				for t := range v {
					suma[c][t] += float64(v[t])
				}
				kc[c]++
			}
		}
	}
	var sims [][]float64
	var y []int
	for _, e := range va {
		msg := make([]float32, m.Dim())
		if !m.Embed(e.Text, msg) {
			continue
		}
		c := indiceDe(p.Pregunta, e.Label)
		pr := ops
		if lam != nil {
			pr = make([][]float32, len(ops))
			for j, o := range ops {
				pr[j] = o
				k, s := kc[j], suma[j]
				if j == c && k > 0 {
					k, s = k-1, make([]float64, len(suma[j]))
					for t := range s {
						s[t] = suma[j][t] - float64(msg[t])
					}
				}
				if w := chispa3.PesoSoporte(k, lam); w > 0 {
					media := make([]float32, len(s))
					for t := range s {
						media[t] = float32(s[t] / float64(k))
					}
					pr[j] = chispa3.Mezclar(o, media, w)
				}
			}
		}
		sims = append(sims, cosenosCon(msg, pr))
		y = append(y, c)
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
	calib.L1LambdaCalib = lam
	calib.TauEscalate, inf.L1TauOK = tauEscalate(conf, ok, p.TauObj, 10)
}
