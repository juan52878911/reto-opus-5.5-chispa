// Command entrenador entrena y empaqueta un `.chispa` v3 con pocos ejemplos (T4.3), y lo evalúa.
//
//	go run . entrenar plan.json   # escribe plan.salida, informe JSON por stdout
//	go run . evaluar  plan.json   # plan.salida (+ plan.prueba) → informe JSON por stdout
//
// plan.json lo escribe `chispa train` (Python). Ver plan.go.
package main

import (
	"encoding/json"
	"fmt"
	"os"
)

func main() {
	if len(os.Args) == 2 && (os.Args[1] == "-h" || os.Args[1] == "--help" || os.Args[1] == "help") {
		fmt.Println("uso: entrenador entrenar|evaluar plan.json")
		return
	}
	if len(os.Args) != 3 {
		fmt.Fprintln(os.Stderr, "uso: entrenador entrenar|evaluar plan.json")
		os.Exit(2)
	}
	p, err := leerPlan(os.Args[2])
	if err == nil {
		var inf any
		switch os.Args[1] {
		case "entrenar":
			inf, err = entrenar(p)
		case "evaluar":
			inf, err = evaluar(p)
		default:
			err = fmt.Errorf("orden desconocida %q", os.Args[1])
		}
		if err == nil {
			err = json.NewEncoder(os.Stdout).Encode(inf)
		}
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "entrenador:", err)
		os.Exit(1)
	}
}
