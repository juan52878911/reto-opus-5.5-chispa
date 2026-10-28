//go:build js && wasm

package main

import "errors"

var errSinModelo = errors.New("primero hay que cargar el modelo")
