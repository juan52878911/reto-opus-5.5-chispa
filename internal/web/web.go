// Package web sirve el panel (index.html embebido), el SSE y la API mínima.
package web

import (
	_ "embed"
	"encoding/json"
	"net/http"
	"sync"
	"time"

	"github.com/juan52878911/chispa/contracts"
)

//go:embed index.html
var indexHTML []byte

// Hub reparte eventos a los clientes SSE. Si un cliente va lento se le
// descartan eventos: el panel muestrea, no necesita todos.
type Hub struct {
	mu      sync.Mutex
	clients map[chan []byte]struct{}
}

func NewHub() *Hub { return &Hub{clients: map[chan []byte]struct{}{}} }

func (h *Hub) Publish(typ string, payload any) {
	b, err := json.Marshal(contracts.Event{Type: typ, TS: time.Now().UTC(), Payload: payload})
	if err != nil {
		return
	}
	h.mu.Lock()
	defer h.mu.Unlock()
	for c := range h.clients {
		select {
		case c <- b:
		default:
		}
	}
}

func (h *Hub) Clients() int {
	h.mu.Lock()
	defer h.mu.Unlock()
	return len(h.clients)
}

// Handler monta /, /events, /metrics y /api/detectors/{id}/{kill,revive}.
func Handler(h *Hub, metrics func() contracts.Metrics, kill, revive func(id string) error, extra func(*http.ServeMux)) http.Handler {
	mux := http.NewServeMux()
	if extra != nil {
		extra(mux)
	}
	mux.HandleFunc("GET /{$}", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.Write(indexHTML)
	})
	mux.HandleFunc("GET /metrics", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(metrics())
	})
	mux.HandleFunc("GET /events", func(w http.ResponseWriter, r *http.Request) {
		fl, ok := w.(http.Flusher)
		if !ok {
			http.Error(w, "sin streaming", 500)
			return
		}
		w.Header().Set("Content-Type", "text/event-stream")
		w.Header().Set("Cache-Control", "no-cache")
		c := make(chan []byte, 512)
		h.mu.Lock()
		h.clients[c] = struct{}{}
		h.mu.Unlock()
		defer func() { h.mu.Lock(); delete(h.clients, c); h.mu.Unlock() }()
		fl.Flush()
		for {
			select {
			case <-r.Context().Done():
				return
			case b := <-c:
				w.Write([]byte("data: "))
				w.Write(b)
				w.Write([]byte("\n\n"))
				fl.Flush()
			}
		}
	})
	act := func(f func(string) error) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			if err := f(r.PathValue("id")); err != nil {
				http.Error(w, err.Error(), 400)
				return
			}
			w.WriteHeader(200)
		}
	}
	mux.HandleFunc("POST /api/detectors/{id}/kill", act(kill))
	mux.HandleFunc("POST /api/detectors/{id}/revive", act(revive))
	return mux
}
