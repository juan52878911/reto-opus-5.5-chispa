// Package chispa es el cliente Go de POST /v1/decide y GET /healthz de chispa-server. Sin dependencias fuera de la biblioteca estándar.
//
// Política de reintentos (la misma que sdk/python/chispa/cliente.py y docs/05-sdks.md):
//   - se reintenta el error de red y el 503 que no sea de timeout, con espera exponencial espera·2^(n-1) y, si hay Retry-After
//     en segundos, al menos esa espera (tope 30 s);
//   - no se reintenta el timeout propio (el servidor cancela y no guarda nada bajo el nonce), el 503 `timeout` del servidor, el 504
//     ni ningún otro estado (400, 405, 413, 429, 500, 502…): se devuelve *ErrorChispa en el acto, con RetryAfter si lo hubo;
//   - el timeout por defecto (35 s) es mayor que el -timeout del servidor (30 s).
package chispa

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"
	"time"
)

const (
	TimeoutPorDefecto = 35 * time.Second
	topeRetryAfter    = 30 * time.Second
	topeRespuesta     = 16 << 20
)

// Cliente es seguro para uso concurrente una vez creado.
type Cliente struct {
	url        string
	http       *http.Client
	timeout    time.Duration
	reintentos int
	espera     time.Duration
	apiKey     string
	limites    Limites
	dormir     func(ctx context.Context, d time.Duration) error
}

// Opt configura un Cliente.
type Opt func(*Cliente)

// ConTimeout fija el timeout de cada intento (incluye leer el cuerpo). Debe superar el -timeout del servidor (30 s).
func ConTimeout(d time.Duration) Opt { return func(c *Cliente) { c.timeout = d } }

// ConReintentos fija los reintentos extra tras el primer intento (3 por defecto).
func ConReintentos(n int) Opt { return func(c *Cliente) { c.reintentos = max(n, 0) } }

// ConEspera fija la espera base del backoff exponencial (200 ms por defecto).
func ConEspera(d time.Duration) Opt { return func(c *Cliente) { c.espera = d } }

// ConAPIKey envía `Authorization: Bearer <clave>` si el servidor la pide.
func ConAPIKey(k string) Opt { return func(c *Cliente) { c.apiKey = k } }

// ConLimites cambia los límites locales si el operador tocó la sección `limites` del servidor.
func ConLimites(l Limites) Opt { return func(c *Cliente) { c.limites = l } }

// ConHTTPClient usa otro http.Client (transporte, proxy, TLS). No le pongas Timeout: el cliente aplica el suyo por intento.
func ConHTTPClient(h *http.Client) Opt { return func(c *Cliente) { c.http = h } }

// Nuevo crea un cliente para el servidor en url (p. ej. "http://127.0.0.1:8090").
func Nuevo(url string, opts ...Opt) *Cliente {
	c := &Cliente{
		url: strings.TrimRight(url, "/"), http: &http.Client{}, timeout: TimeoutPorDefecto, reintentos: 3,
		espera: 200 * time.Millisecond, limites: LimitesPorDefecto(), dormir: dormir,
	}
	for _, o := range opts {
		o(c)
	}
	return c
}

func dormir(ctx context.Context, d time.Duration) error {
	t := time.NewTimer(d)
	defer t.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-t.C:
		return nil
	}
}

// DecidirOpts son opciones de una llamada a Decidir.
type DecidirOpts struct {
	// Nonce da clave de idempotencia a las preguntas que no traen la suya: tal cual con una sola pregunta, `nonce:id` con varias.
	Nonce string
}

// Decidir decide las preguntas sobre el mismo estado; los resultados vienen en el orden de preguntas. opts puede ser nil.
// Valida en local como el servidor (todo o nada). Cada pregunta sin nonce recibe uno antes del primer intento y los reintentos
// lo repiten: el servidor devuelve el resultado guardado en vez de decidir otra vez. Un nonce vacío cuenta como ausente.
// Todos los errores son *ErrorChispa.
func (c *Cliente) Decidir(ctx context.Context, estado string, preguntas []Pregunta, opts *DecidirOpts) ([]Resultado, error) {
	if e := c.limites.validar(estado, preguntas); e != nil {
		return nil, e
	}
	base := ""
	if opts != nil {
		base = opts.Nonce
	}
	qs := make([]Pregunta, len(preguntas))
	for i, q := range preguntas {
		if q.Nonce == "" {
			switch {
			case base == "":
				q.Nonce = nonceAleatorio()
			case len(preguntas) == 1:
				q.Nonce = base
			default:
				q.Nonce = base + ":" + q.ID
			}
		}
		qs[i] = q
	}
	if e := c.limites.validar(estado, qs); e != nil { // el nonce derivado también cuenta en bytes
		return nil, e
	}
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false) // el servidor mide el cuerpo en bytes: no inflarlo con <
	if err := enc.Encode(peticion{State: estado, Questions: qs}); err != nil {
		return nil, &ErrorChispa{Codigo: "invalid_json", Mensaje: err.Error(), Causa: err}
	}
	if n := buf.Len(); n > c.limites.MaxCuerpo {
		return nil, falla("request_too_large", fmt.Sprintf("cuerpo: %d bytes, máximo %d", n, c.limites.MaxCuerpo), "")
	}
	datos, err := c.pedir(ctx, http.MethodPost, "/v1/decide", buf.Bytes())
	if err != nil {
		return nil, err
	}
	var r respuesta
	if err := json.Unmarshal(datos, &r); err != nil || len(r.Results) != len(qs) {
		return nil, &ErrorChispa{Codigo: CodRespuesta, Mensaje: "la respuesta no trae un resultado por pregunta", Status: 200, Causa: err}
	}
	for i := range r.Results {
		if r.Results[i].ID != qs[i].ID {
			return nil, &ErrorChispa{Codigo: CodRespuesta, Mensaje: "la respuesta no trae las preguntas en orden", Status: 200}
		}
	}
	return r.Results, nil
}

// Salud comprueba /healthz: nil si contesta {"status":"ok"}. Sin reintentos.
func (c *Cliente) Salud(ctx context.Context) error {
	datos, err := c.intento(ctx, http.MethodGet, "/healthz", nil)
	if err != nil {
		return err
	}
	var h struct {
		Status string `json:"status"`
	}
	if json.Unmarshal(datos, &h) != nil || h.Status != "ok" {
		return &ErrorChispa{Codigo: CodRespuesta, Mensaje: "/healthz no dice ok", Status: 200}
	}
	return nil
}

func (c *Cliente) pedir(ctx context.Context, metodo, ruta string, cuerpo []byte) ([]byte, error) {
	var ultimo *ErrorChispa
	for i := 0; i <= c.reintentos; i++ {
		if i > 0 { // el cuerpo es el mismo en todos los intentos, nonce incluido
			if err := c.dormir(ctx, max(c.espera<<(i-1), ultimo.RetryAfter)); err != nil {
				return nil, cancelado(err)
			}
		}
		datos, err := c.intento(ctx, metodo, ruta, cuerpo)
		if err == nil {
			return datos, nil
		}
		var ec *ErrorChispa
		if !errors.As(err, &ec) || !reintentable(ec) {
			return nil, err
		}
		ultimo = ec
	}
	ultimo.Mensaje += fmt.Sprintf(" (tras %d intentos)", c.reintentos+1)
	return nil, ultimo
}

func cancelado(err error) *ErrorChispa {
	return &ErrorChispa{Codigo: CodCancelado, Mensaje: err.Error(), Causa: err}
}

// reintentable: error de red, cuerpo 200 ilegible y 503 que no sea `timeout`. Ni el timeout propio, ni el 504, ni otros estados.
func reintentable(e *ErrorChispa) bool {
	switch {
	case e.Status == 503:
		return e.Codigo != CodTimeout
	case e.Status != 0 && e.Status != 200:
		return false
	}
	return e.Codigo == CodRed || e.Codigo == CodRespuesta
}

func (c *Cliente) intento(ctx context.Context, metodo, ruta string, cuerpo []byte) ([]byte, error) {
	cx, cancel := context.WithTimeout(ctx, c.timeout)
	defer cancel()
	var rd io.Reader
	if cuerpo != nil {
		rd = bytes.NewReader(cuerpo)
	}
	req, err := http.NewRequestWithContext(cx, metodo, c.url+ruta, rd)
	if err != nil {
		return nil, &ErrorChispa{Codigo: CodRed, Mensaje: err.Error(), Causa: err}
	}
	if cuerpo != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	if c.apiKey != "" {
		req.Header.Set("Authorization", "Bearer "+c.apiKey)
	}
	resp, err := c.http.Do(req)
	var texto []byte
	if err == nil {
		defer resp.Body.Close()
		texto, err = io.ReadAll(io.LimitReader(resp.Body, topeRespuesta)) // el timeout cubre también la lectura del cuerpo
	}
	if err != nil {
		if ctx.Err() != nil { // el llamador canceló o su plazo venció
			return nil, cancelado(ctx.Err())
		}
		if cx.Err() != nil {
			return nil, &ErrorChispa{Codigo: CodTimeout, Mensaje: fmt.Sprintf("%s: sin respuesta en %v (no se reintenta)", ruta, c.timeout), Causa: err}
		}
		return nil, &ErrorChispa{Codigo: CodRed, Mensaje: fmt.Sprintf("%s%s: %v", c.url, ruta, err), Causa: err}
	}
	if resp.StatusCode/100 == 2 {
		if !json.Valid(texto) {
			return nil, &ErrorChispa{Codigo: CodRespuesta, Mensaje: ruta + ": el cuerpo no es JSON", Status: resp.StatusCode}
		}
		return texto, nil
	}
	return nil, errorHTTP(resp, texto)
}

func errorHTTP(resp *http.Response, texto []byte) *ErrorChispa {
	e := &ErrorChispa{Status: resp.StatusCode, RetryAfter: retryAfter(resp.Header.Get("Retry-After"))}
	var cu cuerpoError
	if json.Unmarshal(texto, &cu) == nil && len(cu.Error) > 0 {
		var t struct {
			Code       string `json:"code"`
			Message    string `json:"message"`
			QuestionID string `json:"question_id"`
		}
		var s string
		switch {
		case json.Unmarshal(cu.Error, &t) == nil && t.Code != "":
			e.Codigo, e.Mensaje, e.IDPregunta = t.Code, t.Message, t.QuestionID
			return e
		case json.Unmarshal(cu.Error, &s) == nil: // formato viejo {"error":"texto"}
			e.Codigo, e.Mensaje = CodHTTPGenerico, s
			return e
		}
	}
	e.Codigo = CodHTTPGenerico
	e.Mensaje = strings.TrimSpace(string(texto[:min(len(texto), 200)]))
	return e
}

// retryAfter lee Retry-After en segundos (con tope de 30 s); una fecha HTTP u otra cosa cuenta como ausente (0).
func retryAfter(v string) time.Duration {
	s, err := strconv.ParseFloat(strings.TrimSpace(v), 64)
	if err != nil || s != s || s <= 0 { // s != s: NaN
		return 0
	}
	if s >= topeRetryAfter.Seconds() {
		return topeRetryAfter
	}
	return time.Duration(s * float64(time.Second))
}

func nonceAleatorio() string {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		panic(err) // crypto/rand no falla en las plataformas soportadas
	}
	return hex.EncodeToString(b[:])
}
