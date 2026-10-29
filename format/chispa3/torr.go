package chispa3

import (
	"encoding/binary"
	"fmt"
	"unicode/utf8"
)

// ---- TORR ----

// TORR lleva el ONNX de la torre de esquemas (e5 de pasaje + cabeza de torre, model/l2/contrato-torre.md) para
// calcular torres de L2 al vuelo en esquemas que ESQUEMAS no trae. Disposición (little endian):
//
//	u32 versión(1) · u32 dim · u32 max_len · u32 len_prefijo · prefijo UTF-8 · ONNX (hasta el final)
//
// El ONNX recibe input_ids y attention_mask int64 (B,T) y devuelve h float32 (B,dim) normalizada.
const (
	torrVersion = 1
	torrCab     = 16
	maxTorrDim  = 4096
	maxTorrLen  = 8192
	maxTorrPref = 256
)

// Torre es la sección TORR decodificada. ONNX apunta a los bytes de entrada (sin copiar).
type Torre struct {
	Dim, MaxLen int
	Prefijo     string // «passage: »
	ONNX        []byte
}

// CodificarTORR serializa una torre; el prefijo debe ser UTF-8 válido.
func CodificarTORR(t Torre) ([]byte, error) {
	if t.Dim <= 0 || t.Dim > maxTorrDim || t.MaxLen <= 0 || t.MaxLen > maxTorrLen ||
		len(t.Prefijo) > maxTorrPref || !utf8.ValidString(t.Prefijo) || len(t.ONNX) == 0 {
		return nil, fmt.Errorf("%w: TORR dim=%d max_len=%d prefijo=%d onnx=%d", ErrContenido, t.Dim, t.MaxLen, len(t.Prefijo), len(t.ONNX))
	}
	b := make([]byte, torrCab, torrCab+len(t.Prefijo)+len(t.ONNX))
	le := binary.LittleEndian
	le.PutUint32(b[0:], torrVersion)
	le.PutUint32(b[4:], uint32(t.Dim))
	le.PutUint32(b[8:], uint32(t.MaxLen))
	le.PutUint32(b[12:], uint32(len(t.Prefijo)))
	b = append(b, t.Prefijo...)
	return append(b, t.ONNX...), nil
}

// DecodificarTORR valida la cabecera y los rangos; no abre el ONNX.
func DecodificarTORR(b []byte) (Torre, error) {
	le := binary.LittleEndian
	if len(b) < torrCab {
		return Torre{}, fmt.Errorf("%w: TORR truncada", ErrContenido)
	}
	if v := le.Uint32(b[0:]); v != torrVersion {
		return Torre{}, fmt.Errorf("%w: TORR versión %d", ErrContenido, v)
	}
	dim, ml, np := le.Uint32(b[4:]), le.Uint32(b[8:]), le.Uint32(b[12:])
	if dim == 0 || dim > maxTorrDim || ml == 0 || ml > maxTorrLen || np > maxTorrPref {
		return Torre{}, fmt.Errorf("%w: TORR dim=%d max_len=%d prefijo=%d", ErrContenido, dim, ml, np)
	}
	if uint64(len(b)) <= uint64(torrCab)+uint64(np) {
		return Torre{}, fmt.Errorf("%w: TORR sin ONNX", ErrContenido)
	}
	pref := b[torrCab : torrCab+int(np)]
	if !utf8.Valid(pref) {
		return Torre{}, fmt.Errorf("%w: TORR prefijo no UTF-8", ErrContenido)
	}
	return Torre{int(dim), int(ml), string(pref), b[torrCab+int(np):]}, nil
}

// Torre devuelve la sección TORR; ErrNoHay si el fichero no la trae.
func (f *Fichero) Torre() (Torre, error) {
	b, err := f.Bytes(TORR)
	if err != nil {
		return Torre{}, err
	}
	return DecodificarTORR(b)
}
