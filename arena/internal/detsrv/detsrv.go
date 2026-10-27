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
	"strings"
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
	return serve(addr, id, dim, load, nil, 0)
}

// ServeBank sirve en modo banco: carga todos los modelos de dir, los deja
// residentes y arranca vacío. POST /configure sin cuerpo elige del banco
// (páginas compartidas entre réplicas restauradas); con cuerpo hace una copia
// privada. GET /bank describe el banco.
func ServeBank(addr, dir string, generation int) error {
	b, err := detectors.LoadBank(dir)
	if err != nil {
		return err
	}
	return serve(addr, "", "", nil, b, generation)
}

// BankInfo es la respuesta de GET /bank.
type BankInfo struct {
	Generation int         `json:"generation"`
	Models     []BankModel `json:"models"`
	Active     string      `json:"active"`
	Shared     bool        `json:"shared"`
}

type BankModel struct {
	ID     string `json:"id"`
	Bytes  int    `json:"bytes"`
	SHA256 string `json:"sha256"`
}

func serve(addr, id, dim string, load func() (detectors.Detector, error), bank *detectors.Bank, generation int) error {
	mux, err := buildMux(id, dim, load, bank, generation)
	if err != nil {
		return err
	}
	return http.ListenAndServe(addr, mux)
}

func buildMux(id, dim string, load func() (detectors.Detector, error), bank *detectors.Bank, generation int) (*http.ServeMux, error) {
	var shared atomic.Bool
	var decisions atomic.Int64
	var activeID atomic.Value
	var cur atomic.Pointer[detectors.Detector]
	var ident atomic.Pointer[[2]string]
	ident.Store(&[2]string{id, dim})
	if load != nil {
		first, err := load()
		if err != nil {
			return nil, err
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
		var d detectors.Detector
		fromBank := false
		if len(b) == 0 && bank != nil {
			var ok bool
			if d, ok = bank.Get(q.Get("dim"), q.Get("kind")); !ok {
				http.Error(w, "modelo fuera del banco: "+detectors.ID(q.Get("dim"), q.Get("kind")), 404)
				return
			}
			fromBank = true
		} else if d, err = detectors.FromBytes(q.Get("dim"), q.Get("kind"), b); err != nil {
			http.Error(w, err.Error(), 400)
			return
		}
		ident.Store(&[2]string{q.Get("id"), q.Get("dim")})
		cur.Store(&d)
		shared.Store(fromBank)
		activeID.Store(detectors.ID(q.Get("dim"), q.Get("kind")))
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
	mux.HandleFunc("POST /bank/put", func(w http.ResponseWriter, r *http.Request) {
		if bank == nil {
			http.Error(w, "sin banco", 400)
			return
		}
		b, err := io.ReadAll(io.LimitReader(r.Body, 64<<20))
		if err == nil {
			err = bank.Put(r.URL.Query().Get("dim"), r.URL.Query().Get("kind"), b)
		}
		if err != nil {
			http.Error(w, err.Error(), 400)
			return
		}
		w.WriteHeader(200)
	})
	// /decide_multi: un lote con elementos de varios detectores del banco. Así
	// un nodo recibe un solo viaje por lote aunque sirva 12 detectores.
	mux.HandleFunc("POST /decide_multi", func(w http.ResponseWriter, r *http.Request) {
		if bank == nil {
			http.Error(w, "sin banco", 400)
			return
		}
		var req MultiRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, err.Error(), 400)
			return
		}
		out := make([]contracts.DecideResult, len(req.Items))
		for i, it := range req.Items {
			d, ok := bank.Get(it.Dim, it.Kind)
			if !ok {
				http.Error(w, "modelo no está en el banco: "+it.Dim+"-"+it.Kind, 404)
				return
			}
			t0 := time.Now()
			dec := d.Decide(it.Text)
			out[i] = contracts.DecideResult{ID: it.ID, Label: dec.Label, Probs: dec.Probs, Escalate: dec.Escalate,
				LatencyMS: float64(time.Since(t0).Nanoseconds()) / 1e6}
		}
		decisions.Add(int64(len(req.Items)))
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(MultiResponse{Results: out})
	})
	mux.HandleFunc("POST /decide_batch", func(w http.ResponseWriter, r *http.Request) {
		var req contracts.DecideRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		// Nodo del enjambre: ?dim=&kind= elige del banco por petición, así una
		// sola microVM sirve los 12 detectores con los pesos compartidos.
		var det detectors.Detector
		idd := *ident.Load()
		if q := r.URL.Query(); bank != nil && q.Get("dim") != "" {
			d, ok := bank.Get(q.Get("dim"), q.Get("kind"))
			if !ok {
				http.Error(w, "modelo no está en el banco", 404)
				return
			}
			det, idd = d, [2]string{q.Get("dim") + "-" + q.Get("kind"), q.Get("dim")}
		} else {
			dp := cur.Load()
			if dp == nil {
				http.Error(w, "sin modelo: falta /configure", 503)
				return
			}
			det = *dp
		}
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
	mux.HandleFunc("GET /bank", func(w http.ResponseWriter, r *http.Request) {
		info := BankInfo{Generation: generation, Models: []BankModel{}, Shared: shared.Load()}
		if a, ok := activeID.Load().(string); ok {
			info.Active = a
		}
		if bank != nil {
			for _, e := range bank.Entries() {
				info.Models = append(info.Models, BankModel{ID: e.ID, Bytes: e.Bytes, SHA256: e.SHA256})
			}
		}
		_ = json.NewEncoder(w).Encode(info)
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
	return mux, nil
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
	Base  string
	Query string
	HTTP  *http.Client
}

// NewClient admite base con consulta ("http://ip:9000?dim=spam&kind=rules"):
// la consulta se añade a /decide_batch (nodo del enjambre).
func NewClient(base string) *Client {
	q := ""
	if i := strings.IndexByte(base, '?'); i >= 0 {
		base, q = base[:i], base[i:]
	}
	tr := &http.Transport{MaxIdleConnsPerHost: 256, MaxConnsPerHost: 256, IdleConnTimeout: 30 * time.Second}
	return &Client{Base: base, Query: q, HTTP: &http.Client{Transport: tr, Timeout: 2 * time.Second}}
}

func (c *Client) DecideBatch(ctx context.Context, items []contracts.DecideItem) (*contracts.DecideResponse, error) {
	b, _ := json.Marshal(contracts.DecideRequest{Items: items})
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.Base+"/decide_batch"+c.Query, bytes.NewReader(b))
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

// Bank consulta GET /bank.
func (c *Client) Bank(ctx context.Context) (*BankInfo, error) {
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, c.Base+"/bank", nil)
	res, err := c.HTTP.Do(req)
	if err != nil {
		return nil, err
	}
	defer res.Body.Close()
	if res.StatusCode != 200 {
		return nil, fmt.Errorf("bank: %s", res.Status)
	}
	var b BankInfo
	return &b, json.NewDecoder(res.Body).Decode(&b)
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

// BankPut sustituye un modelo en el banco de un nodo.
func (c *Client) BankPut(ctx context.Context, dim, kind string, model []byte) error {
	u := fmt.Sprintf("%s/bank/put?dim=%s&kind=%s", c.Base, url.QueryEscape(dim), url.QueryEscape(kind))
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
		return fmt.Errorf("bank/put: %s %s", res.Status, b)
	}
	return nil
}

type MultiItem struct {
	ID   string `json:"id"`
	Text string `json:"text"`
	Dim  string `json:"dim"`
	Kind string `json:"kind"`
}

type MultiRequest struct {
	Items []MultiItem `json:"items"`
}

type MultiResponse struct {
	Results []contracts.DecideResult `json:"results"`
}

// DecideMulti manda un lote mezclado a un nodo (POST /decide_multi).
func (c *Client) DecideMulti(ctx context.Context, items []MultiItem) ([]contracts.DecideResult, error) {
	b, _ := json.Marshal(MultiRequest{Items: items})
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.Base+"/decide_multi", bytes.NewReader(b))
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
		return nil, fmt.Errorf("decide_multi: %s", res.Status)
	}
	var out MultiResponse
	if err := json.NewDecoder(res.Body).Decode(&out); err != nil {
		return nil, err
	}
	if len(out.Results) != len(items) {
		return nil, fmt.Errorf("decide_multi: %d resultados para %d items", len(out.Results), len(items))
	}
	return out.Results, nil
}
