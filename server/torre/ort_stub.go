//go:build !ort

package torre

func abrirSesion([]byte) (Sesion, error) { return nil, ErrSinORT }
