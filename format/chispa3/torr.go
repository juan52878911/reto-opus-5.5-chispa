package chispa3

import (
	"encoding/binary"
	"encoding/json"
	"fmt"
	"unicode/utf8"
)

// ---- TORR ----

// TORR lleva el ONNX de la torre de esquemas (e5 de pasaje + cabeza de torre, model/l2/contrato-torre.md) para
// calcular torres de L2 al vuelo en esquemas que ESQUEMAS no trae. Disposición (little endian):
//
//	u32 versión(1) · u32 dim · u32 max_len · u32 len_prefijo · prefijo UTF-8 · ONNX (hasta el final)
//
// Versión 2 añade la versión del texto de torre con que se entrenó la torre (la misma que META.texto_torre):
//
//	u32 versión(2) · u32 dim · u32 max_len · u32 len_prefijo · u32 texto · prefijo UTF-8 · ONNX (hasta el final)
//
// con texto 2 = «v2_sin_id». TORR v1 significa siempre texto v1 (un v1 no lleva el campo); una torre con texto v1 se escribe
// como TORR v1, para que los runtimes anteriores la sigan leyendo. Un runtime que solo conoce TORR v1 rechaza la v2.
//
// El ONNX recibe input_ids y attention_mask int64 (B,T) y devuelve h float32 (B,dim) normalizada.
const (
	torrVersion   = 1
	torrVersion2  = 2
	torrCab       = 16
	torrCab2      = 20
	torrTextoV2ID = 2 // código de texto «v2_sin_id» en TORR v2
	maxTorrDim    = 4096
	maxTorrLen    = MaxLenTope
	maxTorrPref   = 256
)

// Torre es la sección TORR decodificada. ONNX apunta a los bytes de entrada (sin copiar).
type Torre struct {
	Dim, MaxLen int
	Prefijo     string // «passage: »
	// TextoTorre es la versión del texto de torre: TextoTorreV1 o TextoTorreV2SinID. Al escribir, vacío = v1; al leer, nunca vacío.
	TextoTorre string
	ONNX       []byte
}

// CodificarTORR serializa una torre; el prefijo debe ser UTF-8 válido.
func CodificarTORR(t Torre) ([]byte, error) {
	if t.Dim <= 0 || t.Dim > maxTorrDim || t.MaxLen < MaxLenMin || t.MaxLen > maxTorrLen ||
		len(t.Prefijo) > maxTorrPref || !utf8.ValidString(t.Prefijo) || len(t.ONNX) == 0 {
		return nil, fmt.Errorf("%w: TORR dim=%d max_len=%d (tope %d) prefijo=%d onnx=%d", ErrContenido, t.Dim, t.MaxLen, MaxLenTope, len(t.Prefijo), len(t.ONNX))
	}
	cab, ver := torrCab, uint32(torrVersion)
	switch t.TextoTorre {
	case "", TextoTorreV1:
	case TextoTorreV2SinID:
		cab, ver = torrCab2, torrVersion2
	default:
		return nil, fmt.Errorf("%w: TORR texto_torre %q desconocido (se esperaba %q o %q)", ErrContenido, t.TextoTorre, TextoTorreV1, TextoTorreV2SinID)
	}
	b := make([]byte, cab, cab+len(t.Prefijo)+len(t.ONNX))
	le := binary.LittleEndian
	le.PutUint32(b[0:], ver)
	le.PutUint32(b[4:], uint32(t.Dim))
	le.PutUint32(b[8:], uint32(t.MaxLen))
	le.PutUint32(b[12:], uint32(len(t.Prefijo)))
	if ver == torrVersion2 {
		le.PutUint32(b[16:], torrTextoV2ID)
	}
	b = append(b, t.Prefijo...)
	return append(b, t.ONNX...), nil
}

// DecodificarTORR valida la cabecera y los rangos; no abre el ONNX.
func DecodificarTORR(b []byte) (Torre, error) {
	le := binary.LittleEndian
	if len(b) < torrCab {
		return Torre{}, fmt.Errorf("%w: TORR truncada", ErrContenido)
	}
	v := le.Uint32(b[0:])
	if v != torrVersion && v != torrVersion2 {
		return Torre{}, fmt.Errorf("%w: TORR versión %d desconocida (este runtime lee 1 y 2)", ErrContenido, v)
	}
	cab, texto := torrCab, TextoTorreV1
	if v == torrVersion2 {
		cab = torrCab2
		if len(b) < cab {
			return Torre{}, fmt.Errorf("%w: TORR truncada", ErrContenido)
		}
		if c := le.Uint32(b[16:]); c != torrTextoV2ID {
			return Torre{}, fmt.Errorf("%w: TORR texto de torre %d desconocido", ErrContenido, c)
		}
		texto = TextoTorreV2SinID
	}
	dim, ml, np := le.Uint32(b[4:]), le.Uint32(b[8:]), le.Uint32(b[12:])
	if dim == 0 || dim > maxTorrDim || ml < MaxLenMin || ml > maxTorrLen || np > maxTorrPref {
		return Torre{}, fmt.Errorf("%w: TORR dim=%d max_len=%d (tope %d) prefijo=%d", ErrContenido, dim, ml, MaxLenTope, np)
	}
	if uint64(len(b)) <= uint64(cab)+uint64(np) {
		return Torre{}, fmt.Errorf("%w: TORR sin ONNX", ErrContenido)
	}
	pref := b[cab : cab+int(np)]
	if !utf8.Valid(pref) {
		return Torre{}, fmt.Errorf("%w: TORR prefijo no UTF-8", ErrContenido)
	}
	return Torre{Dim: int(dim), MaxLen: int(ml), Prefijo: string(pref), TextoTorre: texto, ONNX: b[cab+int(np):]}, nil
}

// Torre devuelve la sección TORR; ErrNoHay si el fichero no la trae.
func (f *Fichero) Torre() (Torre, error) {
	b, err := f.Bytes(TORR)
	if err != nil {
		return Torre{}, err
	}
	return DecodificarTORR(b)
}

// TextoTorreEfectivo es la versión del texto de torre con que se montan las torres al vuelo del fichero: sale de TORR (v1 si es
// TORR v1, la de su cabecera si es v2). Si META trae texto_torre y no coincide con TORR, es un error de carga (el fichero se
// entrenó con un texto y META dice otro: calcular cualquiera de los dos sería servir torres distintas a las entrenadas).
// META sin texto_torre no se contrasta (ausente = v1 solo cuando no hay TORR que lo diga). Exige TORR.
func (f *Fichero) TextoTorreEfectivo() (string, error) {
	t, err := f.Torre()
	if err != nil {
		return "", fmt.Errorf("sección TORR: %w", err)
	}
	if !f.Tiene(META) {
		return t.TextoTorre, nil
	}
	b, err := f.Bytes(META)
	if err != nil {
		return "", err
	}
	var m struct {
		TextoTorre string `json:"texto_torre"`
	}
	if err := json.Unmarshal(b, &m); err != nil {
		return "", fmt.Errorf("%w: META: %v", ErrContenido, err)
	}
	if m.TextoTorre == "" {
		return t.TextoTorre, nil
	}
	if m.TextoTorre != TextoTorreV1 && m.TextoTorre != TextoTorreV2SinID {
		return "", fmt.Errorf("%w: META.texto_torre %q desconocido (se esperaba %q o %q)", ErrContenido, m.TextoTorre, TextoTorreV1, TextoTorreV2SinID)
	}
	if m.TextoTorre != t.TextoTorre {
		return "", fmt.Errorf("%w: META.texto_torre %q y TORR (texto %q) no coinciden: el fichero está mal escrito", ErrContenido, m.TextoTorre, t.TextoTorre)
	}
	return t.TextoTorre, nil
}
