// chispa-server sirve POST /v1/decide, /healthz y /metrics (contrato: server/api/openapi.yaml).
package main

import (
	"errors"
	"flag"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
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
	timeout := flag.Duration("timeout", 30*time.Second, "tope de tiempo por petición (cancela su ctx y responde 503 con Retry-After y código timeout); 0 = sin tope")
	ortLib := flag.String("ort-lib", "", "libonnxruntime.so para L2 y la torre (precede a CHISPA_ORT_LIB y a -ldflags -X …decide.RutaORT; vacío = la del sistema)")
	flag.Parse()
	rutaORT, origenORT = fijarRutaORT(*ortLib)
	log.Printf("ORT: ruta %q (%s)", rutaORT, origenORT)
	armar := func(met *decide.Metricas) decide.Armador {
		return func() (*decide.Armado, error) { return armarModelo(met, *cfgPath, *modelo, *rutaTok) }
	}
	met := decide.NuevasMetricas()
	// SIGHUP se registra antes de armar (tarda segundos): sin Notify, Go lo trataría como salida. Un HUP durante el arranque
	// queda encolado y se atiende cuando el servidor está listo (el modelo recién armado ya es el de la config actual,
	// así que ese primer HUP se descarta en lugar de armar dos veces).
	sighup := make(chan os.Signal, 1)
	signal.Notify(sighup, syscall.SIGHUP)
	// Arranque: cualquier fallo es fatal. Recargas: el servidor conserva el modelo anterior.
	inicial, err := armar(met)()
	if err != nil {
		log.Fatal(err)
	}
	srv0 := decide.NuevoServidorDe(inicial, met)
	srv0.ConRecarga(armar(met), inicial.AdminToken)
	handler := montarHandler(srv0, inicial.AdminToken, *timeout, met)
	go func() {
		select {
		case <-sighup: // llegó durante el arranque: el modelo recién armado ya lo refleja
		default:
		}
		for range sighup {
			log.Print("SIGHUP: recargando el modelo")
			srv0.Recargar() // ya registra el error y cuenta la métrica
		}
	}()
	srv := &http.Server{Addr: *addr, Handler: handler, ReadHeaderTimeout: 5 * time.Second}
	log.Printf("chispa-server en %s: %d modelos en L0", *addr, inicial.L0.NumModelos())
	log.Fatal(srv.ListenAndServe())
}

// armarModelo relee la config y el .chispa y arma una cascada completa con cachés propias. Lo usan el arranque y cada recarga
// (SIGHUP o POST /v1/admin/recargar); si algo falla devuelve el error sin tocar nada de lo que sirve.
// rutaORT y origenORT: la ruta de ORT resuelta al arrancar y de dónde salió (para los avisos).
var rutaORT, origenORT string

func armarModelo(met *decide.Metricas, cfgPath, modelo, rutaTok string) (*decide.Armado, error) {
	cfg := decide.ConfigPorDefecto()
	if cfgPath != "" {
		var err error
		if cfg, err = decide.CargarConfig(cfgPath); err != nil {
			return nil, err
		}
	}
	l0 := decide.NuevoL0(cfg.CacheEsquemas)
	if err := l0.Cargar(cfg.Modelos...); err != nil {
		return nil, err
	}
	capaL1, capaL2 := decide.NuevoL1(), decide.NuevoL2()
	var cerrar func() error
	if modelo != "" {
		f, err := chispa3.Abrir(modelo)
		if err != nil {
			return nil, err
		}
		cerrar = f.Close
		if f.Tiene(chispa3.TORR) || f.Tiene(chispa3.L2) {
			if err := comprobarORT(); err != nil {
				log.Printf("AVISO: ONNX Runtime no carga (ruta %q, %s): %v. L2 queda en stub y los esquemas nuevos escalan "+
					"(chispa_torres_calculadas_total seguirá en 0); use -ort-lib o CHISPA_ORT_LIB", rutaORT, origenORT, err)
			}
		}
		fallo := func(err error) (*decide.Armado, error) { f.Close(); return nil, err }
		var tk decide.Tokenizador
		if rutaTok != "" {
			t, err := tok.Abrir(rutaTok)
			if err != nil {
				return fallo(err)
			}
			tk = decide.NuevoTokenizadorE5(t)
		}
		mt, err := decide.ArmarDesde(f, l0, &cfg, cfgPath == "", tk)
		if err != nil {
			return fallo(err)
		}
		if f.Tiene(chispa3.TORR) && tk == nil {
			log.Print("el .chispa trae TORR pero falta -tok: sin torres al vuelo, L2 solo decide esquemas de ESQUEMAS")
		}
		for _, a := range mt.Avisos {
			log.Print(a)
		}
		capaL1, capaL2 = mt.L1, mt.L2
		if mt.Cerrar != nil {
			// Las sesiones ORT (L2 y torre) se cierran antes que el .chispa que las alimentó.
			cerrarSesiones := mt.Cerrar
			cerrar = func() error { return errors.Join(cerrarSesiones(), f.Close()) }
		}
	}
	casc, err := decide.NuevaCascadaConTauNuevo(cfg.Capas, []decide.Decisor{l0, capaL1, capaL2, decide.NuevoL3()}, met, cfg.TauL2EsquemaNuevo)
	if err != nil {
		if cerrar != nil {
			cerrar()
		}
		return nil, err
	}
	return &decide.Armado{Cascada: casc, CacheRespuestas: cfg.CacheRespuestas, Limites: cfg.Limites, AdminToken: cfg.AdminToken, L0: l0, Cerrar: cerrar}, nil
}

// montarHandler envuelve el mux del servidor en el -timeout (503 contado en las métricas), salvo /v1/admin/recargar: una recarga
// puede tardar más (L1 grande + ORT en disco lento) y cortarla con 503 invita al operador a reintentar y recargar dos veces.
func montarHandler(srv *decide.Servidor, adminToken string, timeout time.Duration, met *decide.Metricas) http.Handler {
	handler := srv.Handler()
	if timeout <= 0 {
		return handler
	}
	con := decide.ConTimeoutMet(handler, timeout, met)
	if adminToken == "" {
		return con
	}
	mux := http.NewServeMux()
	mux.Handle("/v1/admin/recargar", handler)
	mux.Handle("/", con)
	return mux
}
