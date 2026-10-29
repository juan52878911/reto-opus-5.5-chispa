//go:build js && wasm

// Command main compila a wasm y expone a JavaScript: cargar(bytes), decidir(texto, preguntaJSON),
// decidirLote(textosJSON, preguntaJSON), memoriaGo(), huella(frasesJSON) y medir(tokens, reps, preguntaJSON). Todas devuelven un objeto {ok, ...} o {ok:false, error}.
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"runtime"
	"syscall/js"

	"chispa/demo/wasm/nucleo"
)

var demo *nucleo.Demo

func resultado(v any, err error) any {
	if err != nil {
		return map[string]any{"ok": false, "error": err.Error()}
	}
	b, _ := json.Marshal(v)
	var o map[string]any
	json.Unmarshal(b, &o)
	o["ok"] = true
	return o
}

func main() {
	if len(os.Args) > 1 { // modo línea de órdenes: node wasm_exec_node.js chispa.wasm huella …
		if err := nucleo.CLI(os.Args[1:], os.Stdout); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		return
	}
	js.Global().Set("cargar", js.FuncOf(func(_ js.Value, a []js.Value) any {
		datos := make([]byte, a[0].Get("length").Int())
		js.CopyBytesToGo(datos, a[0])
		d, err := nucleo.Nueva(datos)
		if err != nil {
			return resultado(nil, err)
		}
		demo = d
		return resultado(map[string]any{"vocab": d.M.Vocab(), "dim": d.M.Dim(), "bytes": len(datos)}, nil)
	}))
	js.Global().Set("decidir", js.FuncOf(func(_ js.Value, a []js.Value) any {
		if demo == nil {
			return resultado(nil, errSinModelo)
		}
		r, err := demo.Decidir(a[0].String(), a[1].String())
		return resultado(r, err)
	}))
	js.Global().Set("huella", js.FuncOf(func(_ js.Value, a []js.Value) any {
		if demo == nil {
			return resultado(nil, errSinModelo)
		}
		var f []string
		if err := json.Unmarshal([]byte(a[0].String()), &f); err != nil {
			return resultado(nil, err)
		}
		return resultado(map[string]any{"huella": demo.Huella(f)}, nil)
	}))
	js.Global().Set("medir", js.FuncOf(func(_ js.Value, a []js.Value) any {
		if demo == nil {
			return resultado(nil, errSinModelo)
		}
		l, err := demo.Medir(a[0].Int(), a[1].Int(), a[2].String())
		return resultado(l, err)
	}))
	js.Global().Set("decidirLote", js.FuncOf(func(_ js.Value, a []js.Value) any {
		if demo == nil {
			return resultado(nil, errSinModelo)
		}
		var t []string
		if err := json.Unmarshal([]byte(a[0].String()), &t); err != nil {
			return resultado(nil, err)
		}
		l, err := demo.DecidirLote(t, a[1].String())
		return resultado(l, err)
	}))
	js.Global().Set("memoriaGo", js.FuncOf(func(_ js.Value, _ []js.Value) any {
		var m runtime.MemStats
		runtime.ReadMemStats(&m)
		return map[string]any{"heap_alloc": float64(m.HeapAlloc), "sys": float64(m.Sys), "num_gc": float64(m.NumGC)}
	}))
	js.Global().Set("chispaListo", true)
	select {} // el runtime de Go debe seguir vivo para atender las llamadas de JS
}
