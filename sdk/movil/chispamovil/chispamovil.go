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
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"os"
	"path/filepath"
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
	Nonce    string   `json:"nonce"`
	Opciones []opcion `json:"options"`
}

type respuesta struct {
	Ok     bool               `json:"ok"`
	Opina  bool               `json:"opina"`
	Answer string             `json:"answer"`
	Conf   float64            `json:"conf"`
	Probs  map[string]float64 `json:"probs"`
	Error  string             `json:"error,omitempty"`
	// Multi: la respuesta es de una pregunta multi; entonces «answers» sale siempre (las opciones activas, [] si ninguna).
	Multi   bool     `json:"-"`
	Answers []string `json:"-"`
}

// MarshalJSON añade «answers» solo en multi (como Resultado en server/decide).
func (r respuesta) MarshalJSON() ([]byte, error) {
	type plano respuesta // sin métodos: evita la recursión
	out := struct {
		plano
		Answers *[]string `json:"answers,omitempty"`
	}{plano: plano(r)}
	if r.Multi && r.Opina {
		a := r.Answers
		if a == nil {
			a = []string{}
		}
		out.Answers = &a
	}
	return json.Marshal(out)
}

// Chispa es un .chispa v3 abierto.
type Chispa struct {
	f           *chispa3.Fichero
	e           embebedor
	l0          []modeloL0
	esq         *chispa3.Esquemas
	calib       chispa3.Calib
	tieneL2     bool
	sinTauNuevo bool               // SinTauEsquemaNuevo(true): TauL2EsquemaNuevo devuelve −1 (L2 usa su τ de siempre)
	maxLenQ     int                // truncado de la consulta (chispa.consulta.max_len del ONNX de L2; 128 si no viene)
	conj        *chispa3.Conj      // sección CONJ (la cabeza conjunta), o nil
	tok         *tok.Tokenizador   // tokenizador de e5, o nil
	torre       *chispa3.Torre     // sección TORR (ONNX de la torre al vuelo), o nil
	dyn         map[string]torreL2 // torres de esquemas nuevos que calculó la app, por claveTorre
	dynUso      map[string]uint64  // último uso de cada torre de dyn (para desalojar la más antigua)
	dynTic      uint64

	sopl        *chispa3.Sopl1 // sección SOPL1 (soporte few-shot: k y media de L1 por opción), o nil
	lambdaL1    *float64       // λ del encogimiento del soporte en L1; nil = apagado; 0 = solo ejemplos; +Inf = solo descripción
	lambdaL2    *float64       // ídem en L2c
	explicitoL1 bool           // el λ de L1 lo pidió el llamador (AbrirConSoporte), no es el default de Abrir
	avisos      []string       // problemas no fatales al abrir (p. ej. SOPL1 inválida con el encogimiento activo)

	mu    sync.Mutex
	cache map[string][][]float32 // pregunta+opciones → torre de L1 de cada opción (en orden)
}

type modeloL0 struct {
	firma string
	m     *chispa.Model       // el Chispa de kindling, o
	tf    *chispa3.L0TFModelo // el TF-IDF de la sección L0TF (manda si el fichero la trae, como en el servidor)
}

// SoporteL1PorDefecto es el λ de L1 que usa Abrir (G.8b: massive 0,395 vs 0,266; inyecciones 0,740 vs 0,326; hatecheck 0,492 vs
// 0,224; JevBench 0,379 vs 0,398). Sin sección SOPL1 en el fichero no tiene efecto. El de L2c queda apagado (sin default medido).
const SoporteL1PorDefecto = 4

// Abrir abre un .chispa v3 (comprobando CRC y sha256 de cada sección que use) y monta las capas que tenga. Equivale a
// AbrirConSoporte(ruta, SoporteL1PorDefecto, SoporteApagado); para el comportamiento anterior en L1,
// AbrirConSoporte(ruta, SoporteApagado, SoporteApagado).
func Abrir(ruta string) (*Chispa, error) {
	return abrir(ruta, SoporteL1PorDefecto, SoporteApagado, false)
}

// SoporteApagado es el valor de λ de AbrirConSoporte que apaga el encogimiento (el puente de gomobile no tiene opcionales:
// cualquier valor negativo o NaN lo apaga también). +Infinito NO lo apaga: es «solo la descripción».
const SoporteApagado = -1.0

// AbrirConSoporte es Abrir con el encogimiento del soporte few-shot (sección SOPL1): con k ejemplos en una opción, su
// prototipo es normaliza((1−w)·descripción + w·media de los ejemplos), w = k/(k+λ), con λ propio en L1 (lambdaL1: Decidir)
// y en L2c (lambdaL2: CabezaConjunta; allí κ ≡ λ y la media lleva la norma por ranura de SOPL1 v2). SoporteApagado (o cualquier
// valor negativo o NaN) = apagado explícito (sin soporte, lo que hacía Abrir antes del default 4); 0 = solo los ejemplos; +Infinito = solo la descripción, en las dos
// capas (antes +Inf apagaba). Sin la sección, o con una pregunta que no está en ella, no cambia nada.
func AbrirConSoporte(ruta string, lambdaL1, lambdaL2 float64) (*Chispa, error) {
	return abrir(ruta, lambdaL1, lambdaL2, true)
}

func abrir(ruta string, lambdaL1, lambdaL2 float64, explicito bool) (*Chispa, error) {
	// En el móvil se mapea: el .chispa vive en el almacenamiento privado de la app (nadie lo pisa con cp) y leerlo
	// entero al heap duplicaría la memoria del L1.
	f, err := chispa3.AbrirCon(ruta, chispa3.Limites{Mmap: true})
	if err != nil {
		return nil, err
	}
	c := &Chispa{f: f, cache: map[string][][]float32{}, lambdaL1: lambdaDe(lambdaL1), lambdaL2: lambdaDe(lambdaL2), explicitoL1: explicito}
	if err := c.montar(); err != nil {
		f.Close()
		return nil, err
	}
	return c, nil
}

// lambdaDe pasa el λ del puente (float64 plano) al interno: nil (apagado) si es negativo o NaN; +Inf pasa tal cual.
func lambdaDe(x float64) *float64 {
	if math.IsNaN(x) || x < 0 {
		return nil
	}
	return &x
}

func (c *Chispa) montar() error {
	f := c.f
	if f.Tiene(chispa3.CALIB) {
		var err error
		if c.calib, err = f.Calib(); err != nil {
			return fmt.Errorf("sección CALIB: %w", err)
		}
	}
	// El τ de L1 se calibró con un λ (CALIB.l1_lambda_calib; ausente = sin encogimiento). Un .chispa viejo con SOPL1 y sin ese
	// campo no mezcla el soporte con el λ por defecto de Abrir (no cambia su resultado); un λ explícito sí se respeta.
	if f.Tiene(chispa3.SOPL1) && c.lambdaL1 != nil {
		lc := c.calib.L1LambdaCalib
		switch {
		case lc == nil && !c.explicitoL1:
			c.lambdaL1 = nil
			c.avisos = append(c.avisos, "SOPL1 sin CALIB.l1_lambda_calib: τ de L1 calibrado sin encogimiento; soporte de L1 apagado (usa AbrirConSoporte para activarlo)")
		case lc == nil:
			c.avisos = append(c.avisos, "L1 mezcla SOPL1 con λ explícito, pero su τ se calibró sin encogimiento: la cobertura y precisión prometidas no valen")
		case *lc != *c.lambdaL1:
			c.avisos = append(c.avisos, fmt.Sprintf("λ de L1 del runtime (%g) distinto del de calibración (l1_lambda_calib=%g): CALIB descalibrada", *c.lambdaL1, *lc))
		}
	}
	// SOPL1 solo hace falta con el encogimiento activo: apagado no se decodifica, y si está mal el fichero abre igual.
	if f.Tiene(chispa3.SOPL1) && (c.lambdaL1 != nil || c.lambdaL2 != nil) {
		sopl, err := f.Sopl1()
		if err != nil {
			c.avisos = append(c.avisos, "SOPL1 inválida, sin mezcla de soporte: "+err.Error())
		} else {
			c.sopl = sopl
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
		if err := validarPrefijoTorre(f, t.Prefijo); err != nil {
			return err
		}
		c.torre = &t
	}
	c.maxLenQ = chispa3.MaxLenDefecto
	if f.Tiene(chispa3.L2) {
		onnx, err := f.L2()
		if err != nil {
			return fmt.Errorf("sección L2: %w", err)
		}
		if c.maxLenQ, err = chispa3.MaxLenConsulta(onnx); err != nil {
			return fmt.Errorf("sección L2: %w", err)
		}
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
			if c.conj.Version() != c.esq.Version() {
				c.avisos = append(c.avisos, fmt.Sprintf("AVISO: ESQUEMAS v%d y CONJ v%d: sus claves no se mezclan y L2c no encontrará los esquemas de CONJ; reentrene con --conjunta", c.esq.Version(), c.conj.Version()))
			}
		}
	}
	return nil
}

// Cerrar libera el fichero. Tras Cerrar no se puede llamar a nada más.
// Avisos son los problemas no fatales de la apertura, uno por línea ("" si no hubo).
func (c *Chispa) Avisos() string { return strings.Join(c.avisos, "\n") }

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
	return escribirAtomico(destino, b)
}

// escribirAtomico escribe en un temporal del mismo directorio, lo sincroniza y lo renombra: si el proceso muere a mitad,
// destino no existe o está completo, nunca truncado.
func escribirAtomico(destino string, b []byte) error {
	tmp, err := os.CreateTemp(filepath.Dir(destino), filepath.Base(destino)+".*.tmp")
	if err != nil {
		return err
	}
	ok := false
	defer func() {
		if !ok {
			tmp.Close()
			os.Remove(tmp.Name())
		}
	}()
	if _, err := tmp.Write(b); err != nil {
		return err
	}
	if err := tmp.Sync(); err != nil {
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	if err := os.Chmod(tmp.Name(), 0o600); err != nil {
		return err
	}
	if err := os.Rename(tmp.Name(), destino); err != nil {
		return err
	}
	ok = true
	return nil
}

// HashSeccion es el sha256 hex de la sección de ese tipo (chispa3.L2, chispa3.TORR…), "" si falta o está corrupta.
// Sirve para nombrar la caché del ONNX extraído.
func (c *Chispa) HashSeccion(tipo int) string {
	b, err := c.f.Bytes(chispa3.Tipo(tipo))
	if err != nil {
		return ""
	}
	h := sha256.Sum256(b)
	return hex.EncodeToString(h[:])
}

// TauL2c es el τ de la cabeza conjunta (L2c) de CALIB; −1 si el fichero no lo trae (L2c usa entonces TauEscalate).
func (c *Chispa) TauL2c() float64 {
	if c.calib.TauL2c == nil {
		return -1
	}
	return *c.calib.TauL2c
}

// TauL2EsquemaNuevoPorDefecto: τ de L2 para esquemas nuevos cuando CALIB no trae tau_l2_esquema_nuevo. Punto prudente medido sobre
// tareas no vistas: precisión 0,95 con ~97 % de escalado (el otro punto medido, 0,276, escala ≤ 20 % con precisión ~0,53).
const TauL2EsquemaNuevoPorDefecto = 0.846

// TauL2EsquemaNuevo es el τ efectivo de L2 cuando la pregunta no está en ESQUEMAS (torre al vuelo): el de CALIB si lo trae y, si no,
// TauL2EsquemaNuevoPorDefecto (0,846). Devuelve −1 solo tras SinTauEsquemaNuevo(true): sin τ propio, L2 usa TauEscalate (o TauL2c con
// CONJ). La cascada de Kotlin/Swift lee este valor al construirse, así que SinTauEsquemaNuevo debe llamarse antes.
func (c *Chispa) TauL2EsquemaNuevo() float64 {
	if c.sinTauNuevo {
		return -1
	}
	if c.calib.TauL2EsquemaNuevo == nil {
		return TauL2EsquemaNuevoPorDefecto
	}
	return *c.calib.TauL2EsquemaNuevo
}

// SinTauEsquemaNuevo(true) vuelve al comportamiento anterior al default: sin τ propio para esquemas nuevos, ignorando también el de
// CALIB (como `tau_l2_esquema_nuevo_apagado` en el servidor). Con false se restablece la prioridad CALIB > default.
func (c *Chispa) SinTauEsquemaNuevo(apagar bool) { c.sinTauNuevo = apagar }

func salida(r respuesta) string {
	b, _ := json.Marshal(r)
	return string(b)
}

func fallo(err error) string {
	return salida(respuesta{Error: err.Error(), Probs: map[string]float64{}})
}

// decodificarEstricto es el decodificador del servidor (http.go): campos desconocidos y datos tras el objeto son error.
func decodificarEstricto(js string, v any) error {
	dec := json.NewDecoder(strings.NewReader(js))
	dec.DisallowUnknownFields()
	if err := dec.Decode(v); err != nil {
		return err
	}
	if dec.More() {
		return errors.New("JSON no válido: datos tras el objeto")
	}
	return nil
}

func leerPregunta(js string) (pregunta, error) {
	var p pregunta
	if err := decodificarEstricto(js, &p); err != nil {
		return p, err
	}
	return p, comprobarPregunta(&p)
}

func comprobarPregunta(p *pregunta) error {
	switch p.Kind {
	case "choice", "noul", "score", "multi":
	case "":
		return errors.New("kind: obligatorio (choice, score, noul o multi)")
	default:
		return fmt.Errorf("kind no válido: %q", p.Kind)
	}
	return validarPregunta(p)
}

// maxEstadoByte es el tope del servidor para el texto (server/decide MaxEstadoByte).
const maxEstadoByte = 256 << 10

var errEstadoLargo = errors.New("state_too_long: el texto supera 256 KiB")

// maxOpciones es el tope del servidor (server/decide MaxOpciones).
const maxOpciones = 256

// Topes en bytes del servidor (server/decide MaxTextoByte, MaxIDByte).
const (
	maxTextoByte = 4 << 10
	maxIDByte    = 256
)

// validarPregunta aplica las reglas de server/decide (validarPeticion): choice/score/multi con ≥2 opciones, noul solo
// {false,true} (vacío → por defecto), ids de opción no vacíos ni repetidos, y MaxOpciones.
func validarPregunta(p *pregunta) error {
	if p.Texto == "" {
		return errors.New("question: obligatorio")
	}
	if len(p.Texto) > maxTextoByte {
		return fmt.Errorf("question: más de %d bytes", maxTextoByte)
	}
	if len(p.Nonce) > maxIDByte {
		return fmt.Errorf("nonce: más de %d bytes", maxIDByte)
	}
	switch p.Kind {
	case "choice", "score", "multi":
		if len(p.Opciones) < 2 {
			return fmt.Errorf("%s necesita al menos 2 opciones", p.Kind)
		}
	case "noul":
		if len(p.Opciones) == 0 {
			p.Opciones = []opcion{{ID: "false"}, {ID: "true"}}
		} else if len(p.Opciones) != 2 || firma([]string{p.Opciones[0].ID, p.Opciones[1].ID}) != firma([]string{"false", "true"}) {
			return errors.New(`noul solo admite los ids "false" y "true"`)
		}
	}
	if len(p.Opciones) > maxOpciones {
		return fmt.Errorf("máximo %d opciones", maxOpciones)
	}
	seen := map[string]bool{}
	for j, o := range p.Opciones {
		if o.ID == "" {
			return fmt.Errorf("options[%d].id: obligatorio", j)
		}
		if seen[o.ID] {
			return fmt.Errorf("options[%d].id: %q repetido", j, o.ID)
		}
		if len(o.ID) > maxIDByte {
			return fmt.Errorf("options[%d].id: más de %d bytes", j, maxIDByte)
		}
		if len(o.Description) > maxTextoByte {
			return fmt.Errorf("options[%d].description: más de %d bytes", j, maxTextoByte)
		}
		seen[o.ID] = true
	}
	return nil
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

func idsDe(p pregunta) []string {
	ids := make([]string, len(p.Opciones))
	for i, o := range p.Opciones {
		ids[i] = o.ID
	}
	return ids
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
	var sop *chispa3.EntradaSopl1
	if c.sopl != nil && c.lambdaL1 != nil && c.sopl.Dim() == c.e.Dim() {
		sop, _ = c.sopl.Buscar(chispa3.ClaveConj(p.Texto, idsDe(p)))
	}
	for i, o := range p.Opciones {
		s := []string{p.Texto, o.ID}
		if o.Description != "" {
			s = append(s, o.Description)
		}
		v[i] = make([]float32, c.e.Dim())
		c.e.Embed(strings.Join(s, " · "), v[i])
		if sop != nil {
			if k, media, ok := sop.Opcion(o.ID, c.e.Dim()); ok {
				v[i] = chispa3.Mezclar(v[i], media, chispa3.PesoSoporte(k, c.lambdaL1))
			}
		}
	}
	c.cache[k] = v
	return v
}

// Decidir es L1: coseno entre el mensaje y «pregunta · opción · descripción» y softmax con la T de CALIB (0,05 por
// defecto), como server/decide/l1.go y demo/wasm. preguntaJSON es la pregunta del servidor ({question, kind, options}).
func (c *Chispa) Decidir(texto, preguntaJSON string) string {
	if len(texto) > maxEstadoByte {
		return fallo(errEstadoLargo)
	}
	p, err := leerPregunta(preguntaJSON)
	if err != nil {
		return fallo(err)
	}
	if c.e == nil {
		return fallo(errors.New("el fichero no trae la sección L1"))
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
	if p.Kind == "score" {
		return salida(puntuarNiveles(p, sims, c.tScore()))
	}
	if p.Kind == "multi" {
		return salida(c.multi(p, sims))
	}
	return salida(softmax(p, sims, c.params("choice").T))
}

// tScore: la T de «score» si CALIB la trae; si no, la de choice (como server/decide/l1.go).
func (c *Chispa) tScore() float64 {
	if p, ok := c.calib.Tipos["score"]; ok && p.T > 0 {
		return p.T
	}
	return c.params("choice").T
}

// puntuarNiveles: softmax sobre los niveles en el orden de la pregunta; answer es la mediana
// (primer nivel con masa acumulada ≥ 0,5) y conf su probabilidad (como server/decide/l1.go).
func puntuarNiveles(p pregunta, sims []float64, T float64) respuesta {
	r := softmax(p, sims, T)
	var acc float64
	for _, o := range p.Opciones {
		acc += r.Probs[o.ID]
		if acc >= 0.5 {
			r.Answer, r.Conf = o.ID, r.Probs[o.ID]
			break
		}
	}
	r.Opina = r.Conf > 0
	return r
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

// paramsMulti son (a, b, θ) de una opción de multi: CALIB «multi#<id>», si no «multi» y si no la de «noul» (como server/decide/multi.go).
func (c *Chispa) paramsMulti(id string) chispa3.ParamsTipo {
	if p, ok := c.calib.Tipos["multi#"+id]; ok {
		return p
	}
	if p, ok := c.calib.Tipos["multi"]; ok {
		return p
	}
	return c.params("noul")
}

// multi: cada opción es un sí/no con su σ(a·s + b) y su θ; answers son las activas, probs la p de cada una (no suman 1) y conf la de la
// opción más dudosa (min de p si activa, 1−p si no), como server/decide.respuestaMulti.
func (c *Chispa) multi(p pregunta, s []float64) respuesta {
	r := respuesta{Ok: true, Opina: true, Multi: true, Probs: make(map[string]float64, len(s)), Answers: []string{}, Conf: 1}
	var top float64
	for i, o := range p.Opciones {
		prm := c.paramsMulti(o.ID)
		pr := 1 / (1 + math.Exp(-(prm.A*s[i] + prm.B)))
		r.Probs[o.ID] = pr
		cf := 1 - pr
		if pr >= prm.Theta {
			cf = pr
			r.Answers = append(r.Answers, o.ID)
			if pr > top {
				top, r.Answer = pr, o.ID
			}
		}
		r.Conf = math.Min(r.Conf, cf)
	}
	if !(r.Conf > 0) {
		r.Conf = math.SmallestNonzeroFloat64
	}
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
	if len(texto) > maxEstadoByte {
		return fallo(errEstadoLargo)
	}
	p, err := leerPregunta(preguntaJSON)
	if err != nil {
		return fallo(err)
	}
	if p.Kind == "multi" { // L0 es multiclase (probs que suman 1): no da una p por opción, no opina en multi
		return salida(respuesta{Ok: true, Probs: map[string]float64{}})
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
			return salida(ordinal(p, respuestaTF(x.tf, texto)))
		}
		pred := x.m.PredictFull(chispa.Input{Text: texto}, 0)
		probs := make(map[string]float64, len(pred.Probs))
		for _, cp := range pred.Probs {
			probs[cp.Label] = cp.Prob
		}
		return salida(ordinal(p, respuesta{Ok: true, Opina: pred.Prob > 0, Answer: pred.Label, Conf: pred.Prob, Probs: probs}))
	}
	return salida(respuesta{Ok: true, Probs: map[string]float64{}})
}

// ordinal: en score la respuesta de L0 es la mediana de la distribución (como L1, L2 y server/decide/l0.go), no el argmax.
func ordinal(p pregunta, r respuesta) respuesta {
	if p.Kind != "score" || r.Conf == 0 {
		return r
	}
	var acc float64
	for _, o := range p.Opciones {
		if acc += r.Probs[o.ID]; acc >= 0.5 {
			r.Answer, r.Conf = o.ID, r.Probs[o.ID]
			break
		}
	}
	return r
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

// MaxLenConsulta es el truncado de la consulta que declara el ONNX de L2 (`chispa.consulta.max_len`; 128 si no lo trae). Lo usa
// TokenizarE5; Kotlin y Swift no recortan por su cuenta: usan los ids que da el motor.
func (c *Chispa) MaxLenConsulta() int {
	if c.maxLenQ <= 0 { // un Chispa que no pasó por montar
		return chispa3.MaxLenDefecto
	}
	return c.maxLenQ
}

// MaxLenPasaje es el truncado del pasaje de la torre: `max_len` de la sección TORR (128 sin ella).
func (c *Chispa) MaxLenPasaje() int {
	if c.torre != nil {
		return c.torre.MaxLen
	}
	return chispa3.MaxLenDefecto
}

// TokenizarE5 devuelve los ids de «query: »+texto con <s> y </s> (como runtime/tok), truncados a MaxLenConsulta (el metadato del
// ONNX de L2, 128 por defecto), en int32 little endian, 4 bytes por id: gomobile no puede devolver []int32. Sin tokenizador
// devuelve nil.
func (c *Chispa) TokenizarE5(texto string) []byte {
	if c.tok == nil {
		return nil
	}
	ids := c.tok.TokenizarMax(tok.Prefijo, texto, c.MaxLenConsulta())
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
	// La clave la elige la versión de ESQUEMAS (HashEsquema en v1, HashEsquema2 en v2: con v2 otra descripción u otro kind
	// es otro esquema y sus torres las instala la app).
	buscar := func(ops []opcion) (torreL2, bool) {
		v, e, ok := c.esq.BuscarEsquema(p.Texto, p.Kind, clavesDe(ops))
		return torreL2{v, e}, ok
	}
	var ts []torreL2
	switch p.Kind {
	case "choice", "multi": // una torre por opción
		for _, o := range p.Opciones {
			t, ok := buscar([]opcion{o})
			if !ok {
				return c.torresNuevas(p)
			}
			ts = append(ts, t)
		}
	default:
		ops := p.Opciones
		if p.Kind == "noul" {
			ops = []opcion{{ID: "false"}, {ID: "true"}}
			for _, o := range p.Opciones {
				for i := range ops {
					if o.ID == ops[i].ID {
						ops[i].Description = o.Description
					}
				}
			}
		}
		t, ok := buscar(ops)
		if !ok {
			return c.torresNuevas(p)
		}
		ts = []torreL2{t}
	}
	return ts, nil
}

func clavesDe(ops []opcion) []chispa3.OpcionClave {
	out := make([]chispa3.OpcionClave, len(ops))
	for i, o := range ops {
		out[i] = chispa3.OpcionClave{ID: o.ID, Descripcion: o.Description}
	}
	return out
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
	case "multi":
		return salida(c.multi(p, sims))
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
			inc, ok := c.calib.Tipos[fmt.Sprintf("%s#%d", clave, j)]
			if !ok {
				return vacia
			}
			b += inc.A
		}
		sup[j] = 1 / (1 + math.Exp(-(base.A*s - b)))
	}
	r := respuesta{Ok: true, Probs: make(map[string]float64, K)}
	var suma float64
	for i := 0; i < K; i++ {
		hi, lo := 1.0, 0.0
		if i > 0 {
			hi = sup[i-1]
		}
		if i < K-1 {
			lo = sup[i]
		}
		d := math.Max(hi-lo, 0)
		r.Probs[p.Opciones[i].ID] = d
		suma += d
	}
	for id, d := range r.Probs { // acumuladas no monótonas: las diferencias recortadas suman > 1; se normaliza (como el servidor)
		r.Probs[id] = d / suma
	}
	// Mediana CORAL: nivel 1 + número de umbrales con P(y > j) > 0,5 (como L1 y el servidor).
	k := 0
	for _, x := range sup {
		if x > 0.5 {
			k++
		}
	}
	r.Answer = p.Opciones[k].ID
	r.Conf = r.Probs[r.Answer]
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
	if err := decodificarEstricto(simsJSON, &in); err != nil {
		return fallo(err)
	}
	p := in.pregunta
	if err := comprobarPregunta(&p); err != nil {
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
	e, ok := c.conj.BuscarEsquema(p.Texto, p.Kind, clavesDe(p.Opciones)) // clave de la versión de CONJ
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
	sims := simsL2(ts, S)
	var sp []float64 // nil ⇒ simproto de CONJ
	if c.sopl != nil {
		if sop, ok := c.sopl.Buscar(chispa3.ClaveConj(p.Texto, ids)); ok {
			sp = chispa3.SimprotoMezclado(e, sop, c.lambdaL2, ids, S, func(i int) ([]byte, float32, bool) { return ts[i].v, ts[i].e, true })
		}
	}
	pr := e.ProbsCabezaSp(ids, S, sims, in.L0, sp)
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
