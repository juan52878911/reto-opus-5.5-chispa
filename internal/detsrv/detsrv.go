// Package detsrv sirve un detector por HTTP (§6.1: POST /decide_batch,
// GET /health) y trae el cliente que usa el motor de ataques.
package detsrv

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"runtime"
	"sync/atomic"
	"syscall"
	"time"

	"github.com/juan52878911/chispa/contracts"
	"github.com/juan52878911/chispa/internal/detectors"
)

// Serve bloquea sirviendo en addr el detector que devuelve load. POST /reload
// lo vuelve a cargar (el bucle de aprendizaje promociona un modelo nuevo).
//
// Con load == nil arranca vacío (modo microVM): espera POST /configure con
// ?id=&dim=&kind= y el .chispa en el cuerpo; /configure también sirve para
// promocionar un modelo nuevo sin reiniciar.
func Serve(addr, id, dim string, load func() (detectors.Detector, error)) error {
	var decisions atomic.Int64
	var cur atomic.Pointer[detectors.Detector]
	var ident atomic.Pointer[[2]string]
	ident.Store(&[2]string{id, dim})
	if load != nil {
		first, err := load()
		if err != nil {
			return err
		}
		cur.Store(&first)
	}
	mux := http.NewServeMux()
	mux.HandleFunc("POST /configure", func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query()
		b, err := io.ReadAll(io.LimitReader(r.Body, 64<<20))
		if err != nil {
			http.Error(w, err.Error(), 400)
			return
		}
		d, err := detectors.FromBytes(q.Get("dim"), q.Get("kind"), b)
		if err != nil {
			http.Error(w, err.Error(), 400)
			return
		}
		ident.Store(&[2]string{q.Get("id"), q.Get("dim")})
		cur.Store(&d)
		w.Write([]byte(d.Version()))
	})
	mux.HandleFunc("POST /reload", func(w http.ResponseWriter, r *http.Request) {
		if load == nil {
			http.Error(w, "usa /configure", 400)
			return
		}
		d, err := load()
		if err != nil {
			http.Error(w, err.Error(), 500)
			return
		}
		cur.Store(&d)
		w.Write([]byte(d.Version()))
	})
	mux.HandleFunc("POST /decide_batch", func(w http.ResponseWriter, r *http.Request) {
		var req contracts.DecideRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		dp := cur.Load()
		if dp == nil {
			http.Error(w, "sin modelo: falta /configure", 503)
			return
		}
		det := *dp
		idd := *ident.Load()
		resp := contracts.DecideResponse{DetectorID: idd[0], Dimension: idd[1], ModelVersion: det.Version(),
			Results: make([]contracts.DecideResult, len(req.Items))}
		for i, it := range req.Items {
			t0 := time.Now()
			d := det.Decide(it.Text)
			resp.Results[i] = contracts.DecideResult{ID: it.ID, Label: d.Label, Probs: d.Probs,
				Escalate: d.Escalate, LatencyMS: float64(time.Since(t0).Nanoseconds()) / 1e6}
		}
		decisions.Add(int64(len(req.Items)))
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(resp)
	})
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) {
		cpu, rss := Usage()
		ver, loaded := "", false
		if dp := cur.Load(); dp != nil {
			ver, loaded = (*dp).Version(), true
		}
		_ = json.NewEncoder(w).Encode(contracts.Health{Status: "ok", ModelVersion: ver, Loaded: loaded,
			PID: os.Getpid(), CPUSeconds: cpu, RSSBytes: rss, Decisions: decisions.Load()})
	})
	return http.ListenAndServe(addr, mux)
}

// Usage devuelve CPU (usuario+sistema, s) y RSS máximo (bytes) del proceso.
func Usage() (float64, int64) {
	var ru syscall.Rusage
	if err := syscall.Getrusage(syscall.RUSAGE_SELF, &ru); err != nil {
		return 0, 0
	}
	cpu := float64(ru.Utime.Sec+ru.Stime.Sec) + float64(ru.Utime.Usec+ru.Stime.Usec)/1e6
	rss := int64(ru.Maxrss)
	if runtime.GOOS == "linux" {
		rss *= 1024 // Linux da KiB; macOS, bytes
	}
	return cpu, rss
}

// Client habla con un detector.
type Client struct {
	Base string
	HTTP *http.Client
}

func NewClient(base string) *Client {
	tr := &http.Transport{MaxIdleConnsPerHost: 256, MaxConnsPerHost: 256, IdleConnTimeout: 30 * time.Second}
	return &Client{Base: base, HTTP: &http.Client{Transport: tr, Timeout: 2 * time.Second}}
}

func (c *Client) DecideBatch(ctx context.Context, items []contracts.DecideItem) (*contracts.DecideResponse, error) {
	b, _ := json.Marshal(contracts.DecideRequest{Items: items})
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.Base+"/decide_batch", bytes.NewReader(b))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	res, err := c.HTTP.Do(req)
	if err != nil {
		return nil, err
	}
	defer res.Body.Close()
	if res.StatusCode != 200 {
		return nil, fmt.Errorf("decide_batch: %s", res.Status)
	}
	var out contracts.DecideResponse
	if err := json.NewDecoder(res.Body).Decode(&out); err != nil {
		return nil, err
	}
	if len(out.Results) != len(items) {
		return nil, fmt.Errorf("decide_batch: %d resultados para %d items", len(out.Results), len(items))
	}
	return &out, nil
}

func (c *Client) Health(ctx context.Context) (*contracts.Health, error) {
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, c.Base+"/health", nil)
	res, err := c.HTTP.Do(req)
	if err != nil {
		return nil, err
	}
	defer res.Body.Close()
	var h contracts.Health
	return &h, json.NewDecoder(res.Body).Decode(&h)
}

// Reload pide al detector que recargue su modelo del disco.
func (c *Client) Reload(ctx context.Context) error {
	req, _ := http.NewRequestWithContext(ctx, http.MethodPost, c.Base+"/reload", nil)
	res, err := c.HTTP.Do(req)
	if err != nil {
		return err
	}
	res.Body.Close()
	if res.StatusCode != 200 {
		return fmt.Errorf("reload: %s", res.Status)
	}
	return nil
}

// Configure carga en el detector su identidad y su modelo.
func (c *Client) Configure(ctx context.Context, id, dim, kind string, model []byte) error {
	u := fmt.Sprintf("%s/configure?id=%s&dim=%s&kind=%s", c.Base, url.QueryEscape(id), url.QueryEscape(dim), url.QueryEscape(kind))
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, u, bytes.NewReader(model))
	if err != nil {
		return err
	}
	res, err := c.HTTP.Do(req)
	if err != nil {
		return err
	}
	defer res.Body.Close()
	if res.StatusCode != 200 {
		b, _ := io.ReadAll(res.Body)
		return fmt.Errorf("configure: %s %s", res.Status, b)
	}
	return nil
}
