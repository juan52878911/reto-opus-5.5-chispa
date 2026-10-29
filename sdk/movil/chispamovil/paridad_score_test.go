package chispamovil

import (
	"context"
	"crypto/sha256"
	"encoding/binary"
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"testing"

	"chispa/format/chispa3"
	"chispa/runtime/l1"
	"github.com/juan52878911/chispa/server/decide"
)

const (
	dimDim   = 32
	tablaDim = 8
	prefDim  = 16
)

func fnvTiny(b []byte) uint64 {
	h := uint64(0xCBF29CE484222325)
	for _, c := range b {
		h = (h ^ uint64(c)) * 0x100000001B3
	}
	return h
}

// l1Diminuto escribe un .chispa-l1 (formato de runtime/l1, versión 1) con un vocabulario diminuto:
// [PAD], [UNK] y una pieza «▁palabra» por palabra. Cada palabra tiene un vector int8 propio,
// derivado de su hash, así que dos palabras distintas son casi ortogonales.
func l1Diminuto(palabras []string) []byte {
	piezas := [][]byte{[]byte("[PAD]"), []byte("[UNK]")}
	for _, w := range palabras {
		piezas = append(piezas, []byte("▁"+w))
	}
	n := len(piezas)
	var blob []byte
	offs := make([]byte, 4*(n+1))
	scores := make([]byte, 8*n)
	pesos := make([]byte, n*dimDim)
	escalas := make([]byte, 4*n)
	maxCar := 0
	for i, p := range piezas {
		binary.LittleEndian.PutUint32(offs[4*i:], uint32(len(blob)))
		blob = append(blob, p...)
		binary.LittleEndian.PutUint64(scores[8*i:], math.Float64bits(-5))
		if c := len([]rune(string(p))); c > maxCar {
			maxCar = c
		}
		h := fnvTiny(p)
		for j := 0; j < dimDim; j++ {
			h = (h ^ uint64(j+1)) * 0x100000001B3
			pesos[i*dimDim+j] = byte(int8(int(h>>40)%255 - 127))
		}
		binary.LittleEndian.PutUint32(escalas[4*i:], math.Float32bits(0.01))
	}
	binary.LittleEndian.PutUint32(offs[4*n:], uint32(len(blob)))
	tabla := make([]byte, 4<<tablaDim)
	for i, p := range piezas {
		s := fnvTiny(p) & (1<<tablaDim - 1)
		for binary.LittleEndian.Uint32(tabla[4*s:]) != 0 {
			s = (s + 1) & (1<<tablaDim - 1)
		}
		binary.LittleEndian.PutUint32(tabla[4*s:], uint32(i+1))
	}
	filtro := make([]byte, 1<<(prefDim-3))
	for _, p := range piezas {
		h := uint64(0xCBF29CE484222325)
		for k, c := range p {
			h = (h ^ uint64(c)) * 0x100000001B3
			if k+1 == len(p) || p[k+1]&0xC0 != 0x80 {
				b := h >> (64 - prefDim)
				filtro[b>>3] |= 1 << (b & 7)
			}
		}
	}
	params, _ := json.Marshal(map[string]any{
		"max_tokens": 512, "mediana_pieza": 6, "recorte_texto": 512 * 6, "max_pieza_car": maxCar, "unk_id": 1,
		"unk_penalizacion": 10.0, "min_score": -5.0, "metaspace": "▁", "prepend": "always",
		"anadidos": map[string]int{"[PAD]": 0, "[UNK]": 1}, "puntuacion": "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~",
		"normalize": true, "escala_bits": 32, "dim": dimDim,
	})
	charsmap := []byte{4, 0, 0, 0, 0, 0, 0, 0} // trie vacío, sin cadenas
	cuerpo := [][]byte{params, charsmap, blob, offs, scores, tabla, pesos, escalas, filtro}
	cab := make([]byte, 256)
	copy(cab, "CHL1")
	le := binary.LittleEndian
	for i, v := range []uint32{1, dimDim, uint32(n), 0, uint32(maxCar), tablaDim, prefDim} {
		le.PutUint32(cab[8+4*i:], v)
	}
	var resto []byte
	pos := 256
	for i, b := range cuerpo {
		pad := (16 - pos%16) % 16
		resto = append(resto, make([]byte, pad)...)
		pos += pad
		le.PutUint64(cab[36+16*i:], uint64(pos))
		le.PutUint64(cab[44+16*i:], uint64(len(b)))
		resto = append(resto, b...)
		pos += len(b)
	}
	h := sha256.Sum256(resto)
	copy(cab[36+16*9:], h[:])
	return append(cab, resto...)
}

var palabrasTiny = []string{"factura", "reembolso", "cobro", "dinero", "envio", "paquete", "retraso", "pedido", "pago", "hola", "gracias"}

// Paridad servidor ↔ móvil en score: mismo L1 diminuto, mismas preguntas, mismas probs y respuesta.
func TestScoreParidadConServidor(t *testing.T) {
	l1b := l1Diminuto(palabrasTiny)
	c := ficheroV3(t, chispa3.Seccion{Tipo: chispa3.L1, Datos: l1b})
	ruta := filepath.Join(t.TempDir(), "m.chispa-l1")
	if err := os.WriteFile(ruta, l1b, 0o600); err != nil {
		t.Fatal(err)
	}
	m, err := l1.Abrir(ruta)
	if err != nil {
		t.Fatal(err)
	}
	defer m.Cerrar()
	srv := decide.NuevoL1Modelo(m, c.calib, 4)

	niveles := []decide.Opcion{{ID: "1", Description: "factura cobro pago dinero reembolso"},
		{ID: "2", Description: "envio paquete retraso"}, {ID: "3", Description: "pedido hola gracias"}}
	njs, _ := json.Marshal(niveles)
	for _, estado := range []string{"quiero un reembolso de la factura", "el paquete llega con retraso", "hola gracias", "pago pedido retraso", "zzz qqq"} {
		p := decide.Pregunta{ID: "q", Texto: "¿Qué tan urgente?", Kind: decide.KindScore, Estado: estado, Opciones: niveles}
		want, err := srv.Decidir(context.Background(), p)
		if err != nil {
			t.Fatal(err)
		}
		got := leer(t, c.Decidir(estado, `{"question":"¿Qué tan urgente?","kind":"score","options":`+string(njs)+`}`))
		if !got.Ok || got.Answer != want.Answer || math.Abs(got.Conf-want.Conf) > tolParidad || got.Opina != (want.Conf > 0) {
			t.Fatalf("%q: móvil %+v, servidor %+v", estado, got, want)
		}
		for id, pr := range want.Probs {
			if math.Abs(got.Probs[id]-pr) > tolParidad {
				t.Fatalf("%q nivel %s: móvil %v, servidor %v", estado, id, got.Probs[id], pr)
			}
		}
		if want.Conf == 0 && estado != "zzz qqq" {
			t.Fatalf("%q: el servidor no opina", estado)
		}
	}
}
