package chispamovil

import (
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"math"
)

func huella(e embebedor, textos []string) string {
	h := sha256.New()
	v := make([]float32, e.Dim())
	b := make([]byte, 4*len(v))
	for _, t := range textos {
		e.Embed(t, v)
		for i, x := range v {
			binary.LittleEndian.PutUint32(b[4*i:], math.Float32bits(x))
		}
		h.Write(b)
	}
	return hex.EncodeToString(h.Sum(nil))
}
