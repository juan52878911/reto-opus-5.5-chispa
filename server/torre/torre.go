// Paquete torre calcula al vuelo la torre de opción de L2 (h ∈ R^256) de un esquema que ESQUEMAS no trae: tokeniza el texto
// con «passage: », corre el ONNX de la sección TORR (e5 + cabeza de torre) y devuelve h normalizada. Contrato:
// model/l2/contrato-torre.md. La caché y la cuantización viven en decide.L2 (ConTorres); aquí solo está el codificador.
package torre

import (
	"context"
	"errors"
	"fmt"
	"io"
	"math"
	"strings"

	"chispa/format/chispa3"
)

const idEOS int64 = 2 // </s> de XLM-R

// prefijoPasaje es el que antepone el tokenizador (IDsPasaje) y el que lleva el texto de torre.
const prefijoPasaje = "passage: "

// prefijoPorVersion: prefijo que exige cada versión de la sección TORR. TORR v2 solo añade la versión del texto: mismo prefijo que v1.
var prefijoPorVersion = map[uint32]string{1: prefijoPasaje, 2: prefijoPasaje}

// ValidarPrefijo rechaza una sección TORR cuyo prefijo no es el de su versión (o de versión desconocida).
func ValidarPrefijo(version uint32, prefijo string) error {
	want, ok := prefijoPorVersion[version]
	if !ok {
		return fmt.Errorf("TORR: versión %d desconocida", version)
	}
	if prefijo != want {
		return fmt.Errorf("TORR v%d: prefijo %q no válido; se espera %q", version, prefijo, want)
	}
	return nil
}

// ErrSinORT: este binario se compiló sin la etiqueta de build «ort».
var ErrSinORT = errors.New("torre: binario compilado sin la etiqueta ort")

// Tokenizador da los ids de e5 de un texto con el prefijo de pasaje ya puesto (<s>, </s>, truncado a max_len de TORR, 128 por defecto).
// El prefijo forma parte del texto tokenizado: lo antepone el tokenizador, no el llamador.
type Tokenizador interface {
	IDsPasaje(texto string) []int64
}

// Sesion es el ONNX de la torre: ids y máscara (1,T) → h (dim). Debe ser segura para uso concurrente.
type Sesion interface {
	Embeber(ids, mascara []int64) ([]float32, error)
}

// SesionCtx es Sesion que espera su turno respetando el ctx (la de ORT); el codificador la usa si la sesión la implementa.
type SesionCtx interface {
	EmbeberCtx(ctx context.Context, ids, mascara []int64) ([]float32, error)
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

// Close libera la sesión del codificador si tiene algo que liberar (la de ORT); no hace nada con sesiones sin Close.
func (c *Codificador) Close() error {
	if cl, ok := c.ses.(io.Closer); ok {
		return cl.Close()
	}
	return nil
}

// Dim es la dimensión de h.
func (c *Codificador) Dim() int { return c.dim }

// Torre devuelve h para el texto de la torre «passage: pregunta · opción · descripción». El tokenizador antepone «passage: »
// él mismo, así que aquí se quita el que traiga el texto: sale una sola vez, sea cual sea el prefijo de la sección.
func (c *Codificador) Torre(texto string) ([]float32, error) {
	return c.TorreCtx(context.Background(), texto)
}

// TorreCtx es Torre que no espera el turno de ORT más allá del ctx (decide.CodificadorTorreCtx).
func (c *Codificador) TorreCtx(ctx context.Context, texto string) ([]float32, error) {
	ids := c.tk.IDsPasaje(strings.TrimPrefix(texto, prefijoPasaje))
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
	var h []float32
	var err error
	if sc, ok := c.ses.(SesionCtx); ok {
		h, err = sc.EmbeberCtx(ctx, ids, mascara)
	} else {
		h, err = c.ses.Embeber(ids, mascara)
	}
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
