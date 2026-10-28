// l1medir mide arranque en frío, RSS y latencia de Embed sobre un .chispa-l1.
//
//	l1medir [-n 2000] modelo.chispa-l1
package main

import (
	"bufio"
	"flag"
	"fmt"
	"os"
	"runtime"
	"sort"
	"strings"
	"time"

	l1 "chispa/runtime/l1"
)

func rss() string {
	f, err := os.Open("/proc/self/status")
	if err != nil {
		return "n/d"
	}
	defer f.Close()
	var out []string
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		if l := sc.Text(); strings.HasPrefix(l, "VmRSS") || strings.HasPrefix(l, "RssAnon") || strings.HasPrefix(l, "RssFile") {
			out = append(out, strings.Join(strings.Fields(l), " "))
		}
	}
	return strings.Join(out, ", ")
}

func main() {
	n := flag.Int("n", 2000, "repeticiones por tamaño")
	flag.Parse()
	if flag.NArg() != 1 {
		fmt.Fprintln(os.Stderr, "uso: l1medir [-n N] modelo.chispa-l1")
		os.Exit(2)
	}
	t0 := time.Now()
	m, err := l1.Abrir(flag.Arg(0))
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	tAbrir := time.Since(t0)
	out := make([]float32, m.Dim())
	m.Embed("hola, ¿qué tal?", out)
	tPrimero := time.Since(t0)
	fmt.Printf("%s/%s %s  abrir=%v  abrir+primer_embed=%v\n", runtime.GOOS, runtime.GOARCH, runtime.Version(), tAbrir, tPrimero)
	fmt.Println("RSS tras primer embed:", rss())

	palabras := strings.Fields("quiero comprar zapatillas deportivas para mi hijo pero no sé la talla ¿pueden ayudarme con el envío a Medellín? " +
		"mi pedido llegó tarde y el producto venía dañado, necesito un reembolso por favor gracias buenos días tengo un problema con la cuenta")
	for _, objetivo := range []int{16, 64, 256} {
		var sb strings.Builder
		var texto string
		for i := 0; ; i++ {
			sb.WriteString(palabras[i%len(palabras)] + " ")
			if len(m.Tokenizar(sb.String())) >= objetivo || i > 4000 {
				texto = sb.String()
				break
			}
		}
		real := len(m.Tokenizar(texto))
		for i := 0; i < 200; i++ {
			m.Embed(texto, out)
		}
		d := make([]time.Duration, *n)
		for i := range d {
			t := time.Now()
			m.Embed(texto, out)
			d[i] = time.Since(t)
		}
		sort.Slice(d, func(a, b int) bool { return d[a] < d[b] })
		fmt.Printf("tokens=%3d (pedido %3d)  p50=%v  p99=%v  max=%v\n", real, objetivo, d[len(d)/2], d[len(d)*99/100], d[len(d)-1])
	}
	fmt.Println("RSS tras la carga:", rss())
}
