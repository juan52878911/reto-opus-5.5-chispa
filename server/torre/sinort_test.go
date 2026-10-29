//go:build !ort

package torre

import (
	"errors"
	"testing"

	"chispa/format/chispa3"
)

// Solo sin la etiqueta ort: ahí Abrir devuelve ErrSinORT. Con ORT, unos bytes que no son ONNX dan un error de protobuf.
func TestAbrirSinORT(t *testing.T) {
	_, err := Abrir(chispa3.Torre{Dim: 2, MaxLen: 8, Prefijo: "passage: ", ONNX: []byte{1}}, &tokFalso{})
	if err == nil {
		t.Skip("compilado con ORT")
	}
	if !errors.Is(err, ErrSinORT) {
		t.Fatal(err)
	}
	if _, err := Abrir(chispa3.Torre{}, nil); err == nil {
		t.Fatal("sin tokenizador")
	}
}
