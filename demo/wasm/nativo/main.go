// Command nativo es la referencia nativa de la prueba de node: ver nucleo.CLI.
package main

import (
	"fmt"
	"os"

	"chispa/demo/wasm/nucleo"
)

func main() {
	if err := nucleo.CLI(os.Args[1:], os.Stdout); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
