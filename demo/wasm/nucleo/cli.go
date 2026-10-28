package nucleo

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
)

// CLI es la interfaz de línea de órdenes común al binario nativo (nativo/) y al wasm bajo wasm_exec_node.js:
//
//	huella <modelo> <frases.json> <pregunta.json>   → {"huella":…, "respuestas":[…]}
//	latencia <modelo> <pregunta.json>               → un JSON por línea (16, 64 y 256 tokens × 200)
func CLI(args []string, w io.Writer) error {
	if len(args) < 2 {
		return fmt.Errorf("uso: huella <modelo> <frases.json> <pregunta.json> | latencia <modelo> <pregunta.json>")
	}
	datos, err := os.ReadFile(args[1])
	if err != nil {
		return err
	}
	d, err := Nueva(datos)
	if err != nil {
		return err
	}
	enc := json.NewEncoder(w)
	switch {
	case args[0] == "huella" && len(args) == 4:
		var frases []string
		b, err := os.ReadFile(args[2])
		if err != nil {
			return err
		}
		if err := json.Unmarshal(b, &frases); err != nil {
			return err
		}
		preg, err := os.ReadFile(args[3])
		if err != nil {
			return err
		}
		resp := make([]string, len(frases))
		for i, f := range frases {
			r, err := d.Decidir(f, string(preg))
			if err != nil {
				return err
			}
			resp[i] = r.Answer
		}
		return enc.Encode(map[string]any{"huella": d.Huella(frases), "respuestas": resp})
	case args[0] == "latencia" && len(args) == 3:
		preg, err := os.ReadFile(args[2])
		if err != nil {
			return err
		}
		for _, n := range []int{16, 64, 256} {
			l, err := d.Medir(n, 200, string(preg))
			if err != nil {
				return err
			}
			if err := enc.Encode(l); err != nil {
				return err
			}
		}
		return nil
	}
	return fmt.Errorf("argumentos no válidos: %v", args)
}
