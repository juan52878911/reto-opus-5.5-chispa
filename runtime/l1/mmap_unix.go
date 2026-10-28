//go:build unix

package l1

import (
	"fmt"
	"os"
	"syscall"
)

// Abrir mapea en memoria (solo lectura) el fichero .chispa-l1: el arranque no copia ni indexa nada.
func Abrir(ruta string) (*Modelo, error) {
	f, err := os.Open(ruta)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	st, err := f.Stat()
	if err != nil {
		return nil, err
	}
	if st.Size() < tamCabecera {
		return nil, fmt.Errorf("l1: %s demasiado corto", ruta)
	}
	b, err := syscall.Mmap(int(f.Fd()), 0, int(st.Size()), syscall.PROT_READ, syscall.MAP_SHARED)
	if err != nil {
		return nil, err
	}
	m, err := Desde(b)
	if err != nil {
		syscall.Munmap(b)
		return nil, err
	}
	m.cerrar = func() error { return syscall.Munmap(b) }
	return m, nil
}
