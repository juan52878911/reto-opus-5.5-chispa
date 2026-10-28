// embeber lee de la entrada estándar un texto JSON por línea y escribe los embeddings de runtime/l1 como
// float32 little endian (n × dim) en la salida indicada.
//
//	embeber modelo.chispa-l1 salida.f32 < textos.jsonl
package main

import (
	"bufio"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"math"
	"os"

	l1 "chispa/runtime/l1"
)

func main() {
	if len(os.Args) != 3 {
		fmt.Fprintln(os.Stderr, "uso: embeber modelo.chispa-l1 salida.f32 < textos.jsonl")
		os.Exit(2)
	}
	m, err := l1.Abrir(os.Args[1])
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	defer m.Cerrar()
	f, err := os.Create(os.Args[2])
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	w := bufio.NewWriter(f)
	sc := bufio.NewScanner(os.Stdin)
	sc.Buffer(nil, 1<<26)
	out := make([]float32, m.Dim())
	buf := make([]byte, 4)
	for sc.Scan() {
		var t string
		if err := json.Unmarshal(sc.Bytes(), &t); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		m.Embed(t, out)
		for _, v := range out {
			binary.LittleEndian.PutUint32(buf, math.Float32bits(v))
			w.Write(buf)
		}
	}
	if err := w.Flush(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	f.Close()
}
