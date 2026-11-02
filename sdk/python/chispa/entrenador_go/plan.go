package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"strings"

	"chispa/format/chispa3"
	"github.com/juan52878911/kindling/pkg/chispa"
)

type opcion struct {
	ID          string `json:"id"`
	Description string `json:"description"`
}

type pregunta struct {
	ID       string   `json:"id"`
	Texto    string   `json:"texto"`
	Kind     string   `json:"kind"` // choice | noul | score
	Opciones []opcion `json:"opciones"`
}

// Plan es lo que Python pasa al entrenador.
type Plan struct {
	Ejemplos   string   `json:"ejemplos"` // JSONL {"text","label"}
	Prueba     string   `json:"prueba"`   // idem, solo para `evaluar`
	Pregunta   pregunta `json:"pregunta"`
	L1         string   `json:"l1"`        // .chispa-l1; vacío = sin L1
	L2Chispa   string   `json:"l2_chispa"` // .chispa v3 de model/l2/exportar.py: de aquí salen L2 y ESQUEMAS; vacío = sin L2
	Conj       string   `json:"conj"`      // sección CONJ ya codificada (train.py --conjunta); vacío = sin cabeza conjunta
	L0TF       string   `json:"l0tf"`      // sección L0TF ya codificada (train.py --conjunta); vacío = sin L0 tfidf
	TauL2c     *float64 `json:"tau_l2c"`   // τ de L2c fuera de pliegue (train.py --conjunta); nil = sin τ propio
	Meta       Meta     `json:"meta"`
	Salida     string   `json:"salida"`
	Semilla    uint64   `json:"semilla"`
	FracValid  float64  `json:"frac_valid"`    // 0,2 por defecto
	TauL0      float64  `json:"tau_l0"`        // τ de L0 en `evaluar` (el servidor lo toma de su config): 0,8
	TauObj     float64  `json:"tau_precision"` // precisión objetivo de τ de escalate: 0,95
	SinL0      bool     `json:"sin_l0"`        // pocos ejemplos por opción (few-shot): sin L0; L1 se calibra con todos los ejemplos
	L1Lambda   *float64 `json:"l1_lambda"`     // λ de encogimiento (SOPL1) con el que calibrar L1; nil = sin encogimiento
	MaxFichero int64    `json:"max_fichero"`   // tope en bytes del .chispa de salida (--max-fichero); 0 = 1 GiB, el del servidor por defecto
	L0MaxMB    float64  `json:"l0_max_mb"`     // tope de la tabla de pesos de L0 en MB (1e6 bytes); 48 por defecto
}

type Meta struct {
	Version   int               `json:"version"`
	Tareas    []string          `json:"tareas"`
	Licencias map[string]string `json:"licencias"`
	Dorado    string            `json:"dorado"`
	// TextoTorre es META.texto_torre (versión del texto de torre al vuelo): se copia del l2.chispa; vacío = v1 (no se escribe).
	TextoTorre string `json:"texto_torre,omitempty"`
}

func leerPlan(ruta string) (*Plan, error) {
	b, err := os.ReadFile(ruta)
	if err != nil {
		return nil, err
	}
	var p Plan
	d := json.NewDecoder(bytes.NewReader(b))
	d.DisallowUnknownFields()
	if err := d.Decode(&p); err != nil {
		return nil, fmt.Errorf("%s: %w", ruta, err)
	}
	if p.FracValid <= 0 || p.FracValid >= 1 {
		p.FracValid = 0.2
	}
	if p.TauObj <= 0 || p.TauObj > 1 {
		p.TauObj = 0.95
	}
	if p.TauL0 <= 0 || p.TauL0 > 1 {
		p.TauL0 = 0.8
	}
	if p.L0MaxMB <= 0 {
		p.L0MaxMB = 48
	}
	if p.Semilla == 0 {
		p.Semilla = 1
	}
	if p.Meta.Version < 1 {
		p.Meta.Version = 1
	}
	if p.Meta.Tareas == nil {
		p.Meta.Tareas = []string{p.Pregunta.ID}
	}
	if p.Meta.Licencias == nil {
		p.Meta.Licencias = map[string]string{}
	}
	if len(p.Pregunta.Opciones) < 2 {
		return nil, fmt.Errorf("la pregunta necesita ≥ 2 opciones")
	}
	return &p, nil
}

func leerEjemplos(ruta string, ids []string) ([]chispa.Example, error) {
	ok := map[string]bool{}
	for _, i := range ids {
		ok[i] = true
	}
	f, err := os.Open(ruta)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	var out []chispa.Example
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 1<<20), 1<<24)
	for n := 1; sc.Scan(); n++ {
		if strings.TrimSpace(sc.Text()) == "" {
			continue
		}
		var e struct {
			Text  string `json:"text"`
			Label string `json:"label"`
		}
		if err := json.Unmarshal(sc.Bytes(), &e); err != nil {
			return nil, fmt.Errorf("%s:%d: %w", ruta, n, err)
		}
		if !ok[e.Label] {
			return nil, fmt.Errorf("%s:%d: etiqueta %q no es una opción", ruta, n, e.Label)
		}
		out = append(out, chispa.Example{Text: e.Text, Label: e.Label})
	}
	return out, sc.Err()
}

func idsDe(p pregunta) []string {
	ids := make([]string, len(p.Opciones))
	for i, o := range p.Opciones {
		ids[i] = o.ID
	}
	return ids
}

// textoOpcion es el de server/decide/l1.go: «pregunta · opción · descripción».
func textoOpcion(p pregunta, o opcion) string {
	s := []string{p.Texto, o.ID}
	if o.Description != "" {
		s = append(s, o.Description)
	}
	return strings.Join(s, " · ")
}

// bucketsParaL0 devuelve el mayor número de buckets (potencia de dos, ≤ el de por defecto) con el que la tabla de pesos de
// L0 (buckets × salidas × 2 bytes; una sola salida si hay dos clases) cabe en maxMB. El lector de kindling rechaza más de
// 64 MiB. Reducir buckets es hashing más denso: más colisiones, mismas características.
func bucketsParaL0(clases int, maxMB float64) int {
	salidas := clases
	if clases <= 2 {
		salidas = 1
	}
	b := chispa.DefaultBuckets
	for b > chispa.MinBuckets && float64(b)*float64(salidas)*2 > maxMB*1e6 {
		b >>= 1
	}
	return b
}

// limites son los de chispa3 para abrir el .chispa de salida y el de --l2: el tope de --max-fichero (0 = 1 GiB).
func (p *Plan) limites() chispa3.Limites { return chispa3.Limites{MaxFichero: p.MaxFichero} }
