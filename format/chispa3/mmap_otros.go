//go:build !unix

package chispa3

import (
	"io"
	"os"
)

func mapear(f *os.File, n int64) ([]byte, func() error, error) {
	b := make([]byte, n)
	if _, err := io.ReadFull(f, b); err != nil {
		return nil, nil, err
	}
	return b, func() error { return nil }, nil
}
