package decide

import (
	"encoding/hex"
	"log"
	"math"
	"reflect"
	"strings"
	"sync"
	"sync/atomic"

	"chispa/format/chispa3"
)

// multi: cada opción es un sí/no independiente sobre «pregunta · opción · descripción». Cada una lleva su sigmoide
// σ(a·s + b) y su umbral θ; la respuesta es la lista de opciones con p ≥ θ y probs trae la p de cada opción (no suman 1).

// Claves de CALIB de multi por capa: la puntuación de L1 (coseno) y la de L2 (MaxSim e5) tienen escalas distintas, así que cada
// capa lleva las suyas: «multi» / «multi#<id>» para L1 y «multi_l2» / «multi_l2#<id>» para L2.
const (
	claveMultiL1 = "multi"
	claveMultiL2 = "multi_l2"
)

// ClaveCalibMulti es el sufijo de esquema de las claves de CALIB de multi: «@» y HashEsquema2 (pregunta, kind, opciones con su
// descripción) en hex. Con él, «multi@<hex>» / «multi@<hex>#<id>» (y las de «multi_l2») valen solo para ese esquema: una opción
// «si» o «otro» de un esquema nuevo no hereda el θ ni la a, b de otro entrenado.
func ClaveCalibMulti(p Pregunta) string {
	h := chispa3.HashEsquema2(p.Texto, p.Kind, clavesDe(p.Opciones))
	return "@" + hex.EncodeToString(h[:])
}

// indiceCalib guarda lo que se averigua una vez de una CALIB de multi (al cargar el modelo): si trae claves con esquema, y los avisos
// de «una vez por modelo». Se queda en cada L1 / L2, que viven lo que el modelo: tras una recarga hay un L1 / L2 nuevo y vuelve a avisar.
type indiceCalib struct {
	once         sync.Once
	porEsquema   bool // alguna clave «multi@…» o «multi_l2@…»: las claves sin esquema ya no se aplican
	l1Esquema    bool // alguna clave «multi@…»
	l2Esquema    bool // alguna clave «multi_l2@…»
	avisoSinL2   sync.Once
	avisoAusente sync.Once
}

func (ix *indiceCalib) carga(c chispa3.Calib) {
	ix.once.Do(func() {
		for k := range c.Tipos {
			if strings.HasPrefix(k, claveMultiL1+"@") {
				ix.l1Esquema = true
			}
			if strings.HasPrefix(k, claveMultiL2+"@") {
				ix.l2Esquema = true
			}
		}
		ix.porEsquema = ix.l1Esquema || ix.l2Esquema
	})
}

// calibPorEsquema dice si CALIB trae alguna clave de multi con esquema (la escribe `chispa train` desde que indexa por esquema).
// Si la trae, las claves sin esquema (ficheros antiguos, sin saber de qué esquema salieron) ya no se aplican.
func calibPorEsquema(c chispa3.Calib) bool {
	var ix indiceCalib
	ix.carga(c)
	return ix.porEsquema
}

// paramsMulti son (a, b, θ) de una opción en la capa de clave `clave` para el esquema `esq` (ClaveCalibMulti): «<clave><esq>#<id>»
// si existe (θ por opción), si no «<clave><esq>»; sin ellas, en ficheros antiguos (sin ninguna clave con esquema) «<clave>#<id>» y
// «<clave>»; y si tampoco la de «noul» (aproximación sin calibrar para multi), y si tampoco la de por defecto. L2 nunca usa «multi».
func paramsMulti(c chispa3.Calib, clave, esq, id string) chispa3.ParamsTipo {
	p, _ := buscarParamsMulti(c, clave, esq, id)
	return p
}

// buscarParamsMulti es paramsMulti diciendo además si salió de una CALIB de multi (true) o es el respaldo de noul / por defecto.
func buscarParamsMulti(c chispa3.Calib, clave, esq, id string) (chispa3.ParamsTipo, bool) {
	return buscarParamsMultiIx(c, calibPorEsquema(c), clave, esq, id)
}

// buscarParamsMultiIx es buscarParamsMulti con el «porEsquema» ya calculado (indiceCalib), sin recorrer CALIB.
func buscarParamsMultiIx(c chispa3.Calib, porEsquema bool, clave, esq, id string) (chispa3.ParamsTipo, bool) {
	if p, ok := c.Tipos[clave+esq+"#"+id]; ok {
		return p, true
	}
	if p, ok := c.Tipos[clave+esq]; ok {
		return p, true
	}
	if !porEsquema {
		if p, ok := c.Tipos[clave+"#"+id]; ok {
			return p, true
		}
		if p, ok := c.Tipos[clave]; ok {
			return p, true
		}
	}
	return paramsDe(c, "noul"), false
}

// hayParamsMulti dice si alguna opción tiene CALIB de multi (no el respaldo) en la capa `clave`.
func hayParamsMulti(p Pregunta, c chispa3.Calib, porEsquema bool, clave, esq string) bool {
	for _, o := range p.Opciones {
		if _, ok := buscarParamsMultiIx(c, porEsquema, clave, esq, o.ID); ok {
			return true
		}
	}
	return false
}

// respuestaMulti pone las puntuaciones s de cada opción (en el orden de la pregunta; el coseno de L1 con clave «multi» o el
// MaxSim de L2 con «multi_l2», ver respuestaMulti y respuestaMultiL2) en probabilidades calibradas por opción y en la lista de activas.
// respuestaMulti es la de L1 (y la de L3 si la usa): CALIB «multi». L1 la llama con su CALIB, así que el índice se busca por la CALIB
// (indiceDe): se calcula una vez por modelo cargado, no en cada pregunta.
func respuestaMulti(p Pregunta, s []float64, c chispa3.Calib) Respuesta {
	return indiceDe(c).respuestaMultiL1(p, s, c)
}

// respuestaMultiL2 es la de L2: CALIB «multi_l2» del esquema. Sin ella L2 no opina en multi (τ de L2 = ∞): el MaxSim de L2 tiene otra
// escala que el coseno de L1, y con la CALIB de noul marcaría activas casi todas las opciones. La cascada escala a la capa siguiente.
func respuestaMultiL2(p Pregunta, s []float64, c chispa3.Calib) Respuesta {
	esq, po := ClaveCalibMulti(p), calibPorEsquema(c)
	if !hayParamsMulti(p, c, po, claveMultiL2, esq) {
		return Respuesta{}
	}
	return respuestaMultiCapa(p, s, c, po, claveMultiL2, esq)
}

var (
	muIndices sync.Mutex
	indices   []entradaIndice // los de las últimas CALIB vistas (un modelo en servicio y, tras recargar, el anterior que acaba)
)

type entradaIndice struct {
	tipos map[string]chispa3.ParamsTipo // se guarda para que la dirección no se reutilice mientras esté aquí
	ix    *indiceCalib
}

// indiceDe devuelve el índice de la CALIB (por identidad de su mapa), creándolo la primera vez. Cada modelo recargado trae su
// propia CALIB, así que tiene su índice y su aviso.
func indiceDe(c chispa3.Calib) *indiceCalib {
	muIndices.Lock()
	defer muIndices.Unlock()
	for _, e := range indices {
		if reflect.ValueOf(e.tipos).Pointer() == reflect.ValueOf(c.Tipos).Pointer() && c.Tipos != nil {
			return e.ix
		}
	}
	ix := new(indiceCalib)
	ix.carga(c)
	if c.Tipos != nil {
		if len(indices) >= 8 {
			indices = indices[1:]
		}
		indices = append(indices, entradaIndice{c.Tipos, ix})
	}
	return ix
}

// multiCalibAusenteL1 cuenta las preguntas multi de L1 sin su CALIB (L1 no conoce a Metricas); Metricas.Escribe lo suma.
var multiCalibAusenteL1 atomic.Uint64

// respuestaMultiL1 es respuestaMulti para L1 con el índice de CALIB precalculado; si la CALIB trae claves «multi@…» y ninguna
// casa con la pregunta (texto o descripciones cambiados respecto al entrenamiento) cuenta la métrica y avisa una vez por modelo.
func (ix *indiceCalib) respuestaMultiL1(p Pregunta, s []float64, c chispa3.Calib) Respuesta {
	ix.carga(c)
	esq := ClaveCalibMulti(p)
	if ix.l1Esquema && !hayParamsMulti(p, c, ix.porEsquema, claveMultiL1, esq) {
		multiCalibAusenteL1.Add(1)
		ix.avisoAusente.Do(func() {
			log.Printf("AVISO: la CALIB trae claves multi@<hash> pero ninguna casa con una pregunta multi (%s): cae a la aproximación de noul; ¿cambió el texto o las descripciones desde `chispa train`?", esq)
		})
	}
	return respuestaMultiCapa(p, s, c, ix.porEsquema, claveMultiL1, esq)
}

// opinaMultiL2 dice si L2 opinará en esta pregunta multi (hay multi_l2 del esquema) y devuelve su clave de esquema. Si no, cuenta
// la métrica y avisa una vez por modelo; la capa debe volver sin calcular torres ni similitudes.
func (ix *indiceCalib) opinaMultiL2(p Pregunta, c chispa3.Calib, met *Metricas) (esq string, ok bool) {
	ix.carga(c)
	esq = ClaveCalibMulti(p)
	if hayParamsMulti(p, c, ix.porEsquema, claveMultiL2, esq) {
		return esq, true
	}
	met.sube(func(m *Metricas) *atomic.Uint64 { return &m.MultiL2SinCalib })
	if ix.l2Esquema {
		met.sube(func(m *Metricas) *atomic.Uint64 { return &m.MultiCalibAusente })
	}
	ix.avisoSinL2.Do(func() {
		log.Printf("AVISO: el .chispa no trae CALIB multi_l2 para este esquema de multi: L2 no opina en multi y escala (reentrena con `chispa train` y ejemplos multi, y L2)")
	})
	return esq, false
}

func respuestaMultiCapa(p Pregunta, s []float64, c chispa3.Calib, porEsquema bool, clave, esq string) Respuesta {
	pr := make([]float64, len(p.Opciones))
	th := make([]float64, len(p.Opciones))
	for i, o := range p.Opciones {
		prm, _ := buscarParamsMultiIx(c, porEsquema, clave, esq, o.ID)
		pr[i] = 1 / (1 + math.Exp(-(prm.A*s[i] + prm.B)))
		th[i] = prm.Theta
	}
	return multiDeProbs(p, pr, th)
}

// multiDeProbs arma la Respuesta de multi desde p por opción y θ por opción. Conf es la de la opción más dudosa:
// min de p (si activa) o 1−p (si no), así la capa solo acepta si todas sus decisiones pasan τ.
func multiDeProbs(p Pregunta, pr, th []float64) Respuesta {
	r := Respuesta{Probs: make(map[string]float64, len(pr)), Answers: []string{}, Conf: 1}
	var top float64
	for i, o := range p.Opciones {
		r.Probs[o.ID] = pr[i]
		c := 1 - pr[i]
		if pr[i] >= th[i] {
			c = pr[i]
			r.Answers = append(r.Answers, o.ID)
			if pr[i] > top {
				top, r.Answer = pr[i], o.ID
			}
		}
		r.Conf = math.Min(r.Conf, c)
	}
	if !(r.Conf > 0) { // p exactamente en el extremo: confianza 0 = «sin opinión»; se deja un mínimo para que cuente
		r.Conf = math.SmallestNonzeroFloat64
	}
	return r
}
