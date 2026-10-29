// Paquete torre calcula al vuelo la torre de opción de L2 (h ∈ R^256) de un esquema que ESQUEMAS no trae: tokeniza el texto
// con «passage: », corre el ONNX de la sección TORR (e5 + cabeza de torre) y devuelve h normalizada. Contrato:
// model/l2/contrato-torre.md. La caché y la cuantización viven en decide.L2 (ConTorres); aquí solo está el codificador.
package torre

import (
	"errors"
	"fmt"
	"math"
	"strings"

	"chispa/format/chispa3"
)

const idEOS int64 = 2 // </s> de XLM-R

// ErrSinORT: este binario se compiló sin la etiqueta de build «ort».
var ErrSinORT = errors.New("torre: binario compilado sin la etiqueta ort")

// Tokenizador da los ids de e5 de un texto con el prefijo de pasaje ya puesto (<s>, </s>, truncado a 128).
// El prefijo forma parte del texto tokenizado: lo antepone el tokenizador, no el llamador.
type Tokenizador interface {
	IDsPasaje(texto string) []int64
}

// Sesion es el ONNX de la torre: ids y máscara (1,T) → h (dim). Debe ser segura para uso concurrente.
type Sesion interface {
	Embeber(ids, mascara []int64) ([]float32, error)
}

// Codificador implementa decide.CodificadorTorre sobre una Sesion.
type Codificador struct {
	ses     Sesion
	tk      Tokenizador
	prefijo string
	dim     int
	maxLen  int
}

// Nuevo monta el codificador con la sesión y los metadatos de la sección TORR (dim, max_len, prefijo).
func Nuevo(ses Sesion, tk Tokenizador, t chispa3.Torre) *Codificador {
	return &Codificador{ses: ses, tk: tk, prefijo: t.Prefijo, dim: t.Dim, maxLen: t.MaxLen}
}

// Abrir abre el ONNX de la sección con ONNX Runtime (build tag ort) y monta el codificador.
func Abrir(t chispa3.Torre, tk Tokenizador) (*Codificador, error) {
	if tk == nil {
		return nil, errors.New("torre: falta el tokenizador de e5")
	}
	ses, err := abrirSesion(t.ONNX)
	if err != nil {
		return nil, err
	}
	return Nuevo(ses, tk, t), nil
}

// Dim es la dimensión de h.
func (c *Codificador) Dim() int { return c.dim }

// Torre devuelve h para el texto de la torre «passage: pregunta · opción · descripción». Si el texto no trae el prefijo de la
// sección se le antepone (el tokenizador lo pone una sola vez: aquí se quita el que ya traiga).
func (c *Codificador) Torre(texto string) ([]float32, error) {
	ids := c.tk.IDsPasaje(strings.TrimPrefix(texto, c.prefijo))
	if len(ids) == 0 {
		return nil, errors.New("torre: texto sin tokens")
	}
	if c.maxLen > 0 && len(ids) > c.maxLen { // truncado de la sección, conservando </s>
		ids = append(ids[:c.maxLen-1:c.maxLen-1], idEOS)
	}
	mascara := make([]int64, len(ids))
	for i := range mascara {
		mascara[i] = 1
	}
	h, err := c.ses.Embeber(ids, mascara)
	if err != nil {
		return nil, err
	}
	if len(h) != c.dim {
		return nil, fmt.Errorf("torre: h de dimensión %d, esperaba %d", len(h), c.dim)
	}
	for _, x := range h {
		if math.IsNaN(float64(x)) || math.IsInf(float64(x), 0) {
			return nil, errors.New("torre: h no es finito")
		}
	}
	return h, nil
}
