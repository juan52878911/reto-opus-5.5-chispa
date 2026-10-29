package chispa3

import (
	"encoding/binary"
	"fmt"
	"strconv"
)

// Truncado del tokenizador de e5 (mensaje y torre): sale de los metadatos del modelo, no de una constante.
//
//   - pasaje (torre de las opciones): `max_len` de la sección TORR;
//   - consulta (mensaje): la clave `chispa.consulta.max_len` de `metadata_props` del ONNX de la sección L2 (misma convención
//     que `chispa.torre.*`);
//   - si no viene, MaxLenDefecto (128, el de G.7). Tope duro MaxLenTope; por encima, error.
const (
	MaxLenDefecto = 128
	MaxLenMin     = 3 // <s>, al menos un token y </s>
	MaxLenTope    = 512 // e5-small tiene 512 posiciones; coincide con runtime/tok.TopeMaxLen

	// ClaveMaxLenConsulta es la clave de metadata_props del ONNX de L2 con el truncado de la consulta.
	ClaveMaxLenConsulta = "chispa.consulta.max_len"
)

// ComprobarMaxLen devuelve un error claro si n no cabe en 3..MaxLenTope (<s>, al menos un token y </s>). `donde` dice de qué
// valor se trata («metadato chispa.consulta.max_len», «TORR max_len»…).
func ComprobarMaxLen(n int, donde string) error {
	if n < MaxLenMin || n > MaxLenTope {
		return fmt.Errorf("%s: max_len %d fuera de rango (3..%d)", donde, n, MaxLenTope)
	}
	return nil
}

// MetadatosONNX lee metadata_props (ModelProto, campo 14: repeticiones de StringStringEntryProto key=1 value=2) de un ONNX
// sin abrirlo con ORT: recorre solo los campos de primer nivel y se salta el grafo. En Go puro, así que sirve igual con el
// stub de ORT, en el servidor y en el móvil. Si una clave se repite, gana la última (como el diccionario de onnx).
func MetadatosONNX(b []byte) (map[string]string, error) {
	meta := map[string]string{}
	for len(b) > 0 {
		tag, n := binary.Uvarint(b)
		if n <= 0 {
			return nil, fmt.Errorf("onnx: etiqueta protobuf inválida")
		}
		b = b[n:]
		campo, tipo := tag>>3, tag&7
		var cuerpo []byte
		switch tipo {
		case 0:
			_, n = binary.Uvarint(b)
			if n <= 0 {
				return nil, fmt.Errorf("onnx: varint inválido")
			}
			b = b[n:]
			continue
		case 1:
			n = 8
		case 5:
			n = 4
		case 2:
			l, k := binary.Uvarint(b)
			if k <= 0 || l > uint64(len(b)-k) {
				return nil, fmt.Errorf("onnx: campo %d truncado", campo)
			}
			cuerpo, n = b[k:k+int(l)], k+int(l)
		default:
			return nil, fmt.Errorf("onnx: tipo de cable %d", tipo)
		}
		if n > len(b) {
			return nil, fmt.Errorf("onnx: campo %d truncado", campo)
		}
		b = b[n:]
		if campo == 14 && tipo == 2 {
			k, v, err := entradaMeta(cuerpo)
			if err != nil {
				return nil, err
			}
			meta[k] = v
		}
	}
	return meta, nil
}

func entradaMeta(b []byte) (clave, valor string, err error) {
	for len(b) > 0 {
		tag, n := binary.Uvarint(b)
		if n <= 0 {
			return "", "", fmt.Errorf("onnx: metadata_props inválido")
		}
		b = b[n:]
		if tag&7 != 2 {
			return "", "", fmt.Errorf("onnx: metadata_props con tipo de cable %d", tag&7)
		}
		l, k := binary.Uvarint(b)
		if k <= 0 || l > uint64(len(b)-k) {
			return "", "", fmt.Errorf("onnx: metadata_props truncado")
		}
		s := string(b[k : k+int(l)])
		b = b[k+int(l):]
		switch tag >> 3 {
		case 1:
			clave = s
		case 2:
			valor = s
		}
	}
	return clave, valor, nil
}

// MaxLenConsulta es el truncado de la consulta que declara el ONNX de L2: `chispa.consulta.max_len` o MaxLenDefecto si no viene.
// Si los metadatos no se pueden leer devuelve MaxLenDefecto y un aviso en MaxLenConsultaConAviso; aquí se descarta (ORT dará su propio
// error al abrir un ONNX roto). Quien pueda mostrar avisos (ArmarDesde, chispamovil) debe usar MaxLenConsultaConAviso.
// Un valor que no es un entero, o fuera de 3..MaxLenTope, es un error claro.
func MaxLenConsulta(onnx []byte) (int, error) {
	n, _, err := MaxLenConsultaConAviso(onnx)
	return n, err
}

// MaxLenConsultaConAviso es MaxLenConsulta pero no esconde que no pudo leer los metadatos: si fallan, devuelve MaxLenDefecto, un aviso
// claro («no se sabe si declara chispa.consulta.max_len») y error nil; el aviso es "" en los demás casos.
func MaxLenConsultaConAviso(onnx []byte) (int, string, error) {
	meta, err := MetadatosONNX(onnx)
	if err != nil {
		return MaxLenDefecto, fmt.Sprintf("metadatos del ONNX de L2 ilegibles (%v): no se sabe si declara %s; se usa %d", err, ClaveMaxLenConsulta, MaxLenDefecto), nil
	}
	v, ok := meta[ClaveMaxLenConsulta]
	if !ok {
		return MaxLenDefecto, "", nil
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return 0, "", fmt.Errorf("metadato %s=%q: no es un entero", ClaveMaxLenConsulta, v)
	}
	if err := ComprobarMaxLen(n, "metadato "+ClaveMaxLenConsulta); err != nil {
		return 0, "", err
	}
	return n, "", nil
}
