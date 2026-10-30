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
	"sync/atomic"
	"unicode"

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

// embebedorIDs lo cumple *l1.Modelo: tokenizar y sumar por separado, que es lo que hace falta para trocear. Un embebedor falso que no
// lo cumpla se queda con la cabeza.
type embebedorIDs interface {
	embebedor
	TokenizarTruncado(texto string) ([]int32, bool)
	TokenizarSinTope(texto string, maxRunas int) []int32
	EmbedIDs(ids []int32, out []float32) bool
	MaxTokens() int
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
	// EsquemaNuevo: las torres de la pregunta no están en ESQUEMAS (salieron al vuelo); como Respuesta.EsquemaNuevo del servidor.
	EsquemaNuevo bool `json:"esquema_nuevo,omitempty"`
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

	largo  tok.TextoLargo // estrategia para textos que pasan del truncado (AbrirConTextoLargo); cero = cabeza
	largoN atomic.Int64   // textos que pasaron del truncado de L1 o de la consulta de L2 (TextoLargoSuperados)

	sopl        *chispa3.Sopl1 // sección SOPL1 (soporte few-shot: k y media de L1 por opción), o nil
	lambdaL1    *float64       // λ del encogimiento del soporte en L1; nil = apagado; 0 = solo ejemplos; +Inf = solo descripción
	lambdaL2    *float64       // ídem en L2c
	explicitoL1 bool           // el λ de L1 lo pidió el llamador (AbrirConSoporte), no es el default de Abrir
	avisos      []string       // problemas no fatales al abrir (p. ej. SOPL1 inválida con el encogimiento activo)

	calibOnce  sync.Once
	calibInfo  [2]infoMulti // [0] tipos (L1), [1] tipos que lee L2
	multiAus   atomic.Int64 // peticiones multi cuya CALIB tiene claves con esquema de la capa y ninguna casa
	avisoMulti sync.Once

	defecto contadorDefecto // decisiones con parámetros de CALIB por defecto (CalibDefectoJSON)

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

// AbrirConTextoLargo es AbrirConSoporte (o Abrir, con explicito=false: los λ se ignoran y valen los de Abrir) con la estrategia para textos que pasan del truncado de L1 (max_tokens del modelo) y de
// L2 (chispa.consulta.max_len): textoLargoJSON es el mismo objeto que `texto_largo` del servidor,
// {"estrategia":"cabeza|cabeza_cola|trozos","agregacion":"max|media","solape":N,"max_trozos":N,"ventana_l1":N}. "" o "{}" =
// cabeza, lo de siempre (bit a bit). Con cabeza_cola, L1 y TokenizarE5 usan los N/2 primeros y últimos tokens; con trozos,
// L1 decide cada ventana aquí y para L2 la app pide las ventanas con TrozosE5 y las puntúa con PuntuarL2Trozos. Un JSON mal formado, con
// claves desconocidas o con valores fuera de rango es un error.
func AbrirConTextoLargo(ruta string, lambdaL1, lambdaL2 float64, explicito bool, textoLargoJSON string) (*Chispa, error) {
	var tl tok.TextoLargo
	if strings.TrimSpace(textoLargoJSON) != "" {
		if err := decodificarEstricto(textoLargoJSON, &tl); err != nil {
			return nil, fmt.Errorf("texto_largo: %w", err)
		}
	}
	if err := tl.Validar(); err != nil {
		return nil, err
	}
	if !explicito {
		lambdaL1, lambdaL2 = SoporteL1PorDefecto, SoporteApagado
	}
	c, err := abrir(ruta, lambdaL1, lambdaL2, explicito)
	if err != nil {
		return nil, err
	}
	c.largo = tl
	return c, nil
}

// TextoLargoSuperados cuenta los textos que pasaron del truncado de L1 (Decidir) o de la consulta de L2 (TokenizarE5, TrozosE5).
func (c *Chispa) TextoLargoSuperados() int64 { return c.largoN.Load() }

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
	c.avisarCalib()
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

// TauEscalate es el τ de CALIB para L1 (0 si el fichero no trae CALIB; entonces la cascada usa el suyo).
func (c *Chispa) TauEscalate() float64 { return c.calib.TauEscalate }

// TauEscalateL2 es el τ de CALIB para L2: tau_escalate_l2 si el fichero lo trae y, si no, TauEscalate (ficheros anteriores).
func (c *Chispa) TauEscalateL2() float64 { return c.calib.ParaL2().TauEscalate }

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

func comprobarPregunta(p *pregunta) error { return validarPregunta(p) }

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
	// como el escáner del servidor: el tope de opciones salta antes que los demás errores de la pregunta
	if len(p.Opciones) > maxOpciones {
		return codigo("too_many_options", "máximo %d opciones", maxOpciones)
	}
	if p.Texto == "" {
		return codigo("missing_question", "question: obligatorio")
	}
	if len(p.Texto) > maxTextoByte {
		return codigo("field_too_long", "question: más de %d bytes", maxTextoByte)
	}
	if tieneSeparador(p.Texto) {
		return errSeparador("question")
	}
	if len(p.Nonce) > maxIDByte {
		return codigo("field_too_long", "nonce: más de %d bytes", maxIDByte)
	}
	switch p.Kind {
	case "choice", "score", "multi":
		if len(p.Opciones) < 2 {
			return codigo("too_few_options", "%s necesita al menos 2 opciones", p.Kind)
		}
	case "noul":
		if len(p.Opciones) == 0 {
			p.Opciones = []opcion{{ID: "false"}, {ID: "true"}}
		} else if len(p.Opciones) != 2 || firma([]string{p.Opciones[0].ID, p.Opciones[1].ID}) != firma([]string{"false", "true"}) {
			return codigo("invalid_options", `noul solo admite los ids "false" y "true"`)
		}
	case "":
		return codigo("missing_kind", "kind: obligatorio (choice, score, noul o multi)")
	default:
		return codigo("invalid_kind", "kind: %q no válido (choice, score, noul o multi)", p.Kind)
	}
	if len(p.Opciones) > maxOpciones {
		return codigo("too_many_options", "máximo %d opciones", maxOpciones)
	}
	seen := map[string]bool{}
	for j, o := range p.Opciones {
		if o.ID == "" {
			return codigo("missing_option_id", "options[%d].id: obligatorio", j)
		}
		if len(o.ID) > maxIDByte {
			return codigo("field_too_long", "options[%d].id: más de %d bytes", j, maxIDByte)
		}
		if len(o.Description) > maxTextoByte {
			return codigo("field_too_long", "options[%d].description: más de %d bytes", j, maxTextoByte)
		}
		if tieneSeparador(o.ID) {
			return errSeparador(fmt.Sprintf("options[%d].id", j))
		}
		if tieneSeparador(o.Description) {
			return errSeparador(fmt.Sprintf("options[%d].description", j))
		}
		if seen[o.ID] {
			return codigo("duplicate_option_id", "options[%d].id: %q repetido", j, o.ID)
		}
		seen[o.ID] = true
	}
	return nil
}

// codigo da un error «<código>: mensaje» con el código del servidor (server/decide http.go Err*); Android e iOS solo ven el texto.
func codigo(code, format string, a ...any) error {
	return fmt.Errorf("%s: %s", code, fmt.Sprintf(format, a...))
}

// tieneSeparador dice si s trae U+001D–U+001F, los separadores de HashEsquema2 (sin prefijos de longitud); como el servidor.
func tieneSeparador(s string) bool { return strings.ContainsAny(s, "\x1d\x1e\x1f") }

func errSeparador(campo string) error {
	return fmt.Errorf("invalid_characters: %s no admite los caracteres de control U+001D–U+001F", campo)
}

// params son los parámetros de un tipo en los tipos de L1.
func (c *Chispa) params(tipo string) chispa3.ParamsTipo {
	return c.paramsCapa("L1", c.calib.Tipos, tipo)
}

// paramsL2 son los parámetros de un tipo en los tipos que lee L2 (tipos_l2 si existen, si no tipos).
func (c *Chispa) paramsL2(tipo string) chispa3.ParamsTipo {
	return c.paramsCapa("L2", c.calib.ParaL2().Tipos, tipo)
}

func paramsTipo(tipos map[string]chispa3.ParamsTipo, tipo string) chispa3.ParamsTipo {
	if p, ok := tipos[tipo]; ok {
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

// idsOrdenados son los ids en el orden que usa la agregación: por nivel en score, el declarado en el resto.
func idsOrdenados(p pregunta) []string {
	if p.Kind != "score" {
		return idsDe(p)
	}
	ops, _ := ordenNivel(p.Opciones)
	return idsDe(pregunta{Opciones: ops})
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
	msgs := c.ventanasMsg(texto)
	if len(msgs) == 0 {
		return salida(respuesta{Ok: true, Probs: map[string]float64{}})
	}
	ops := c.torres(p)
	sims := make([][]float64, len(msgs))
	for w, msg := range msgs {
		sims[w] = make([]float64, len(ops))
		for i, o := range ops {
			for j := range msg {
				sims[w][i] += float64(msg[j]) * float64(o[j])
			}
		}
	}
	agg := c.largo.Agg()
	if p.Kind == "multi" { // cada opción, un sí/no sobre su similitud: se agregan las similitudes
		return salida(c.multi(p, tok.AgregarSims(sims, agg)))
	}
	rs := make([]respuesta, len(sims))
	theta := 0.5
	for w, s := range sims {
		switch p.Kind {
		case "noul":
			prm := c.params("noul")
			theta = prm.Theta
			var st float64
			for i, o := range p.Opciones {
				if o.ID == "true" {
					st = s[i]
				}
			}
			rs[w] = noul(prm.A*st+prm.B, prm.Theta)
		case "score":
			rs[w] = puntuarNiveles(p, s, c.tScore())
		default:
			rs[w] = softmax(p, s, c.params("choice").T)
		}
	}
	return salida(agregarVentanas(p, rs, agg, theta))
}

// agregarVentanas reúne las respuestas de las ventanas de un texto largo (tok.AgregarProbs, la misma que el servidor). Una sola, o
// una sin opinión, se devuelve tal cual.
func agregarVentanas(p pregunta, rs []respuesta, agg string, theta float64) respuesta {
	if len(rs) == 1 || !rs[0].Opina || rs[0].Probs == nil {
		return rs[0]
	}
	ps := make([]map[string]float64, len(rs))
	for i, r := range rs {
		ps[i] = r.Probs
	}
	probs, ans, conf, ok := tok.AgregarProbs(p.Kind, idsOrdenados(p), ps, agg, theta)
	if !ok {
		return rs[0]
	}
	return respuesta{Ok: true, Opina: conf > 0, Answer: ans, Conf: conf, Probs: probs}
}

// ventanasMsg devuelve el embedding de cada ventana del mensaje en L1 (las sin tokens se omiten). Sin estrategia, o con un texto que
// cabe, es la única de siempre (c.e.Embed del texto entero); como el servidor (server/decide/l1.go).
func (c *Chispa) ventanasMsg(texto string) [][]float32 {
	dim := c.e.Dim()
	un := func(emb func(out []float32) bool) [][]float32 {
		e := make([]float32, dim)
		if !emb(e) {
			return nil
		}
		return [][]float32{e}
	}
	entero := func() [][]float32 { return un(func(out []float32) bool { return c.e.Embed(texto, out) }) }
	m, ok := c.e.(embebedorIDs)
	if !ok {
		return entero()
	}
	n := m.MaxTokens()
	if c.largo.VentanaL1 > 0 {
		n = min(n, c.largo.VentanaL1)
	}
	if !c.largo.Activa() {
		ids, trunc := m.TokenizarTruncado(texto)
		if trunc {
			c.largoN.Add(1)
		}
		return un(func(out []float32) bool { return m.EmbedIDs(ids, out) })
	}
	todo := m.TokenizarSinTope(texto, c.largo.NecesitaTokens(n)*16)
	if len(todo) <= n {
		ids, trunc := m.TokenizarTruncado(texto)
		if trunc {
			c.largoN.Add(1)
		}
		return un(func(out []float32) bool { return m.EmbedIDs(ids, out) })
	}
	c.largoN.Add(1)
	var out [][]float32
	for _, w := range tok.Trocear(todo, n, c.largo) {
		out = append(out, un(func(o []float32) bool { return m.EmbedIDs(w, o) })...)
	}
	return out
}

// tScore: la T de «score» si CALIB la trae; si no, la de choice (como server/decide/l1.go).
func (c *Chispa) tScore() float64 {
	if p, ok := c.calib.Tipos["score"]; ok && p.T > 0 {
		return p.T
	}
	if _, ok := c.calib.Tipos["choice"]; !ok {
		c.defecto.sube("L1", "score")
		return tDefecto
	}
	return c.params("choice").T
}

// puntuarNiveles: softmax sobre los niveles en el orden de la pregunta; answer es la mediana
// (primer nivel con masa acumulada ≥ 0,5) y conf su probabilidad (como server/decide/l1.go).
func puntuarNiveles(p pregunta, sims []float64, T float64) respuesta {
	r := softmax(p, sims, T)
	var acc float64
	ops, _ := ordenNivel(p.Opciones)
	for _, o := range ops {
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

// claveCalibMulti es el sufijo de esquema de las claves de CALIB de multi: «@» y HashEsquema2 en hex (como server/decide.ClaveCalibMulti).
func claveCalibMulti(p pregunta) string {
	h := chispa3.HashEsquema2(p.Texto, p.Kind, clavesDe(p.Opciones))
	return "@" + hex.EncodeToString(h[:])
}

// infoMulti dice qué claves de multi con esquema trae un mapa de tipos.
type infoMulti struct {
	esq  bool    // alguna clave de multi con esquema («multi@…» o «multi_l2@…»)
	capa [2]bool // por capa: [0] «multi@», [1] «multi_l2@»
}

// calibPorEsquema: los tipos de la capa (L2 o L1) traen alguna clave de multi con esquema; si la traen, las claves sin esquema
// (ficheros antiguos) no se aplican. Se calcula una vez (no por opción). Sin tipos_l2, L1 y L2 leen el mismo mapa.
func (c *Chispa) calibPorEsquema(l2 bool) infoMulti {
	c.calibOnce.Do(func() {
		for i, tipos := range [2]map[string]chispa3.ParamsTipo{c.calib.Tipos, c.calib.ParaL2().Tipos} {
			inf := &c.calibInfo[i]
			for k := range tipos {
				if strings.HasPrefix(k, "multi@") {
					inf.capa[0] = true
				} else if strings.HasPrefix(k, "multi_l2@") {
					inf.capa[1] = true
				}
			}
			inf.esq = inf.capa[0] || inf.capa[1]
		}
	})
	if l2 {
		return c.calibInfo[1]
	}
	return c.calibInfo[0]
}

// MultiCalibAusente cuenta las peticiones de multi cuya CALIB trae claves con esquema para esa capa y ninguna casa con la pregunta
// (el texto o las descripciones cambiaron: L1 cae a la CALIB de noul). Equivale a chispa_multi_calib_ausente_total del servidor.
func (c *Chispa) MultiCalibAusente() int64 { return c.multiAus.Load() }

// avisarCalibAusente apunta la CALIB de multi perdida; el aviso (Avisos) sale una sola vez.
func (c *Chispa) avisarCalibAusente(capa string) {
	c.multiAus.Add(1)
	c.avisoMulti.Do(func() {
		c.mu.Lock()
		defer c.mu.Unlock()
		c.avisos = append(c.avisos, "CALIB de "+capa+" trae claves multi con esquema y ninguna casa con la pregunta (¿cambió el texto o una descripción?): cae a la CALIB de noul")
	})
}

// paramsMultiCapa son (a, b, θ) de una opción de multi en la capa `clave` («multi» L1, «multi_l2» L2) para el esquema `esq`:
// «<clave><esq>#<id>», si no «<clave><esq>»; en ficheros sin claves con esquema, «<clave>#<id>» y «<clave>»; si no la de «noul»
// (como server/decide/multi.go). Las de «multi» salen de cosenos de L1 (otra escala) y no valen para MaxSim.
func (c *Chispa) paramsMultiCapa(clave, esq, id string) chispa3.ParamsTipo {
	p, _ := c.buscarParamsMulti(clave, esq, id)
	return p
}

// buscarParamsMulti es paramsMultiCapa diciendo además si salió de una CALIB de multi (true) o es el respaldo de noul.
func (c *Chispa) buscarParamsMulti(clave, esq, id string) (chispa3.ParamsTipo, bool) {
	l2 := clave == "multi_l2"
	tipos := c.calib.Tipos
	if l2 {
		tipos = c.calib.ParaL2().Tipos
	}
	if p, ok := tipos[clave+esq+"#"+id]; ok {
		return p, true
	}
	if p, ok := tipos[clave+esq]; ok {
		return p, true
	}
	if !c.calibPorEsquema(l2).esq {
		if p, ok := tipos[clave+"#"+id]; ok {
			return p, true
		}
		if p, ok := tipos[clave]; ok {
			return p, true
		}
	}
	return paramsTipo(tipos, "noul"), false
}

func (c *Chispa) paramsMultiDe(p pregunta, esq, clave string) []chispa3.ParamsTipo {
	prms := make([]chispa3.ParamsTipo, len(p.Opciones))
	casa := false
	for i, o := range p.Opciones {
		var ok bool
		prms[i], ok = c.buscarParamsMulti(clave, esq, o.ID)
		casa = casa || ok
	}
	if inf := c.calibPorEsquema(clave == "multi_l2"); !casa && inf.esq {
		capa := 0
		if clave == "multi_l2" {
			capa = 1
		}
		if inf.capa[capa] {
			c.avisarCalibAusente(clave)
		}
	}
	return prms
}

// l2OpinaMulti: L2 solo opina en multi con alguna CALIB «multi_l2» del esquema (como server/decide.respuestaMultiL2); si no, no vale
// calcular torres ni ejecutar el ONNX.
func (c *Chispa) l2OpinaMulti(p pregunta, esq string) bool {
	for _, o := range p.Opciones {
		if _, ok := c.buscarParamsMulti("multi_l2", esq, o.ID); ok {
			return true
		}
	}
	return false
}

// multiL2 es multi sobre el MaxSim de L2 con las cabezas por capa.
// Sin CALIB «multi_l2» del esquema L2 no opina en multi (como server/decide.respuestaMultiL2).
func (c *Chispa) multiL2(p pregunta, s []float64) respuesta {
	esq := claveCalibMulti(p)
	if !c.l2OpinaMulti(p, esq) {
		return respuesta{Ok: true, Probs: map[string]float64{}}
	}
	return multiDe(p, s, c.paramsMultiDe(p, esq, "multi_l2"))
}

// multi: cada opción es un sí/no con su σ(a·s + b) y su θ; answers son las activas, probs la p de cada una (no suman 1) y conf la de la
// opción más dudosa (min de p si activa, 1−p si no), como server/decide.respuestaMulti.
func (c *Chispa) multi(p pregunta, s []float64) respuesta {
	return multiDe(p, s, c.paramsMultiDe(p, claveCalibMulti(p), "multi"))
}

func multiDe(p pregunta, s []float64, prms []chispa3.ParamsTipo) respuesta {
	r := respuesta{Ok: true, Opina: true, Multi: true, Probs: make(map[string]float64, len(s)), Answers: []string{}, Conf: 1}
	var top float64
	for i, o := range p.Opciones {
		prm := prms[i]
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
	ops, _ := ordenNivel(p.Opciones)
	for _, o := range ops {
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
// ONNX de L2, 128 por defecto), en int32 little endian, 4 bytes por id: gomobile no puede devolver []int32. Con la estrategia de
// AbrirConTextoLargo es la primera ventana: la cabeza (cabeza y trozos) o la cabeza_cola. Sin tokenizador devuelve nil.
func (c *Chispa) TokenizarE5(texto string) []byte {
	v := c.ventanasE5(texto)
	if v == nil {
		return nil
	}
	return idsABytes(v[0])
}

// TrozosE5 devuelve las ventanas de la consulta que decide la estrategia (como mucho max_trozos; una sola si el texto cabe o la
// estrategia no es «trozos»), cada una con sus <s> y </s> y a lo sumo MaxLenConsulta ids: int32 little endian, [n][len₁][ids₁…][len₂][ids₂…]…
// La app corre ONNX en cada una y pasa las ranuras concatenadas a PuntuarL2Trozos. Sin tokenizador devuelve nil.
func (c *Chispa) TrozosE5(texto string) []byte {
	v := c.ventanasE5(texto)
	if v == nil {
		return nil
	}
	b := binary.LittleEndian.AppendUint32(nil, uint32(len(v)))
	for _, w := range v {
		b = binary.LittleEndian.AppendUint32(b, uint32(len(w)))
		b = append(b, idsABytes(w)...)
	}
	return b
}

func (c *Chispa) ventanasE5(texto string) [][]int32 {
	if c.tok == nil {
		return nil
	}
	v, largo := c.tok.Ventanas(tok.Prefijo, NormalizarMayusculas(texto), c.MaxLenConsulta(), c.largo)
	if largo {
		c.largoN.Add(1)
	}
	return v
}

// NormalizarMayusculas aplica el contrato de normalización de mayúsculas (docs/contrato-normalizacion.md): con al menos 8 letras
// y más del 70 % en mayúscula devuelve el texto en minúsculas; si no, el mismo. TokenizarE5 y TrozosE5 la aplican al mensaje
// entero antes de anteponer «query: », tokenizar y ventanear; L0 y L1 no. Función propia: no depende del servidor.
func NormalizarMayusculas(texto string) string {
	letras, mayus := 0, 0
	for _, r := range texto {
		if unicode.IsLetter(r) {
			letras++
			if unicode.IsUpper(r) {
				mayus++
			}
		}
	}
	if letras >= 8 && mayus*10 > 7*letras {
		return strings.ToLower(texto)
	}
	return texto
}

func idsABytes(ids []int32) []byte {
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
	if err != nil || !c.tieneL2 || c.sinOpinionMulti(p, true) {
		return false
	}
	_, err = c.torresL2(p)
	return err == nil
}

// sinOpinionMulti: contar solo en TorresL2 (una vez por petición; el cliente llama luego a TextosTorreL2/PuntuarL2). Multi sin CALIB «multi_l2» del esquema; L2 no opinará, así que ni se piden torres ni se ejecuta ONNX.
func (c *Chispa) sinOpinionMulti(p pregunta, contar bool) bool {
	if p.Kind != "multi" || c.l2OpinaMulti(p, claveCalibMulti(p)) {
		return false
	}
	// CALIB multi_l2 con esquema pero ninguna casa con la pregunta: lo cuenta como el servidor (multi_l2_sin_calib).
	if contar && c.calibPorEsquema(true).capa[1] {
		c.avisarCalibAusente("multi_l2")
	}
	return true
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

// esquemaNuevo dice si ESQUEMAS no trae las torres de la pregunta; mira solo c.esq, no la caché de torres al vuelo
// (como server/decide/l2.go esquemaNuevo).
func (c *Chispa) esquemaNuevo(p pregunta) bool {
	if c.esq == nil {
		return true
	}
	if p.Kind == "choice" || p.Kind == "multi" {
		for _, o := range p.Opciones {
			if _, _, ok := c.esq.BuscarEsquema(p.Texto, p.Kind, clavesDe([]opcion{o})); !ok {
				return true
			}
		}
		return false
	}
	_, _, ok := c.esq.BuscarEsquema(p.Texto, p.Kind, clavesDe(opcionesUnica(p)))
	return !ok
}

// EsquemaEnEsquemas dice si la sección ESQUEMAS trae las torres de la pregunta (preguntaJSON como en las demás llamadas);
// false si no (o no hay L2): entonces L2 puntúa con torres al vuelo y la cascada usa el τ de esquema nuevo.
func (c *Chispa) EsquemaEnEsquemas(preguntaJSON string) bool {
	p, err := leerPregunta(preguntaJSON)
	return err == nil && c.tieneL2 && !c.esquemaNuevo(p)
}

// ordenNivel ordena las opciones de un score por nivel: por id numérico ("2" < "10") si todos son enteros; si alguno no lo es,
// conserva el orden declarado (nunca lexicográfico). El bool dice si todos eran numéricos.
func ordenNivel(ops []opcion) ([]opcion, bool) {
	out := append([]opcion(nil), ops...)
	for _, o := range out {
		if _, err := strconv.Atoi(o.ID); err != nil {
			return out, false
		}
	}
	sort.SliceStable(out, func(i, j int) bool {
		a, _ := strconv.Atoi(out[i].ID)
		b, _ := strconv.Atoi(out[j].ID)
		return a < b
	})
	return out, true
}

// opcionesUnica son las opciones de la única torre de noul (false y true con la descripción de la pregunta) y de score (todas).
func opcionesUnica(p pregunta) []opcion {
	if p.Kind == "score" {
		ops, _ := ordenNivel(p.Opciones)
		return ops
	}
	if p.Kind != "noul" {
		return p.Opciones
	}
	ops := []opcion{{ID: "false"}, {ID: "true"}}
	for _, o := range p.Opciones {
		for i := range ops {
			if o.ID == ops[i].ID {
				ops[i].Description = o.Description
			}
		}
	}
	return ops
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
	return c.puntuarL2(preguntaJSON, ranuras, []int{k})
}

// PuntuarL2Trozos es PuntuarL2 para un texto largo con varias ventanas (TrozosE5): ranuras son las de cada ventana una tras otra
// y ksJSON el número de ranuras de cada una ([k₁,k₂,…]). Se puntúa cada ventana y se agregan las probabilidades según la
// estrategia de AbrirConTextoLargo (max o media; en multi, las similitudes). Con una sola ventana es PuntuarL2.
func (c *Chispa) PuntuarL2Trozos(preguntaJSON string, ranuras []byte, ksJSON string) string {
	var ks []int
	if err := json.Unmarshal([]byte(ksJSON), &ks); err != nil || len(ks) == 0 || len(ks) > tok.TopeMaxTrozos {
		return fallo(fmt.Errorf("ks: hace falta una lista de 1 a %d números de ranuras", tok.TopeMaxTrozos))
	}
	return c.puntuarL2(preguntaJSON, ranuras, ks)
}

func (c *Chispa) puntuarL2(preguntaJSON string, ranuras []byte, ks []int) string {
	p, err := leerPregunta(preguntaJSON)
	if err != nil {
		return fallo(err)
	}
	if !c.tieneL2 {
		return fallo(errors.New("el fichero no trae las secciones L2 y ESQUEMAS"))
	}
	if c.sinOpinionMulti(p, false) {
		return salida(respuesta{Ok: true, Probs: map[string]float64{}})
	}
	ts, err := c.torresL2(p)
	if err != nil {
		return salida(respuesta{Ok: true, Probs: map[string]float64{}})
	}
	Ss, err := ventanasRanuras(ranuras, ks, len(ts[0].v))
	if err != nil {
		return fallo(err)
	}
	sims := make([][]float64, len(Ss))
	for i, S := range Ss {
		sims[i] = simsL2(ts, S)
	}
	agg := c.largo.Agg()
	var r respuesta
	if p.Kind == "multi" {
		r = c.multiL2(p, tok.AgregarSims(sims, agg))
	} else {
		rs := make([]respuesta, len(sims))
		theta := 0.5
		for i, s := range sims {
			switch p.Kind {
			case "choice":
				rs[i] = softmax(p, s, c.paramsL2("choice").T)
			case "noul":
				prm := c.paramsL2("noul")
				theta = prm.Theta
				rs[i] = noul(prm.A*s[0]+prm.B, prm.Theta)
			default:
				rs[i] = c.score(p, s[0])
			}
		}
		r = agregarVentanas(p, rs, agg, theta)
	}
	r.EsquemaNuevo = r.Opina && c.esquemaNuevo(p)
	return salida(r)
}

// ventanasRanuras parte las ranuras concatenadas de varias ventanas (ks[i] ranuras de d floats cada una).
func ventanasRanuras(b []byte, ks []int, d int) ([][][]float32, error) {
	var total int
	for _, k := range ks {
		if k <= 0 {
			return nil, fmt.Errorf("L2: ventana con %d ranuras", k)
		}
		total += k
	}
	if len(b) != 4*total*d {
		return nil, fmt.Errorf("L2: %d bytes de ranuras no son %d×%d float32", len(b), total, d)
	}
	out := make([][][]float32, len(ks))
	for i, k := range ks {
		S, err := ranurasDe(b[:4*k*d], k, d)
		if err != nil {
			return nil, err
		}
		out[i], b = S, b[4*k*d:]
	}
	return out, nil
}

// score: CORAL, P(y>j) = σ(a·s − b_j); b_1 = b de «scoreK» y b_j = b_{j−1} + a de «scoreK#j».
func (c *Chispa) score(p pregunta, s float64) respuesta {
	vacia := respuesta{Ok: true, Probs: map[string]float64{}}
	K := len(p.Opciones)
	// El orden de los niveles es el del id numérico (como el servidor y model/l2/modelo.py): el orden de la petición no cambia la
	// respuesta. Si ningún id es entero se conserva el orden declarado (Python rechaza esos casos); una mezcla no opina.
	ops, numerico := ordenNivel(p.Opciones)
	if !numerico {
		for _, o := range ops {
			if _, err := strconv.Atoi(o.ID); err == nil {
				return vacia // mezcla de ids enteros y no enteros: el nivel sería ambiguo
			}
		}
	} else {
		for i, o := range ops {
			if o.ID != strconv.Itoa(i+1) {
				return vacia // las cabezas de score numéricas van sobre 1..K
			}
		}
	}
	clave := "score" + strconv.Itoa(K)
	base, ok := c.calib.ParaL2().Tipos[clave]
	if !ok || K < 2 {
		return vacia
	}
	sup := make([]float64, K-1) // P(y > j+1)
	b := base.B
	for j := 0; j < K-1; j++ {
		if j > 0 {
			inc, ok := c.calib.ParaL2().Tipos[fmt.Sprintf("%s#%d", clave, j)]
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
		r.Probs[ops[i].ID] = d
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
	r.Answer = ops[k].ID
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
	// Ks, para un texto largo con trozos: las ranuras de cada ventana (TrozosE5), una tras otra, y cuántas tiene cada una; si
	// viene, K se ignora. La cabeza decide cada ventana y se agregan las probabilidades (como server/decide/l2c.go).
	Ks []int `json:"ks,omitempty"`
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
	ks := in.Ks
	if len(ks) == 0 {
		ks = []int{in.K}
	}
	if len(ks) > tok.TopeMaxTrozos {
		return fallo(fmt.Errorf("ks: como mucho %d ventanas", tok.TopeMaxTrozos))
	}
	flat := make([]byte, 0, 4*len(in.Ranuras))
	for _, v := range in.Ranuras {
		flat = binary.LittleEndian.AppendUint32(flat, math.Float32bits(v))
	}
	Ss, err := ventanasRanuras(flat, ks, len(ts[0].v))
	if err != nil {
		return fallo(err)
	}
	if len(Ss[0][0]) != e.D {
		return sinOpinar
	}
	rs := make([]respuesta, len(Ss))
	for w, S := range Ss {
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
		rs[w] = r
	}
	r := agregarVentanas(p, rs, c.largo.Agg(), 0.5)
	r.EsquemaNuevo = r.Opina && c.esquemaNuevo(p)
	return salida(r)
}
