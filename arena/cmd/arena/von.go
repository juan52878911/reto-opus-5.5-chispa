package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"sync"
	"time"
)

// startVONPool restaura n réplicas VON del MISMO snapshot en paralelo. En
// Firecracker la memoria del snapshot se mapea MAP_PRIVATE: los pesos del GGUF
// ya cargados se comparten copy-on-write entre réplicas.
func startVONPool(ctx context.Context, snapshot string, n, cpuPct int) ([]string, func(), error) {
	names := make([]string, n)
	urls := make([]string, n)
	errs := make([]error, n)
	var wg sync.WaitGroup
	for i := 0; i < n; i++ {
		names[i] = fmt.Sprintf("arena-von-%d", i+1)
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			kling(ctx, "rm", names[i])
			t0 := time.Now()
			args := []string{"run", "-from", snapshot, "-name", names[i], "-label", "app=chispa-arena"}
			if cpuPct > 0 {
				args = append(args, "-cpu-pct", fmt.Sprint(cpuPct))
			}
			if _, err := kling(ctx, args...); err != nil {
				errs[i] = err
				return
			}
			ip, err := klingIP(ctx, names[i])
			if err != nil {
				errs[i] = err
				return
			}
			urls[i] = fmt.Sprintf("http://%s:8000", ip)
			for j := 0; j < 600; j++ { // llama-server tarda en contestar tras el restore
				if res, err := http.Get(urls[i] + "/v1/models"); err == nil {
					res.Body.Close()
					if res.StatusCode == 200 {
						break
					}
				}
				time.Sleep(100 * time.Millisecond)
			}
			log.Printf("VON %s listo en %s (%s)", names[i], urls[i], time.Since(t0).Round(time.Millisecond))
		}(i)
	}
	wg.Wait()
	stop := func() {
		c, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cancel()
		for _, n := range names {
			kling(c, "rm", n)
		}
	}
	var ok []string
	for i, u := range urls {
		if errs[i] == nil && u != "" {
			ok = append(ok, u)
		}
	}
	if len(ok) == 0 {
		stop()
		return nil, nil, fmt.Errorf("ninguna réplica VON arrancó: %v", errs[0])
	}
	return ok, stop, nil
}
