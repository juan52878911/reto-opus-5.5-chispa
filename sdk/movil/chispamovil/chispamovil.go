// Package chispamovil es la API de Chispa para móviles, pensada para `gomobile bind`: solo tipos que gomobile
// sabe cruzar (string, []byte, int, float64, error y punteros a structs). Envuelve un .chispa v3 y expone cada capa
// por separado; la cascada (τ, orden, L2 con ONNX Runtime) vive en Kotlin y Swift.
//
//	L0: DecidirL0       — Chispa lineal de la sección L0
//	L1: Decidir         — embedding estático (runtime/l1), la misma cuenta que server/decide/l1.go y demo/wasm
//	L2: PuntuarL2       — MaxSim de las ranuras que da ONNX Runtime contra las torres de ESQUEMAS (server/decide/l2.go)
//
// Todas las decisiones devuelven JSON: {"ok":true,"opina":bool,"answer":…,"conf":…,"probs":{…}} o
// {"ok":false,"error":…}. «opina:false» (conf 0) significa que la capa no tiene nada que decir de esa pregunta.
package chispamovil

import (
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"os"
	"sort"
	"strconv"
	"strings"
	"sync"

	"chispa/format/chispa3"
	"chispa/runtime/l1"
	"chispa/runtime/tok"

	"github.com/juan52878911/kindling/pkg/chispa"
)

// tDefecto es la temperatura de L1 cuando CALIB no trae el tipo (igual que server/decide/l1.go).
const tDefecto = 0.05

// embebedor es lo que L1 necesita del modelo; *l1.Modelo lo cumple y las pruebas usan uno falso.
type embebedor interface {
	Dim() int
	Embed(texto string, out []float32) bool
}

type opcion struct {
	ID          string `json:"id"`
	Description string `json:"description,omitempty"`
}

type pregunta struct {
	Texto    string   `json:"question"`
	Kind     string   `json:"kind"`
	Opciones []opcion `json:"options"`
}

type respuesta struct {
	Ok     bool               `json:"ok"`
	Opina  bool               `json:"opina"`
	Answer string             `json:"answer"`
	Conf   float64            `json:"conf"`
	Probs  map[string]float64 `json:"probs"`
	Error  string             `json:"error,omitempty"`
}

// Chispa es un .chispa v3 abierto.
type Chispa struct {
	f       *chispa3.Fichero
	e       embebedor
	l0      []modeloL0
	esq     *chispa3.Esquemas
	calib   chispa3.Calib
	tieneL2 bool
	conj    *chispa3.Conj      // sección CONJ (la cabeza conjunta), o nil
	tok     *tok.Tokenizador   // tokenizador de e5, o nil
	torre   *chispa3.Torre     // sección TORR (ONNX de la torre al vuelo), o nil
	dyn     map[string]torreL2 // torres de esquemas nuevos que calculó la app, por claveTorre

	mu    sync.Mutex
	cache map[string][][]float32 // pregunta+opciones → torre de L1 de cada opción (en orden)
}

type modeloL0 struct {
	firma string
	m     *chispa.Model       // el Chispa de kindling, o
	tf    *chispa3.L0TFModelo // el TF-IDF de la sección L0TF (manda si el fichero la trae, como en el servidor)
}

// Abrir abre un .chispa v3 (comprobando CRC y sha256 de cada sección que use) y monta las capas que tenga.
func Abrir(ruta string) (*Chispa, error) {
	f, err := chispa3.Abrir(ruta)
	if err != nil {
		return nil, err
	}
	c := &Chispa{f: f, cache: map[string][][]float32{}}
	if err := c.montar(); err != nil {
		f.Close()
		return nil, err
	}
	return c, nil
}

func (c *Chispa) montar() error {
	f := c.f
	if f.Tiene(chispa3.CALIB) {
		var err error
		if c.calib, err = f.Calib(); err != nil {
			return fmt.Errorf("sección CALIB: %w", err)
		}
	}
	if f.Tiene(chispa3.L0TF) {
		m, err := f.L0TF()
		if err != nil {
			return fmt.Errorf("sección L0TF: %w", err)
		}
		c.l0 = append(c.l0, modeloL0{firma: firma(m.Etiquetas), tf: m})
	} else if f.Tiene(chispa3.L0) {
		m, err := f.L0Modelo()
		if err != nil {
			return fmt.Errorf("sección L0: %w", err)
		}
		c.l0 = append(c.l0, modeloL0{firma: firma(m.Labels), m: m})
	}
	if f.Tiene(chispa3.L1) {
		b, err := f.L1()
		if err != nil {
			return fmt.Errorf("sección L1: %w", err)
		}
		m, err := l1.Desde(b)
		if err != nil {
			return fmt.Errorf("sección L1: %w", err)
		}
		c.e = m
	}
	if f.Tiene(chispa3.TORR) {
		t, err := f.Torre()
		if err != nil {
			return fmt.Errorf("sección TORR: %w", err)
		}
		c.torre = &t
	}
	if f.Tiene(chispa3.L2) && f.Tiene(chispa3.ESQUEMAS) {
		esq, err := f.Esquemas()
		if err != nil {
			return fmt.Errorf("sección ESQUEMAS: %w", err)
		}
		c.esq, c.tieneL2 = esq, true
		if f.Tiene(chispa3.CONJ) {
			if c.conj, err = f.Conj(); err != nil {
				return fmt.Errorf("sección CONJ: %w", err)
			}
		}
	}
	return nil
}

// Cerrar libera el fichero. Tras Cerrar no se puede llamar a nada más.
func (c *Chispa) Cerrar() error { return c.f.Close() }

// Capas devuelve en JSON las capas presentes en el fichero, p. ej. ["L0","L1","L2"].
func (c *Chispa) Capas() string {
	cs := []string{}
	if len(c.l0) > 0 {
		cs = append(cs, "L0")
	}
	if c.e != nil {
		cs = append(cs, "L1")
	}
	if c.tieneL2 {
		cs = append(cs, "L2")
	}
	b, _ := json.Marshal(cs)
	return string(b)
}

// TauEscalate es el τ de CALIB para L1 y L2 (0 si el fichero no trae CALIB; entonces la cascada usa el suyo).
func (c *Chispa) TauEscalate() float64 { return c.calib.TauEscalate }

// TieneConj dice si el fichero trae la sección CONJ (con L2 y ESQUEMAS): entonces la cascada puede usar CabezaConjunta.
func (c *Chispa) TieneConj() bool { return c.conj != nil }

// TieneCalib dice si el fichero trae la sección CALIB (si no, TauEscalate no significa nada).
func (c *Chispa) TieneCalib() bool { return c.f.Tiene(chispa3.CALIB) }

// ExtraerL2 escribe el ONNX int8 de la sección L2 en destino (ONNX Runtime lo abre desde ruta, sin copiarlo a la
// memoria de la JVM). Devuelve error si el fichero no trae L2.
func (c *Chispa) ExtraerL2(destino string) error {
	b, err := c.f.L2()
	if err != nil {
		return err
	}
	return os.WriteFile(destino, b, 0o600)
}

func salida(r respuesta) string {
	b, _ := json.Marshal(r)
	return string(b)
}

func fallo(err error) string {
	return salida(respuesta{Error: err.Error(), Probs: map[string]float64{}})
}

func leerPregunta(js string) (pregunta, error) {
	var p pregunta
	if err := json.Unmarshal([]byte(js), &p); err != nil {
		return p, err
	}
	switch p.Kind {
	case "", "choice", "noul", "score":
	default:
		return p, fmt.Errorf("kind no válido: %q", p.Kind)
	}
	if p.Kind == "" {
		p.Kind = "choice"
	}
	if len(p.Opciones) == 0 {
		return p, errors.New("la pregunta no tiene opciones")
	}
	return p, nil
}

func (c *Chispa) params(tipo string) chispa3.ParamsTipo {
	if p, ok := c.calib.Tipos[tipo]; ok {
		return p
	}
	return chispa3.ParamsTipo{T: tDefecto, A: 4, B: -2, Theta: 0.5}
}

// ---- L1 ----

func clave(p pregunta) string {
	var sb strings.Builder
	sb.WriteString(p.Texto)
	for _, o := range p.Opciones {
		sb.WriteString("\x00" + o.ID + "\x01" + o.Description)
	}
	return sb.String()
}

func (c *Chispa) torres(p pregunta) [][]float32 {
	k := clave(p)
	c.mu.Lock()
	defer c.mu.Unlock()
	if v, ok := c.cache[k]; ok {
		return v
	}
	if len(c.cache) >= 256 { // las preguntas de una app son pocas; si se desborda, se vacía
		c.cache = map[string][][]float32{}
	}
	v := make([][]float32, len(p.Opciones))
	for i, o := range p.Opciones {
		s := []string{p.Texto, o.ID}
		if o.Description != "" {
			s = append(s, o.Description)
		}
		v[i] = make([]float32, c.e.Dim())
		c.e.Embed(strings.Join(s, " · "), v[i])
	}
	c.cache[k] = v
	return v
}

// Decidir es L1: coseno entre el mensaje y «pregunta · opción · descripción» y softmax con la T de CALIB (0,05 por
// defecto), como server/decide/l1.go y demo/wasm. preguntaJSON es la pregunta del servidor ({question, kind, options}).
func (c *Chispa) Decidir(texto, preguntaJSON string) string {
	p, err := leerPregunta(preguntaJSON)
	if err != nil {
		return fallo(err)
	}
	if c.e == nil {
		return fallo(errors.New("el fichero no trae la sección L1"))
	}
	if p.Kind == "score" { // un coseno no ordena niveles: sin opinión
		return salida(respuesta{Ok: true, Probs: map[string]float64{}})
	}
	msg := make([]float32, c.e.Dim())
	if !c.e.Embed(texto, msg) {
		return salida(respuesta{Ok: true, Probs: map[string]float64{}})
	}
	ops := c.torres(p)
	sims := make([]float64, len(ops))
	for i, o := range ops {
		for j := range msg {
			sims[i] += float64(msg[j]) * float64(o[j])
		}
	}
	if p.Kind == "noul" {
		prm := c.params("noul")
		var s float64
		for i, o := range p.Opciones {
			if o.ID == "true" {
				s = sims[i]
			}
		}
		return salida(noul(prm.A*s+prm.B, prm.Theta))
	}
	return salida(softmax(p, sims, c.params("choice").T))
}

func softmax(p pregunta, sims []float64, T float64) respuesta {
	mx := math.Inf(-1)
	for _, s := range sims {
		mx = math.Max(mx, s)
	}
	var z float64
	ex := make([]float64, len(sims))
	for i, s := range sims {
		ex[i] = math.Exp((s - mx) / T)
		z += ex[i]
	}
	r := respuesta{Ok: true, Probs: make(map[string]float64, len(sims))}
	for i, o := range p.Opciones {
		pr := ex[i] / z
		r.Probs[o.ID] = pr
		if pr > r.Conf {
			r.Conf, r.Answer = pr, o.ID
		}
	}
	r.Opina = r.Conf > 0
	return r
}

func noul(z, theta float64) respuesta {
	pt := 1 / (1 + math.Exp(-z))
	r := respuesta{Ok: true, Probs: map[string]float64{"true": pt, "false": 1 - pt}}
	if pt >= theta {
		r.Answer, r.Conf = "true", pt
	} else {
		r.Answer, r.Conf = "false", 1-pt
	}
	r.Opina = true
	return r
}

// ---- L0 ----

func firma(ids []string) string {
	s := append([]string(nil), ids...)
	sort.Strings(s)
	return strings.Join(s, "\x00")
}

// DecidirL0 es el Chispa lineal: usa el modelo de la sección L0 cuyas etiquetas coinciden con los ids de las
// opciones. Sin modelo para la pregunta no opina.
func (c *Chispa) DecidirL0(texto, preguntaJSON string) string {
	p, err := leerPregunta(preguntaJSON)
	if err != nil {
		return fallo(err)
	}
	ids := make([]string, len(p.Opciones))
	for i, o := range p.Opciones {
		ids[i] = o.ID
	}
	f := firma(ids)
	for _, x := range c.l0 {
		if x.firma != f {
			continue
		}
		if x.tf != nil {
			return salida(respuestaTF(x.tf, texto))
		}
		pred := x.m.PredictFull(chispa.Input{Text: texto}, 0)
		probs := make(map[string]float64, len(pred.Probs))
		for _, cp := range pred.Probs {
			probs[cp.Label] = cp.Prob
		}
		return salida(respuesta{Ok: true, Opina: pred.Prob > 0, Answer: pred.Label, Conf: pred.Prob, Probs: probs})
	}
	return salida(respuesta{Ok: true, Probs: map[string]float64{}})
}

// respuestaTF: las probabilidades del TF-IDF con regresión logística; la respuesta es el primer máximo, como en
// server/decide/l0.go.
func respuestaTF(m *chispa3.L0TFModelo, texto string) respuesta {
	pr := m.Probs(texto)
	probs := make(map[string]float64, len(pr))
	top := 0
	for i, x := range pr {
		probs[m.Etiquetas[i]] = x
		if x > pr[top] {
			top = i
		}
	}
	return respuesta{Ok: true, Opina: pr[top] > 0, Answer: m.Etiquetas[top], Conf: pr[top], Probs: probs}
}

// ---- Tokenizador de e5 ----

// CargarTokenizadorE5 abre un .chispa-tok de e5 (runtime/tok/exportar.py), el mismo que usa el servidor.
func (c *Chispa) CargarTokenizadorE5(ruta string) error {
	t, err := tok.Abrir(ruta)
	if err != nil {
		return err
	}
	c.tok = t
	return nil
}

// TieneTokenizadorE5 dice si ya se cargó el tokenizador.
func (c *Chispa) TieneTokenizadorE5() bool { return c.tok != nil }

// TokenizarE5 devuelve los ids de «query: »+texto con <s> y </s> (como runtime/tok, truncado a 128) en int32 little
// endian, 4 bytes por id: gomobile no puede devolver []int32. Sin tokenizador devuelve nil.
func (c *Chispa) TokenizarE5(texto string) []byte {
	if c.tok == nil {
		return nil
	}
	ids := c.tok.Tokenizar(texto)
	b := make([]byte, 4*len(ids))
	for i, id := range ids {
		binary.LittleEndian.PutUint32(b[4*i:], uint32(id))
	}
	return b
}

// ---- L2 ----

// TorresL2 dice si hay torres de ESQUEMAS para la pregunta; la cascada lo consulta antes de tokenizar y llamar a ORT.
func (c *Chispa) TorresL2(preguntaJSON string) bool {
	p, err := leerPregunta(preguntaJSON)
	if err != nil || !c.tieneL2 {
		return false
	}
	_, err = c.torresL2(p)
	return err == nil
}

type torreL2 struct {
	v []byte
	e float32
}

func (c *Chispa) torresL2(p pregunta) ([]torreL2, error) {
	buscar := func(ops []string) (torreL2, bool) {
		v, e, ok := c.esq.Buscar(chispa3.HashEsquema(p.Texto, ops))
		return torreL2{v, e}, ok
	}
	var ts []torreL2
	switch p.Kind {
	case "choice":
		for _, o := range p.Opciones {
			t, ok := buscar([]string{o.ID})
			if !ok {
				return c.torresNuevas(p)
			}
			ts = append(ts, t)
		}
	default:
		ids := make([]string, len(p.Opciones))
		for i, o := range p.Opciones {
			ids[i] = o.ID
		}
		if p.Kind == "noul" {
			ids = []string{"false", "true"}
		}
		t, ok := buscar(ids)
		if !ok {
			return c.torresNuevas(p)
		}
		ts = []torreL2{t}
	}
	return ts, nil
}

// ranurasDe lee las ranuras K×d float32 little endian que salen del ONNX.
func ranurasDe(b []byte, k, d int) ([][]float32, error) {
	if k <= 0 || len(b) != 4*k*d {
		return nil, fmt.Errorf("L2: %d bytes de ranuras no son %d×%d float32", len(b), k, d)
	}
	v := make([]float32, k*d)
	for i := range v {
		v[i] = math.Float32frombits(binary.LittleEndian.Uint32(b[4*i:]))
	}
	return partirRanuras(v, k, d)
}

// partirRanuras corta k·d valores en k ranuras de d.
func partirRanuras(v []float32, k, d int) ([][]float32, error) {
	if k <= 0 || len(v) != k*d {
		return nil, fmt.Errorf("L2: %d valores de ranuras no son %d×%d", len(v), k, d)
	}
	S := make([][]float32, k)
	for r := range S {
		S[r] = v[r*d : (r+1)*d : (r+1)*d]
	}
	return S, nil
}

// simsL2 es el MaxSim de las ranuras contra cada torre (chispa3.MaxSim, igual que el servidor).
func simsL2(ts []torreL2, S [][]float32) []float64 {
	sims := make([]float64, len(ts))
	for i, t := range ts {
		sims[i] = chispa3.MaxSim(S, t.v, t.e)
	}
	return sims
}

// PuntuarL2 hace la parte de L2 que no es ONNX: ranuras son las K×d salidas S del modelo como float32 little endian
// (K·d·4 bytes); se puntúan con MaxSim = max_k softplus(h·s_k) contra las torres de ESQUEMAS y las cabezas de CALIB,
// igual que server/decide/l2.go. Sin torres (o sin cabeza calibrada) para la pregunta, no opina.
func (c *Chispa) PuntuarL2(preguntaJSON string, ranuras []byte, k int) string {
	p, err := leerPregunta(preguntaJSON)
	if err != nil {
		return fallo(err)
	}
	if !c.tieneL2 {
		return fallo(errors.New("el fichero no trae las secciones L2 y ESQUEMAS"))
	}
	ts, err := c.torresL2(p)
	if err != nil {
		return salida(respuesta{Ok: true, Probs: map[string]float64{}})
	}
	S, err := ranurasDe(ranuras, k, len(ts[0].v))
	if err != nil {
		return fallo(err)
	}
	sims := simsL2(ts, S)
	switch p.Kind {
	case "choice":
		return salida(softmax(p, sims, c.params("choice").T))
	case "noul":
		prm := c.params("noul")
		return salida(noul(prm.A*sims[0]+prm.B, prm.Theta))
	}
	return salida(c.score(p, sims[0]))
}

// score: CORAL, P(y>j) = σ(a·s − b_j); b_1 = b de «scoreK» y b_j = b_{j−1} + a de «scoreK#j».
func (c *Chispa) score(p pregunta, s float64) respuesta {
	vacia := respuesta{Ok: true, Probs: map[string]float64{}}
	K := len(p.Opciones)
	for i, o := range p.Opciones {
		if o.ID != strconv.Itoa(i+1) {
			return vacia // las cabezas de score van sobre 1..K en orden
		}
	}
	clave := "score" + strconv.Itoa(K)
	base, ok := c.calib.Tipos[clave]
	if !ok || K < 2 {
		return vacia
	}
	sup := make([]float64, K-1) // P(y > j+1)
	b := base.B
	for j := 0; j < K-1; j++ {
		if j > 0 {
			inc, ok := c.calib.Tipos[fmt.Sprintf("%s#%d", clave, j+1)]
			if !ok {
				return vacia
			}
			b += inc.A
		}
		sup[j] = 1 / (1 + math.Exp(-(base.A*s - b)))
	}
	r := respuesta{Ok: true, Probs: make(map[string]float64, K)}
	for i := 0; i < K; i++ {
		hi, lo := 1.0, 0.0
		if i > 0 {
			hi = sup[i-1]
		}
		if i < K-1 {
			lo = sup[i]
		}
		pr := math.Max(hi-lo, 0)
		r.Probs[p.Opciones[i].ID] = pr
		if pr > r.Conf {
			r.Conf, r.Answer = pr, p.Opciones[i].ID
		}
	}
	r.Opina = r.Conf > 0
	return r
}

// Huella es el sha256 (hex) de los embeddings float32 little endian de los textos, como demo/wasm: sirve para
// comprobar que L1 da los mismos bits en el móvil que en el servidor.
func (c *Chispa) Huella(frasesJSON string) string {
	var fr []string
	if err := json.Unmarshal([]byte(frasesJSON), &fr); err != nil || c.e == nil {
		return ""
	}
	return huella(c.e, fr)
}

// ---- CONJ (L2c) ----

type entradaConj struct {
	pregunta
	L0      map[string]float64 `json:"l0"`      // probabilidades de L0 por id de opción
	Ranuras []float32          `json:"ranuras"` // las K×d salidas S del ONNX, aplanadas por filas
	K       int                `json:"k"`
}

// CabezaConjunta es L2c: la cabeza lineal de la sección CONJ sobre las probabilidades de L0 y las similitudes de L2
// con soporte (server/decide/l2c.go, con el mismo código de chispa3). simsJSON lleva la pregunta (question, kind,
// options), «l0» (probabilidades de DecidirL0 por id), «ranuras» (las K×d salidas S del ONNX aplanadas por filas, como
// números JSON: float32 sobrevive exacto a la ida y vuelta) y «k». Las similitudes MaxSim se calculan aquí contra ESQUEMAS.
// Si el fichero no trae CONJ, no hay cabeza para la pregunta, no es choice o falta L0, devuelve ok sin opinar: la
// cascada cae entonces a PuntuarL2.
func (c *Chispa) CabezaConjunta(simsJSON string) string {
	var in entradaConj
	if err := json.Unmarshal([]byte(simsJSON), &in); err != nil {
		return fallo(err)
	}
	p, err := leerPregunta(simsJSON)
	if err != nil {
		return fallo(err)
	}
	sinOpinar := salida(respuesta{Ok: true, Probs: map[string]float64{}})
	if c.conj == nil || !c.tieneL2 || p.Kind != "choice" || len(in.L0) == 0 {
		return sinOpinar
	}
	ids := make([]string, len(p.Opciones))
	for i, o := range p.Opciones {
		ids[i] = o.ID
	}
	e, ok := c.conj.Buscar(chispa3.ClaveConj(p.Texto, ids))
	if !ok {
		return sinOpinar
	}
	ts, err := c.torresL2(p)
	if err != nil {
		return sinOpinar
	}
	S, err := partirRanuras(in.Ranuras, in.K, len(ts[0].v))
	if err != nil {
		return fallo(err)
	}
	if len(S[0]) != e.D {
		return sinOpinar
	}
	pr := e.ProbsCabeza(ids, S, simsL2(ts, S), in.L0)
	r := respuesta{Ok: true, Probs: make(map[string]float64, len(pr))}
	for i, id := range ids {
		r.Probs[id] = pr[i]
		if pr[i] > r.Conf {
			r.Conf, r.Answer = pr[i], id
		}
	}
	r.Opina = r.Conf > 0
	return salida(r)
}
