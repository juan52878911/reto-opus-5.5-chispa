package main

import (
	"net"
	"sync"
	"testing"
	"time"
)

// R9-H9: una ociosa que pasa a activa entre elegirla y cerrarla no se expulsa.
func TestExpulsarNoCortaLaQueSeActiva(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	ll := limitarConexiones(ln, 1).(*limitListener)
	defer ll.Close()
	cli, err := net.Dial("tcp", ln.Addr().String())
	if err != nil {
		t.Fatal(err)
	}
	defer cli.Close()
	s, err := ll.Accept()
	if err != nil {
		t.Fatal(err)
	}
	c := s.(*conLimitada)
	c.ociosa(true)
	antesDeExpulsar = func() { c.ociosa(false) } // llega una petición justo tras elegirla
	defer func() { antesDeExpulsar = nil }()
	v, hubo := ll.expulsarOciosa()
	if !hubo || v != nil {
		t.Fatalf("no debía expulsar a la conexión ya activa (hubo=%v v=%v)", hubo, v)
	}
	cli.SetReadDeadline(time.Now().Add(100 * time.Millisecond))
	if _, err := cli.Read(make([]byte, 1)); err == nil || !isTimeout(err) {
		t.Fatalf("la conexión activa se cerró: %v", err)
	}
}

func isTimeout(err error) bool {
	ne, ok := err.(net.Error)
	return ok && ne.Timeout()
}

// Carrera (-race): expulsores concurrentes contra transiciones idle/activa; nunca se cierra una activa.
func TestExpulsarCarreraConActivacion(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	ll := limitarConexiones(ln, 64).(*limitListener)
	defer ll.Close()
	var conns []*conLimitada
	for i := 0; i < 32; i++ {
		cli, err := net.Dial("tcp", ln.Addr().String())
		if err != nil {
			t.Fatal(err)
		}
		defer cli.Close()
		s, err := ll.Accept()
		if err != nil {
			t.Fatal(err)
		}
		c := s.(*conLimitada)
		c.ociosa(true)
		conns = append(conns, c)
	}
	var wg sync.WaitGroup
	for g := 0; g < 4; g++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for i := 0; i < 64; i++ {
				if v, _ := ll.expulsarOciosa(); v != nil {
					if v.estado.Load() != estExpulsada {
						t.Error("expulsada sin marca")
					}
				}
			}
		}()
	}
	for _, c := range conns {
		wg.Add(1)
		go func(c *conLimitada) { defer wg.Done(); c.ociosa(false) }(c)
	}
	wg.Wait()
	for _, c := range conns {
		if st := c.estado.Load(); st == estExpulsada && c.desde == 0 {
			t.Error("estado inconsistente")
		}
	}
}
