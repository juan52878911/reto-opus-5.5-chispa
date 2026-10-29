package main

import (
	"context"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func init() { minOcio = 0 } // los tests previos expulsan ociosas recién creadas

// R10-1: con el tope lleno y nadie esperando, las keep-alive no se cortan (antes: ~28 % de EOF).
func TestTopeLlenoSinEsperaNoCortaKeepAlive(t *testing.T) {
	old := minOcio
	minOcio = time.Second // el valor de producción
	defer func() { minOcio = old }()
	ts := httptest.NewUnstartedServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { fmt.Fprint(w, "ok") }))
	ts.Config = nuevoHTTPServer("", ts.Config.Handler, time.Second)
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	ts.Listener = limitarConexiones(ln, 2)
	ts.Start()
	defer ts.Close()
	var nuevas atomic.Int32
	var errs, oks atomic.Int32
	var wg sync.WaitGroup
	for i := 0; i < 2; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			cl := &http.Client{Transport: &http.Transport{
				MaxIdleConnsPerHost: 1,
				DialContext: func(ctx context.Context, n, a string) (net.Conn, error) {
					nuevas.Add(1)
					return (&net.Dialer{}).DialContext(ctx, n, a)
				},
			}}
			for j := 0; j < 200; j++ {
				resp, err := cl.Post(ts.URL, "text/plain", nil)
				if err != nil {
					errs.Add(1)
					continue
				}
				io.Copy(io.Discard, resp.Body) // leer hasta EOF devuelve la conexión al pool antes del siguiente POST (sin dial especulativo)
				resp.Body.Close()
				oks.Add(1)
			}
		}()
	}
	wg.Wait()
	if errs.Load() != 0 || nuevas.Load() != 2 {
		t.Fatalf("ok=%d errores=%d conexiones nuevas=%d (esperado 400/0/2)", oks.Load(), errs.Load(), nuevas.Load())
	}
}

// R10-6: una ociosa más joven que minOcio no se expulsa; una madura sí.
func TestExpulsarSoloOciosasMaduras(t *testing.T) {
	old := minOcio
	minOcio = 200 * time.Millisecond
	defer func() { minOcio = old }()
	ln, _ := net.Listen("tcp", "127.0.0.1:0")
	ll := limitarConexiones(ln, 1).(*limitListener)
	defer ll.Close()
	cli, _ := net.Dial("tcp", ln.Addr().String())
	defer cli.Close()
	s, _ := ll.Accept()
	s.(*conLimitada).ociosa(true)
	if v, hubo := ll.expulsarOciosa(); hubo || v != nil {
		t.Fatal("expulsó una ociosa joven")
	}
	time.Sleep(250 * time.Millisecond)
	if v, _ := ll.expulsarOciosa(); v == nil {
		t.Fatal("no expulsó una ociosa madura")
	}
}
