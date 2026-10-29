package main

import (
	"net"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestPausaErrorBackoff(t *testing.T) {
	if pausaError(1) != 10*time.Millisecond || pausaError(2) != 20*time.Millisecond {
		t.Fatalf("backoff: %v %v", pausaError(1), pausaError(2))
	}
	if pausaError(100) != 500*time.Millisecond {
		t.Fatalf("tope: %v", pausaError(100))
	}
}

func TestServidorCaidoNoGiraSinPausa(t *testing.T) {
	l, _ := net.Listen("tcp", "127.0.0.1:0")
	url := "http://" + l.Addr().String()
	l.Close()
	cli := &http.Client{Timeout: time.Second}
	_, errs, _ := trabajar(cli, url, [][]byte{[]byte("{}")}, 0, 1, time.Now().Add(300*time.Millisecond), false)
	if errs == 0 || errs > 30 {
		t.Fatalf("errores=%d: sin pausa serían miles; con backoff, pocos pero contados", errs)
	}
}

func TestTimeoutServidorColgado(t *testing.T) {
	parar := make(chan struct{})
	srv := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) { <-parar }))
	defer srv.Close()
	defer close(parar)
	cli := &http.Client{Timeout: 100 * time.Millisecond}
	t0 := time.Now()
	_, errs, _ := trabajar(cli, srv.URL, [][]byte{[]byte("{}")}, 0, 1, time.Now().Add(300*time.Millisecond), false)
	if errs == 0 || time.Since(t0) > 2*time.Second {
		t.Fatalf("errs=%d en %v", errs, time.Since(t0))
	}
}
