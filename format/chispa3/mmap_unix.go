//go:build unix

package chispa3

import (
	"os"
	"syscall"
)

func mapear(f *os.File, n int64) ([]byte, func() error, error) {
	b, err := syscall.Mmap(int(f.Fd()), 0, int(n), syscall.PROT_READ, syscall.MAP_SHARED)
	if err != nil {
		return nil, nil, err
	}
	return b, func() error { return syscall.Munmap(b) }, nil
}
