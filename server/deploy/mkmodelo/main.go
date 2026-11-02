// mkmodelo escribe un .chispa v3 pequeño para probar la imagen sin modelos en S3: la sección L0 de un .chispa
// de testdata, un L1 diminuto (32 dimensiones, una pieza por palabra; copia de l1Tiny en decide/l1_test.go) y CALIB.
// Uso: mkmodelo -l0 testdata/injection.chispa -out /tmp/tiny.chispa
//
// Con -unir a.chispa,b.chispa escribe en -out un v3 con la unión de las secciones de los ficheros (si una sección está
// en varios, gana el primero): chispa-server solo acepta un -modelo, y en S3 L0+L1 y L2 van en ficheros distintos.
package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/binary"
	"encoding/json"
	"flag"
	"log"
	"math"
	"os"
	"strings"

	"chispa/format/chispa3"
)

const (
	dimTiny = 32
	tablaB  = 8
	prefB   = 16
)

func fnvB(b []byte) uint64 {
	h := uint64(0xCBF29CE484222325)
	for _, c := range b {
		h = (h ^ uint64(c)) * 0x100000001B3
	}
	return h
}

// l1Tiny escribe un .chispa-l1 (formato de runtime/l1, versión 1) con un vocabulario diminuto:
// [PAD], [UNK] y una pieza «▁palabra» por palabra. Cada palabra tiene un vector int8 propio,
// derivado de su hash, así que dos palabras distintas son casi ortogonales.
func l1Tiny(palabras []string) []byte {
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
	charsmap := []byte{4, 0, 0, 0, 0, 0, 0, 0} // trie vacío, sin cadenas
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

var palabras = []string{"factura", "reembolso", "cobro", "dinero", "envio", "paquete", "retraso", "pedido", "pago", "hola", "gracias"}

func main() {
	l0p := flag.String("l0", "testdata/injection.chispa", ".chispa v2 del que sale la sección L0")
	out := flag.String("out", "tiny.chispa", "fichero de salida")
	unir := flag.String("unir", "", "lista separada por comas de .chispa v3 a fusionar (ignora -l0)")
	maxFichero := flag.Int64("max-fichero", 0, "tope en bytes de cada .chispa de -unir (0 = 1 GiB, el del servidor por defecto)")
	flag.Parse()
	if *maxFichero < 0 {
		log.Fatalf("-max-fichero debe ser >= 0: %d", *maxFichero)
	}
	if *unir != "" {
		if err := fusionar(strings.Split(*unir, ","), *out, chispa3.Limites{MaxFichero: *maxFichero}); err != nil {
			log.Fatal(err)
		}
		return
	}
	l0, err := os.ReadFile(*l0p)
	if err != nil {
		log.Fatal(err)
	}
	meta, err := chispa3.Meta{Version: 1}.Codificar()
	if err != nil {
		log.Fatal(err)
	}
	cb, err := chispa3.Calib{TauEscalate: 0.7, Tipos: map[string]chispa3.ParamsTipo{
		"choice": {T: 0.05, Theta: 0.5},
		"noul":   {T: 1, A: 12, B: -3, Theta: 0.5},
	}}.Codificar()
	if err != nil {
		log.Fatal(err)
	}
	var buf bytes.Buffer
	if err := chispa3.Escribir(&buf, []chispa3.Seccion{{Tipo: chispa3.META, Datos: meta}, {Tipo: chispa3.L0, Datos: l0},
		{Tipo: chispa3.L1, Datos: l1Tiny(palabras)}, {Tipo: chispa3.CALIB, Datos: cb}}); err != nil {
		log.Fatal(err)
	}
	if err := os.WriteFile(*out, buf.Bytes(), 0o644); err != nil {
		log.Fatal(err)
	}
}

func fusionar(rutas []string, out string, lim chispa3.Limites) error {
	var secs []chispa3.Seccion
	vistas := map[chispa3.Tipo]string{}
	for _, r := range rutas {
		f, err := chispa3.AbrirCon(r, lim)
		if err != nil {
			return err
		}
		defer f.Close()
		for _, t := range f.Tipos() {
			if o, ok := vistas[t]; ok {
				log.Printf("sección %v en %s y en %s: gana la primera", t, o, r)
				continue
			}
			b, err := f.Bytes(t)
			if err != nil {
				return err
			}
			vistas[t] = r
			secs = append(secs, chispa3.Seccion{Tipo: t, Datos: append([]byte(nil), b...)})
			log.Printf("sección %v (%d bytes) de %s", t, len(b), r)
		}
	}
	var buf bytes.Buffer
	if err := chispa3.Escribir(&buf, secs); err != nil {
		return err
	}
	// el resultado también debe caber en el tope: es lo que luego abre el servidor
	if _, err := chispa3.Desde(buf.Bytes(), lim); err != nil {
		return err
	}
	return os.WriteFile(out, buf.Bytes(), 0o644)
}
