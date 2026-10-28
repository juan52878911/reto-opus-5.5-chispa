package chispa3

import (
	"fmt"

	"github.com/juan52878911/kindling/pkg/chispa"
)

// L0 devuelve el .chispa v1/v2 tal cual (tras comprobar el sha256 de la sección).
func (f *Fichero) L0() ([]byte, error) { return f.Bytes(L0) }

// L0Modelo carga la sección L0 como modelo de kindling.
func (f *Fichero) L0Modelo() (*chispa.Model, error) {
	b, err := f.Bytes(L0)
	if err != nil {
		return nil, err
	}
	m, err := chispa.Unmarshal(b)
	if err != nil {
		return nil, fmt.Errorf("%w: L0: %v", ErrContenido, err)
	}
	return m, nil
}
