// carga es un generador de carga sencillo para chispa-server: N trabajadores
// mandan POST /v1/decide en bucle durante -d y se imprimen decisiones/s (preguntas decididas por segundo), peticiones/s y p50/p99.
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
	timeout := flag.Duration("timeout", 0, "timeout de cada petición (0 = 2×duración)")
	esquemas := flag.String("esquemas", "", "esquemas-carga.json: manda sus preguntas (zero-shot) en vez de la fija; ver README")
	var lotesNombre string
	flag.StringVar(&lotesNombre, "lotes-nombre", "", "con -esquemas: lote con nombre (uno, tres, cinco, ocho…); sin él, -lote N toma N preguntas del fichero rotando")
	flag.StringVar(&lotesNombre, "lote-nombre", "", "alias de -lotes-nombre")
	capas := flag.Bool("capas", false, "cuenta la capa que decidió cada resultado y la imprime")
	flag.Parse()

	estados := []string{estadoFijo}
	if *textos != "" {
		var err error
		if estados, err = cargarTextos(*textos); err != nil {
			log.Fatal(err)
		}
	}
	var cuerpos [][]byte
	if *esquemas != "" {
		es, err := cargarEsquemas(*esquemas)
		if err != nil {
			log.Fatal(err)
		}
		if cuerpos, *lote, err = construirCuerposEsquemas(es, estados, lotesNombre, *lote); err != nil {
			log.Fatal(err)
		}
	} else {
		cuerpos = construirCuerpos(estados, *lote)
	}

	if *timeout <= 0 {
		*timeout = 2 * *dur
	}
	cli := &http.Client{Timeout: *timeout, Transport: &http.Transport{MaxIdleConnsPerHost: *conc}}
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
			mine, e, cn := trabajar(cli, *url, cuerpos, w, *conc, fin, *capas)
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
		if *esquemas != "" {
			fmt.Println("preguntas=" + formatoPreguntas(porCapa))
		}
	}
	if *csv {
		fmt.Println(lineaCSV(len(lat), errs, *lote, el, p(.5), p(.99)))
	}
}

// pausaError es la espera tras el n-ésimo error de red seguido: 10ms, doblando hasta 500ms.
func pausaError(n int) time.Duration {
	d := 10 * time.Millisecond
	for i := 1; i < n && d < 500*time.Millisecond; i++ {
		d *= 2
	}
	return min(d, 500*time.Millisecond)
}

// trabajar manda peticiones hasta fin; devuelve latencias, errores y capas contadas.
func trabajar(cli *http.Client, url string, cuerpos [][]byte, w, conc int, fin time.Time, capas bool) ([]time.Duration, int, map[string]int) {
	var mine []time.Duration
	e, seguidos := 0, 0
	cn := map[string]int{}
	for i := w; time.Now().Before(fin); i += conc {
		cuerpo := cuerpos[i%len(cuerpos)]
		t := time.Now()
		resp, err := cli.Post(url, "application/json", bytes.NewReader(cuerpo))
		if err != nil {
			e++
			seguidos++
			time.Sleep(min(pausaError(seguidos), time.Until(fin)))
			continue
		}
		seguidos = 0
		var leido []byte
		if capas {
			leido, _ = io.ReadAll(resp.Body)
		} else {
			io.Copy(io.Discard, resp.Body)
		}
		resp.Body.Close()
		if resp.StatusCode != 200 {
			e++
			continue
		}
		if capas {
			contarCapas(leido, cn)
		}
		mine = append(mine, time.Since(t))
	}
	return mine, e, cn
}
