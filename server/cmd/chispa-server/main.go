// chispa-server sirve POST /v1/decide, /healthz y /metrics.
package main

import (
	"flag"
	"log"
	"net/http"
	"time"

	"chispa/format/chispa3"
	"chispa/runtime/tok"
	"github.com/juan52878911/chispa/server/decide"
)

func main() {
	addr := flag.String("addr", "127.0.0.1:8090", "dirección de escucha")
	cfgPath := flag.String("config", "", "JSON de configuración (capas, τ, modelos, cachés)")
	modelo := flag.String("modelo", "", ".chispa v3 (o v2 envuelto) del que armar L0, L1 y L2 según sus secciones")
	rutaTok := flag.String("tok", "", ".chispa-tok de e5 (runtime/tok/exportar.py); sin él, L2 queda en stub")
	flag.Parse()
	cfg := decide.ConfigPorDefecto()
	if *cfgPath != "" {
		var err error
		if cfg, err = decide.CargarConfig(*cfgPath); err != nil {
			log.Fatal(err)
		}
	}
	l0 := decide.NuevoL0(cfg.CacheEsquemas)
	if err := l0.Cargar(cfg.Modelos...); err != nil {
		log.Fatal(err)
	}
	met := decide.NuevasMetricas()
	met.EsquemaHits = l0.Hits.Load
	met.EsquemaMisses = l0.Misses.Load
	capaL1, capaL2 := decide.NuevoL1(), decide.NuevoL2()
	if *modelo != "" {
		f, err := chispa3.Abrir(*modelo)
		if err != nil {
			log.Fatal(err)
		}
		defer f.Close()
		var tk decide.Tokenizador
		if *rutaTok != "" {
			t, err := tok.Abrir(*rutaTok)
			if err != nil {
				log.Fatal(err)
			}
			tk = tokE5{t}
		}
		mt, err := decide.ArmarDesde(f, l0, &cfg, *cfgPath == "", tk)
		if err != nil {
			log.Fatal(err)
		}
		for _, a := range mt.Avisos {
			log.Print(a)
		}
		capaL1, capaL2 = mt.L1, mt.L2
	}
	casc, err := decide.NuevaCascada(cfg.Capas, []decide.Decisor{l0, capaL1, capaL2, decide.NuevoL3()}, met)
	if err != nil {
		log.Fatal(err)
	}
	srv := &http.Server{Addr: *addr, Handler: decide.NuevoServidor(casc, met, cfg.CacheRespuestas).Handler(),
		ReadHeaderTimeout: 5 * time.Second}
	log.Printf("chispa-server en %s: %d modelos en L0", *addr, l0.NumModelos())
	log.Fatal(srv.ListenAndServe())
}

// tokE5 adapta runtime/tok a decide.Tokenizador (ids int64 para el ONNX).
type tokE5 struct{ t *tok.Tokenizador }

func (e tokE5) IDs(texto string) []int64 {
	ids := e.t.Tokenizar(texto)
	out := make([]int64, len(ids))
	for i, v := range ids {
		out[i] = int64(v)
	}
	return out
}
