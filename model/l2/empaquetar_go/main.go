// Command empaquetar escribe un `.chispa` v3 con META, L2, ESQUEMAS y CALIB (T2.6).
//
//	go run . --meta meta.json --l2 l2.onnx --esquemas esquemas.json --calib calib.json --salida l2.chispa
//
// esquemas.json: {"dim": N, "entradas": [{"pregunta": "...", "kind": "choice|noul|score",
// "opciones": [{"id": "...", "description": "..."}], "escala": f, "vec": "<base64 de N int8>"}]};
// escribe ESQUEMAS v2 y la clave de cada entrada la calcula `chispa3.HashEsquema2`, no el llamador.
package main

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"flag"
	"fmt"
	"os"

	"chispa/format/chispa3"
)

type opcionJSON struct {
	ID          string `json:"id"`
	Description string `json:"description"`
}

type entradaJSON struct {
	Pregunta string       `json:"pregunta"`
	Kind     string       `json:"kind"`
	Opciones []opcionJSON `json:"opciones"`
	Escala   float32      `json:"escala"`
	Vec      string       `json:"vec"`
}

// clave es la HashEsquema2 de la entrada.
func (e entradaJSON) clave() [16]byte {
	ops := make([]chispa3.OpcionClave, len(e.Opciones))
	for i, o := range e.Opciones {
		ops[i] = chispa3.OpcionClave{ID: o.ID, Descripcion: o.Description}
	}
	return chispa3.HashEsquema2(e.Pregunta, e.Kind, ops)
}

type esquemasJSON struct {
	Dim      int           `json:"dim"`
	Entradas []entradaJSON `json:"entradas"`
}

func codificarEsquemas(b []byte) ([]byte, error) {
	var j esquemasJSON
	d := json.NewDecoder(bytes.NewReader(b))
	d.DisallowUnknownFields()
	if err := d.Decode(&j); err != nil {
		return nil, fmt.Errorf("esquemas.json: %w", err)
	}
	es := make([]chispa3.EntradaEsquema2, len(j.Entradas))
	for i, e := range j.Entradas {
		raw, err := base64.StdEncoding.DecodeString(e.Vec)
		if err != nil {
			return nil, fmt.Errorf("esquemas.json entrada %d: %w", i, err)
		}
		v := make([]int8, len(raw))
		for k, x := range raw {
			v[k] = int8(x)
		}
		es[i] = chispa3.EntradaEsquema2{Hash: e.clave(), Escala: e.Escala, Vec: v}
	}
	return chispa3.CodificarEsquemas2(j.Dim, es)
}

// empaquetar valida cada sección con los decodificadores de chispa3 y escribe el fichero.
func empaquetar(metaB, l2, esqB, calibB []byte, salida string) error {
	m, err := chispa3.DecodificarMeta(metaB)
	if err != nil {
		return err
	}
	meta, err := m.Codificar()
	if err != nil {
		return err
	}
	c, err := chispa3.DecodificarCalib(calibB)
	if err != nil {
		return err
	}
	calib, err := c.Codificar()
	if err != nil {
		return err
	}
	esq, err := codificarEsquemas(esqB)
	if err != nil {
		return err
	}
	if len(l2) == 0 {
		return fmt.Errorf("L2 vacío")
	}
	var buf bytes.Buffer
	secs := []chispa3.Seccion{{Tipo: chispa3.META, Datos: meta}, {Tipo: chispa3.L2, Datos: l2},
		{Tipo: chispa3.ESQUEMAS, Datos: esq}, {Tipo: chispa3.CALIB, Datos: calib}}
	if err := chispa3.Escribir(&buf, secs); err != nil {
		return err
	}
	// ida y vuelta antes de escribir: lo que sale se abre y verifica
	f, err := chispa3.Desde(buf.Bytes(), chispa3.Limites{})
	if err != nil {
		return err
	}
	if err := f.Verificar(); err != nil {
		return err
	}
	if _, err := f.Esquemas(); err != nil {
		return err
	}
	tmp := salida + ".tmp"
	if err := os.WriteFile(tmp, buf.Bytes(), 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, salida)
}

func main() {
	meta := flag.String("meta", "", "META (json)")
	l2 := flag.String("l2", "", "ONNX int8")
	esq := flag.String("esquemas", "", "esquemas.json")
	calib := flag.String("calib", "", "CALIB (json)")
	salida := flag.String("salida", "", ".chispa de salida")
	flag.Parse()
	rd := func(p string) []byte {
		b, err := os.ReadFile(p)
		if err != nil {
			fmt.Fprintln(os.Stderr, "empaquetar:", err)
			os.Exit(1)
		}
		return b
	}
	if *meta == "" || *l2 == "" || *esq == "" || *calib == "" || *salida == "" {
		flag.Usage()
		os.Exit(2)
	}
	if err := empaquetar(rd(*meta), rd(*l2), rd(*esq), rd(*calib), *salida); err != nil {
		fmt.Fprintln(os.Stderr, "empaquetar:", err)
		os.Exit(1)
	}
}
