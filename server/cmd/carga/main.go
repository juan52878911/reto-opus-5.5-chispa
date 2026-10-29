// carga es un generador de carga sencillo para chispa-server: N trabajadores
// mandan POST /v1/decide en bucle durante -d y se imprimen decisiones/s y p50/p99.
package main

import (
	"bytes"
	"flag"
	"fmt"
	"io"
	"log"
	"net/http"
	"sort"
	"sync"
	"time"
)

func main() {
	url := flag.String("url", "http://127.0.0.1:8090/v1/decide", "endpoint")
	conc := flag.Int("c", 8, "conexiones concurrentes")
	dur := flag.Duration("d", 10*time.Second, "duración")
	lote := flag.Int("lote", 1, "preguntas por petición")
	textos := flag.String("textos", "", "fichero con un mensaje por línea; se rotan entre peticiones (por defecto, el fijo de siempre)")
	csv := flag.Bool("csv", false, "añade una línea CSV: decisiones_s,peticiones_s,p50_ms,p99_ms,peticiones,errores")
	capas := flag.Bool("capas", false, "cuenta la capa que decidió cada resultado y la imprime")
	flag.Parse()

	estados := []string{estadoFijo}
	if *textos != "" {
		var err error
		if estados, err = cargarTextos(*textos); err != nil {
			log.Fatal(err)
		}
	}
	cuerpos := construirCuerpos(estados, *lote)

	cli := &http.Client{Transport: &http.Transport{MaxIdleConnsPerHost: *conc}}
	fin := time.Now().Add(*dur)
	var mu sync.Mutex
	var lat []time.Duration
	var errs int
	porCapa := map[string]int{}
	var wg sync.WaitGroup
	t0 := time.Now()
	for w := 0; w < *conc; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			var mine []time.Duration
			e := 0
			cn := map[string]int{}
			for i := w; time.Now().Before(fin); i += *conc {
				cuerpo := cuerpos[i%len(cuerpos)]
				t := time.Now()
				resp, err := cli.Post(*url, "application/json", bytes.NewReader(cuerpo))
				if err != nil {
					e++
					continue
				}
				var leido []byte
				if *capas {
					leido, _ = io.ReadAll(resp.Body)
				} else {
					io.Copy(io.Discard, resp.Body)
				}
				resp.Body.Close()
				if resp.StatusCode != 200 {
					e++
					continue
				}
				if *capas {
					contarCapas(leido, cn)
				}
				mine = append(mine, time.Since(t))
			}
			mu.Lock()
			lat = append(lat, mine...)
			errs += e
			for k, v := range cn {
				porCapa[k] += v
			}
			mu.Unlock()
		}()
	}
	wg.Wait()
	el := time.Since(t0).Seconds()
	if len(lat) == 0 {
		log.Fatalf("ninguna petición correcta (%d errores)", errs)
	}
	sort.Slice(lat, func(i, j int) bool { return lat[i] < lat[j] })
	p := func(q float64) time.Duration { return lat[int(q*float64(len(lat)-1))] }
	fmt.Printf("peticiones=%d errores=%d lote=%d conc=%d\n", len(lat), errs, *lote, *conc)
	fmt.Printf("decisiones/s=%.0f peticiones/s=%.0f p50=%v p99=%v\n",
		float64(len(lat)**lote)/el, float64(len(lat))/el, p(.5), p(.99))
	if *capas {
		fmt.Println("capas=" + formatoCapas(porCapa))
	}
	if *csv {
		fmt.Println(lineaCSV(len(lat), errs, *lote, el, p(.5), p(.99)))
	}
}
