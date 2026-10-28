// verificar_l1 da el top-1 de L1 (coseno del mensaje con «pregunta · opción · descripción») con runtime/l1, para
// compararlo con el de Python (`model/cascada/verificar_l1.py`). Mismo cálculo que `L1.Decidir` de server/decide/l1.go.
//
//	verificar_l1 modelo.chispa-l1 < casos.jsonl     (una línea {"mensaje": …, "opciones": ["pregunta · id · desc", …]})
//
// Escribe por línea {"top1": índice, "cos": [..]}.
package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"

	l1 "chispa/runtime/l1"
)

type caso struct {
	Mensaje  string   `json:"mensaje"`
	Opciones []string `json:"opciones"`
}

func main() {
	if len(os.Args) != 2 {
		fmt.Fprintln(os.Stderr, "uso: verificar_l1 modelo.chispa-l1 < casos.jsonl")
		os.Exit(2)
	}
	m, err := l1.Abrir(os.Args[1])
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	emb := func(s string) []float32 {
		e := make([]float32, m.Dim())
		m.Embed(s, e)
		return e
	}
	sc := bufio.NewScanner(os.Stdin)
	sc.Buffer(make([]byte, 1<<20), 1<<24)
	enc := json.NewEncoder(os.Stdout)
	for sc.Scan() {
		var c caso
		if err := json.Unmarshal(sc.Bytes(), &c); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		msg := emb(c.Mensaje)
		cos := make([]float64, len(c.Opciones))
		best := 0
		for i, o := range c.Opciones {
			v := emb(o)
			for j := range v {
				cos[i] += float64(msg[j]) * float64(v[j])
			}
			if cos[i] > cos[best] {
				best = i
			}
		}
		enc.Encode(map[string]any{"top1": best, "cos": cos})
	}
}
