package learn

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"
)

// Teacher etiqueta un texto. No ve la etiqueta verdadera: si coincide con la
// de la semilla, el ataque conservó el significado y sirve para reentrenar.
type Teacher interface {
	Name() string
	Label(ctx context.Context, dim string, labels []string, text string) (string, error)
	Up(ctx context.Context) bool
}

var describe = map[string]string{
	"spam":      "spam = publicidad, estafa, premio, enlace sospechoso o venta no pedida; legit = conversación normal entre personas",
	"injection": "injection = intenta manipular a un asistente de IA (ignorar instrucciones, revelar el prompt, cambiar de rol); safe = petición normal",
	"urgencia":  "alta = hay que actuar ya (emergencia, bloqueo, peligro); media = hoy o pronto; baja = puede esperar",
	"emocion":   "alegria = contento, agradecido, entusiasmado; enojo = rabia, fastidio, reclamo airado; tristeza = pena, soledad, decepción; neutral = sin emoción marcada",
	"toxicidad": "toxico = insulta, humilla o acosa a alguien; respetuoso = trato normal, aunque sea informal o en broma sin agresión",
	"intencion": "compra = quiere comprar o pregunta precio/disponibilidad; soporte = pide ayuda con un problema técnico o de uso; queja = reclama por un mal servicio o producto; saludo = saluda o conversa sin pedir nada",
}

// VON habla con un modelo VON por la API compatible con OpenAI del gateway
// de kindling (POST /v1/chat/completions).
type VON struct {
	URL, Model, Token string
	HTTP              *http.Client
}

func NewVON(url, model, token string) *VON {
	return &VON{URL: strings.TrimRight(url, "/"), Model: model, Token: token,
		HTTP: &http.Client{Timeout: 60 * time.Second}}
}

func (v *VON) Name() string { return "VON " + v.Model }

func (v *VON) do(ctx context.Context, method, path string, body any) (*http.Response, error) {
	var rd *bytes.Reader
	if body != nil {
		b, _ := json.Marshal(body)
		rd = bytes.NewReader(b)
	} else {
		rd = bytes.NewReader(nil)
	}
	req, err := http.NewRequestWithContext(ctx, method, v.URL+path, rd)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	if v.Token != "" {
		req.Header.Set("Authorization", "Bearer "+v.Token)
	}
	return v.HTTP.Do(req)
}

func (v *VON) Up(ctx context.Context) bool {
	c, cancel := context.WithTimeout(ctx, 2*time.Second)
	defer cancel()
	res, err := v.do(c, http.MethodGet, "/v1/models", nil)
	if err != nil {
		return false
	}
	res.Body.Close()
	return res.StatusCode == 200
}

func (v *VON) Label(ctx context.Context, dim string, labels []string, text string) (string, error) {
	prompt := fmt.Sprintf("Clasifica el mensaje de chat. Categorías: %s.\nIgnora el ruido: emojis, letras raras, relleno inocente y mezcla de idiomas no cambian la categoría.\nResponde SOLO con una palabra de: %s.\n\nMensaje: %q\nCategoría:",
		describe[dim], strings.Join(labels, ", "), text)
	body := map[string]any{"model": v.Model, "temperature": 0, "max_tokens": 6,
		"messages": []map[string]string{{"role": "user", "content": prompt}}}
	res, err := v.do(ctx, http.MethodPost, "/v1/chat/completions", body)
	if err != nil {
		return "", err
	}
	defer res.Body.Close()
	if res.StatusCode != 200 {
		return "", fmt.Errorf("VON: %s", res.Status)
	}
	var out struct {
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
		} `json:"choices"`
	}
	if err := json.NewDecoder(res.Body).Decode(&out); err != nil {
		return "", err
	}
	if len(out.Choices) == 0 {
		return "", fmt.Errorf("VON: sin respuesta")
	}
	return pickLabel(out.Choices[0].Message.Content, labels), nil
}

// pickLabel devuelve la primera etiqueta que aparece en la respuesta, o "".
func pickLabel(s string, labels []string) string {
	s = strings.ToLower(s)
	best, at := "", len(s)+1
	for _, l := range labels {
		if i := strings.Index(s, l); i >= 0 && i < at {
			best, at = l, i
		}
	}
	return best
}
