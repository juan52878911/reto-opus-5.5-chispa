//go:build !unix

package l1

import "os"

// Abrir lee el fichero entero (sin mmap en esta plataforma).
func Abrir(ruta string) (*Modelo, error) {
	b, err := os.ReadFile(ruta)
	if err != nil {
		return nil, err
	}
	return Desde(b)
}
