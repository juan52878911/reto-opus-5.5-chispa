package chispa3

import (
	"crypto/sha256"
	"encoding/binary"
	"fmt"
	"hash/crc32"
)

// legadoVersion es la única versión de .chispa previa a v3 que escribe y lee kindling v0.17.0
// (chispa.FormatVersion = 2); una v1 no existe en esa biblioteca y se rechaza como versión.
const legadoVersion = 2

// desdeLegado envuelve un .chispa v2 como un Fichero con solo la sección L0. Comprueba la magia
// (ya vista), la versión y el CRC-32C final; el contenido lo valida L0Modelo con kindling.
func desdeLegado(data []byte, lim Limites) (*Fichero, error) {
	if len(data) < len(magia)+8+4 {
		return nil, fmt.Errorf("%w: .chispa v2 de %d bytes", ErrTruncado, len(data))
	}
	if int64(len(data)) > lim.maxDe(L0) {
		return nil, fmt.Errorf("%w: L0 de %d bytes", ErrTamano, len(data))
	}
	cuerpo, suma := data[:len(data)-4], binary.LittleEndian.Uint32(data[len(data)-4:])
	if crc32.Checksum(cuerpo, crcTabla) != suma {
		return nil, fmt.Errorf("%w: .chispa v2", ErrCRC)
	}
	x := &entrada{tipo: L0, len: uint64(len(data)), datos: data, sha: sha256.Sum256(data)}
	return &Fichero{data: data, sec: map[Tipo]*entrada{L0: x}, orden: []Tipo{L0}, compat: true}, nil
}
