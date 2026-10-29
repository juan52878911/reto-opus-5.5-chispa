//go:build ort

package main

import (
	"os"

	"github.com/juan52878911/chispa/server/decide"
	"github.com/juan52878911/chispa/server/torre"
)

// fijarRutaORT resuelve la ruta de libonnxruntime con la precedencia -ort-lib > CHISPA_ORT_LIB > -ldflags -X …decide.RutaORT >
// búsqueda por defecto del sistema (vacía), y la asigna a L2 (decide) y a la torre: las dos comparten un único entorno ORT.
func fijarRutaORT(flagORT string) (ruta, origen string) {
	switch env := os.Getenv("CHISPA_ORT_LIB"); {
	case flagORT != "":
		ruta, origen = flagORT, "-ort-lib"
	case env != "":
		ruta, origen = env, "CHISPA_ORT_LIB"
	case decide.RutaORT != "":
		ruta, origen = decide.RutaORT, "ldflags"
	default:
		origen = "búsqueda por defecto"
	}
	decide.RutaORT, torre.RutaORT = ruta, ruta
	return ruta, origen
}

// comprobarORT carga ONNX Runtime ya (una vez por proceso, como en L2 y la torre) para avisar al arrancar si no carga.
func comprobarORT() error { return torre.IniciarORT("") }
