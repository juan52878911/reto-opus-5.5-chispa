package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"strings"
	"time"
)

const estadoFijo = "¿cómo hago el reclamo de la garantía? quiero saber el proceso"

// cargarTextos lee un mensaje por línea; ignora líneas vacías y las que empiezan por #.
func cargarTextos(path string) ([]string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	var out []string
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 1<<20), 1<<20)
	for sc.Scan() {
		l := strings.TrimSpace(sc.Text())
		if l != "" && !strings.HasPrefix(l, "#") {
			out = append(out, l)
		}
	}
	if err := sc.Err(); err != nil {
		return nil, err
	}
	if len(out) == 0 {
		return nil, fmt.Errorf("%s: sin mensajes", path)
	}
	return out, nil
}

// construirCuerpos arma un cuerpo de petición por estado, con lote preguntas cada uno.
func construirCuerpos(estados []string, lote int) [][]byte {
	qs := make([]byte, 0, 256*lote)
	for i := 0; i < lote; i++ {
		if i > 0 {
			qs = append(qs, ',')
		}
		qs = append(qs, fmt.Sprintf(`{"id":"q%d","question":"¿Qué quiere hacer el cliente?","kind":"choice","options":[{"id":"compra"},{"id":"queja"},{"id":"saludo"},{"id":"soporte"}]}`, i)...)
	}
	out := make([][]byte, len(estados))
	for i, e := range estados {
		st, _ := json.Marshal(e)
		out[i] = []byte(`{"state":` + string(st) + `,"questions":[` + string(qs) + `]}`)
	}
	return out
}

// contarCapas suma en cn la capa de cada resultado (y, por pregunta, la clave q:<id>/<capa>) de una respuesta de /v1/decide.
func contarCapas(b []byte, cn map[string]int) {
	var r struct {
		Results []struct {
			ID    string `json:"id"`
			Layer string `json:"layer"`
		} `json:"results"`
	}
	if json.Unmarshal(b, &r) != nil {
		return
	}
	for _, x := range r.Results {
		cn[x.Layer]++
		if x.ID != "" {
			cn["q:"+x.ID+"/"+x.Layer]++
		}
	}
}

func formatoCapas(cn map[string]int) string {
	ks := make([]string, 0, len(cn))
	for k := range cn {
		if !strings.HasPrefix(k, "q:") {
			ks = append(ks, k)
		}
	}
	sort.Strings(ks)
	parts := make([]string, len(ks))
	for i, k := range ks {
		parts[i] = fmt.Sprintf("%s:%d", k, cn[k])
	}
	return strings.Join(parts, ",")
}

func lineaCSV(peticiones, errs, lote int, seg float64, p50, p99 time.Duration) string {
	return fmt.Sprintf("%.0f,%.0f,%.3f,%.3f,%d,%d", float64(peticiones*lote)/seg, float64(peticiones)/seg,
		float64(p50.Microseconds())/1000, float64(p99.Microseconds())/1000, peticiones, errs)
}
