// cargamsg es server/cmd/carga (mismas banderas y misma salida) pero con el mensaje de cada petición tomado, por turno,
// de un fichero de mensajes reales (uno por línea). Existe porque carga manda siempre el mismo texto y no se puede cambiar.
package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"sort"
	"sync"
	"sync/atomic"
	"time"
)

func main() {
	url := flag.String("url", "http://127.0.0.1:8090/v1/decide", "endpoint")
	conc := flag.Int("c", 8, "conexiones concurrentes")
	dur := flag.Duration("d", 10*time.Second, "duración")
	lote := flag.Int("lote", 1, "preguntas por petición")
	msgs := flag.String("mensajes", "", "fichero de mensajes, uno por línea")
	flag.Parse()

	f, err := os.Open(*msgs)
	if err != nil {
		log.Fatal(err)
	}
	var cuerpos [][]byte
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		if sc.Text() == "" {
			continue
		}
		var qs []byte
		for i := 0; i < *lote; i++ {
			if i > 0 {
				qs = append(qs, ',')
			}
			qs = append(qs, fmt.Sprintf(`{"id":"q%d","question":"¿Qué quiere hacer el cliente?","kind":"choice","options":[{"id":"compra"},{"id":"queja"},{"id":"saludo"},{"id":"soporte"}]}`, i)...)
		}
		est, _ := json.Marshal(sc.Text())
		cuerpos = append(cuerpos, []byte(`{"state":`+string(est)+`,"questions":[`+string(qs)+`]}`))
	}
	if len(cuerpos) == 0 {
		log.Fatal("sin mensajes")
	}

	cli := &http.Client{Transport: &http.Transport{MaxIdleConnsPerHost: *conc}}
	fin := time.Now().Add(*dur)
	var mu sync.Mutex
	var lat []time.Duration
	var errs int
	var sig atomic.Uint64
	var wg sync.WaitGroup
	t0 := time.Now()
	for w := 0; w < *conc; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			var mine []time.Duration
			e := 0
			for time.Now().Before(fin) {
				cuerpo := cuerpos[int(sig.Add(1))%len(cuerpos)]
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
