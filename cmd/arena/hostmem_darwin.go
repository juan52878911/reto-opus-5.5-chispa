package main

import (
	"syscall"
	"unsafe"
)

func hostMem() int64 {
	v, err := syscall.Sysctl("hw.memsize")
	if err != nil || len(v) < 7 {
		return 0
	}
	// syscall.Sysctl devuelve el uint64 como cadena sin el último byte nulo.
	b := append([]byte(v), 0)
	return int64(*(*uint64)(unsafe.Pointer(&b[0])))
}
