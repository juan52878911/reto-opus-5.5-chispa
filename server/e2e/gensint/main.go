// gensint escribe los modelos sintéticos de la prueba e2e: un .chispa-l1 diminuto (formato de runtime/l1, igual que l1Tiny
// de server/decide/l1_test.go) y un .chispa-l2 (L2 sintético + ESQUEMAS de las opciones de la ferretería).
// Uso: gensint -l1 salida.chispa-l1 -l2 salida.chispa -l2onnx l2_sintetico.onnx -esquema-json ferreteria.json
package main

import (
	"crypto/sha256"
	"encoding/binary"
	"encoding/json"
	"flag"
	"log"
	"math"
	"os"
	"sort"
	"strings"

	"chispa/format/chispa3"
)

const (
	dimTiny = 32
	tablaB  = 8
	prefB   = 16
	dimL2   = 256

	// CALIB de L2 que escribe gensint: τ (tau_escalate_l2 en el .chispa final) y temperatura de choice (tipos_l2.choice.T).
	TauL2Sint = 0.37
	TL2Sint   = 0.02
)

func fnvB(b []byte) uint64 {
	h := uint64(0xCBF29CE484222325)
	for _, c := range b {
		h = (h ^ uint64(c)) * 0x100000001B3
	}
	return h
}

func l1(palabras []string) []byte {
	piezas := [][]byte{[]byte("[PAD]"), []byte("[UNK]")}
	for _, w := range palabras {
		piezas = append(piezas, []byte("▁"+w))
	}
	n := len(piezas)
	var blob []byte
	offs := make([]byte, 4*(n+1))
	scores := make([]byte, 8*n)
	pesos := make([]byte, n*dimTiny)
	escalas := make([]byte, 4*n)
	maxCar := 0
	for i, p := range piezas {
		binary.LittleEndian.PutUint32(offs[4*i:], uint32(len(blob)))
		blob = append(blob, p...)
		binary.LittleEndian.PutUint64(scores[8*i:], math.Float64bits(-5))
		if c := len([]rune(string(p))); c > maxCar {
			maxCar = c
		}
		h := fnvB(p)
		for j := 0; j < dimTiny; j++ {
			h = (h ^ uint64(j+1)) * 0x100000001B3
			pesos[i*dimTiny+j] = byte(int8(int(h>>40)%255 - 127))
		}
		binary.LittleEndian.PutUint32(escalas[4*i:], math.Float32bits(0.01))
	}
	binary.LittleEndian.PutUint32(offs[4*n:], uint32(len(blob)))
	tabla := make([]byte, 4<<tablaB)
	for i, p := range piezas {
		s := fnvB(p) & (1<<tablaB - 1)
		for binary.LittleEndian.Uint32(tabla[4*s:]) != 0 {
			s = (s + 1) & (1<<tablaB - 1)
		}
		binary.LittleEndian.PutUint32(tabla[4*s:], uint32(i+1))
	}
	filtro := make([]byte, 1<<(prefB-3))
	for _, p := range piezas {
		h := uint64(0xCBF29CE484222325)
		for k, c := range p {
			h = (h ^ uint64(c)) * 0x100000001B3
			if k+1 == len(p) || p[k+1]&0xC0 != 0x80 {
				b := h >> (64 - prefB)
				filtro[b>>3] |= 1 << (b & 7)
			}
		}
	}
	params, _ := json.Marshal(map[string]any{
		"max_tokens": 512, "mediana_pieza": 6, "recorte_texto": 512 * 6, "max_pieza_car": maxCar, "unk_id": 1,
		"unk_penalizacion": 10.0, "min_score": -5.0, "metaspace": "▁", "prepend": "always",
		"anadidos": map[string]int{"[PAD]": 0, "[UNK]": 1}, "puntuacion": "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~",
		"normalize": true, "escala_bits": 32, "dim": dimTiny,
	})
	charsmap := []byte{4, 0, 0, 0, 0, 0, 0, 0}
	cuerpo := [][]byte{params, charsmap, blob, offs, scores, tabla, pesos, escalas, filtro}
	cab := make([]byte, 256)
	copy(cab, "CHL1")
	le := binary.LittleEndian
	for i, v := range []uint32{1, dimTiny, uint32(n), 0, uint32(maxCar), tablaB, prefB} {
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

type esquema struct {
	Pregunta string            `json:"pregunta"`
	Opciones map[string]string `json:"opciones"`
}

func main() {
	sl1 := flag.String("l1", "", "salida .chispa-l1")
	sl2 := flag.String("l2", "", "salida .chispa con L2 y ESQUEMAS")
	l2onnx := flag.String("l2onnx", "", "ONNX sintético de consulta de L2")
	esqJSON := flag.String("esquema-json", "", "esquema (pregunta, opciones) cuyas opciones llevan torre en ESQUEMAS")
	extra := flag.String("palabras", "", "palabras extra del vocabulario de L1, separadas por espacios")
	flag.Parse()
	var q esquema
	b, err := os.ReadFile(*esqJSON)
	if err != nil {
		log.Fatal(err)
	}
	if err := json.Unmarshal(b, &q); err != nil {
		log.Fatal(err)
	}
	set := map[string]bool{}
	for _, f := range strings.Fields(strings.ToLower(*extra)) {
		set[f] = true
	}
	for _, d := range q.Opciones {
		for _, f := range strings.Fields(strings.ToLower(d)) {
			set[strings.Trim(f, ",.¿?¡!")] = true
		}
	}
	var pal []string
	for w := range set {
		if w != "" {
			pal = append(pal, w)
		}
	}
	sort.Strings(pal)
	if err := os.WriteFile(*sl1, l1(pal), 0o644); err != nil {
		log.Fatal(err)
	}
	var ids []string
	for id := range q.Opciones {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	var es []chispa3.EntradaEsquema
	for i, id := range ids {
		v := make([]int8, dimL2)
		v[i%dimL2] = 100
		es = append(es, chispa3.EntradaEsquema{Hash: chispa3.HashEsquema(q.Pregunta, []string{id}), Escala: 0.01, Vec: v})
	}
	esq, err := chispa3.CodificarEsquemas(dimL2, es)
	if err != nil {
		log.Fatal(err)
	}
	onnx, err := os.ReadFile(*l2onnx)
	if err != nil {
		log.Fatal(err)
	}
	f, err := os.Create(*sl2)
	if err != nil {
		log.Fatal(err)
	}
	defer f.Close()
	// CALIB propia de L2 (el e2e comprueba que `chispa train --l2` la pasa a tipos_l2 y tau_escalate_l2, y que L2 lee esos): T y τ
	// distintos de los de L1 a propósito, para que usar la CALIB equivocada cambie las probabilidades.
	calib, err := json.Marshal(chispa3.Calib{TauEscalate: TauL2Sint, Tipos: map[string]chispa3.ParamsTipo{"choice": {T: TL2Sint, Theta: 0.5}}})
	if err != nil {
		log.Fatal(err)
	}
	if err := chispa3.Escribir(f, []chispa3.Seccion{{Tipo: chispa3.L2, Datos: onnx}, {Tipo: chispa3.ESQUEMAS, Datos: esq}, {Tipo: chispa3.CALIB, Datos: calib}}); err != nil {
		log.Fatal(err)
	}
}
