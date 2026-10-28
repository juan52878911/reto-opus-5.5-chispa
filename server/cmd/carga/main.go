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
	flag.Parse()

	qs := make([]byte, 0, 256**lote)
	for i := 0; i < *lote; i++ {
		if i > 0 {
			qs = append(qs, ',')
		}
		qs = append(qs, fmt.Sprintf(`{"id":"q%d","question":"¿Qué quiere hacer el cliente?","kind":"choice","options":[{"id":"compra"},{"id":"queja"},{"id":"saludo"},{"id":"soporte"}]}`, i)...)
	}
	cuerpo := []byte(`{"state":"¿cómo hago el reclamo de la garantía? quiero saber el proceso","questions":[` + string(qs) + `]}`)

	cli := &http.Client{Transport: &http.Transport{MaxIdleConnsPerHost: *conc}}
	fin := time.Now().Add(*dur)
	var mu sync.Mutex
	var lat []time.Duration
	var errs int
	var wg sync.WaitGroup
	t0 := time.Now()
	for w := 0; w < *conc; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			var mine []time.Duration
			e := 0
			for time.Now().Before(fin) {
				t := time.Now()
				resp, err := cli.Post(*url, "application/json", bytes.NewReader(cuerpo))
				if err != nil {
					e++
					continue
				}
				io.Copy(io.Discard, resp.Body)
				resp.Body.Close()
				if resp.StatusCode != 200 {
					e++
					continue
				}
				mine = append(mine, time.Since(t))
			}
			mu.Lock()
			lat = append(lat, mine...)
			errs += e
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
}
