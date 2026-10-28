//go:build !ort

package decide

import (
	"errors"

	"chispa/format/chispa3"
)

// ErrSinORT: este binario se compiló sin la etiqueta de build «ort».
var ErrSinORT = errors.New("L2: binario compilado sin la etiqueta ort (ver README)")

// NuevoL2ORT no puede montar L2 sin ONNX Runtime; el llamador deja el stub.
func NuevoL2ORT(onnx []byte, esq *chispa3.Esquemas, calib chispa3.Calib, tok Tokenizador) (Decisor, error) {
	return nil, ErrSinORT
}
