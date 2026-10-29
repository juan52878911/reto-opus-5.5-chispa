//go:build !ort

package main

import "github.com/juan52878911/chispa/server/decide"

func fijarRutaORT(string) (ruta, origen string) { return "", "binario sin la etiqueta ort" }

func comprobarORT() error { return decide.ErrSinORT }
