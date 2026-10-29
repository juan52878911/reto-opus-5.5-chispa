package decide

import (
	"context"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"fmt"
	"math"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"
)

// ClaveAPI es una clave de API de la config (api_keys). Nunca lleva la clave en claro: solo su SHA-256 en hexadecimal.
type ClaveAPI struct {
	ID         string  `json:"id"`          // etiqueta de la clave en las métricas (nunca el secreto)
	HashSHA256 string  `json:"hash_sha256"` // sha256(clave) en hex (64 caracteres); lo imprime `chispa-server -hash-clave`
	RPS        float64 `json:"rps"`         // peticiones por segundo sostenidas (> 0)
	Rafaga     int     `json:"rafaga"`      // capacidad del cubo (0 = ceil(rps), mínimo 1)
}

// HashClave devuelve el SHA-256 en hex de una clave en claro.
func HashClave(clave string) string {
	h := sha256.Sum256([]byte(clave))
	return hex.EncodeToString(h[:])
}

var idClaveValido = regexp.MustCompile(`^[A-Za-z0-9_.-]{1,64}$`)

// bearer extrae la clave de una cabecera Authorization: el esquema no distingue mayúsculas (RFC 7235) y se toleran espacios
// repetidos entre esquema y credencial. ok es false si el esquema no es Bearer o no hay credencial.
func bearer(cab string) (string, bool) {
	esq, resto, _ := strings.Cut(strings.TrimLeft(cab, " \t"), " ")
	if !strings.EqualFold(esq, "Bearer") {
		return "", false
	}
	resto = strings.TrimLeft(resto, " \t")
	return resto, resto != ""
}

func validarClaves(ks []ClaveAPI) error {
	ids := map[string]bool{}
	hashes := map[string]bool{}
	for i, k := range ks {
		if k.ID == "" || ids[k.ID] {
			return fmt.Errorf("config: api_keys[%d]: id vacío o repetido: %q", i, k.ID)
		}
		if !idClaveValido.MatchString(k.ID) {
			return fmt.Errorf("config: api_keys[%d]: id %q no válido: use [A-Za-z0-9_.-], 1 a 64 caracteres", i, k.ID)
		}
		ids[k.ID] = true
		h := strings.ToLower(k.HashSHA256)
		if b, err := hex.DecodeString(h); err != nil || len(b) != sha256.Size {
			return fmt.Errorf("config: api_keys[%d] (%s): hash_sha256 debe ser un SHA-256 en hex de 64 caracteres (use chispa-server -hash-clave)", i, k.ID)
		}
		if hashes[h] {
			return fmt.Errorf("config: api_keys[%d] (%s): hash_sha256 repetido", i, k.ID)
		}
		hashes[h] = true
		if !(k.RPS > 0) || math.IsInf(k.RPS, 0) {
			return fmt.Errorf("config: api_keys[%d] (%s): rps debe ser > 0", i, k.ID)
		}
		if k.Rafaga < 0 {
			return fmt.Errorf("config: api_keys[%d] (%s): rafaga no puede ser negativa", i, k.ID)
		}
	}
	return nil
}

// cubo es un token bucket: capacidad cap, recarga rps tokens por segundo.
type cubo struct {
	mu     sync.Mutex
	tokens float64
	cap    float64
	rps    float64
	ultimo time.Time
}

// reajusta cambia capacidad y tasa sin devolver tokens: si la capacidad baja, los tokens se recortan.
func (c *cubo) reajusta(cap, rps float64) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.cap, c.rps = cap, rps
	c.tokens = math.Min(c.tokens, cap)
}

// toma gasta un token. Si no hay, devuelve los segundos (enteros, ≥ 1) tras los que habrá uno.
func (c *cubo) toma(ahora time.Time) (bool, int) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if d := ahora.Sub(c.ultimo).Seconds(); d > 0 {
		c.tokens = math.Min(c.cap, c.tokens+d*c.rps)
		c.ultimo = ahora
	}
	if c.tokens >= 1 {
		c.tokens--
		return true, 0
	}
	espera := int(math.Ceil((1 - c.tokens) / c.rps))
	if espera < 1 {
		espera = 1
	}
	return false, espera
}

// cobra descuenta n tokens sin comprobar, sin bajar de 0: un lote válido (hasta max_preguntas) no deja deuda que bloquee a la clave
// durante minutos; a lo sumo vacía el cubo y la siguiente petición espera lo que tarde en llegar un token.
func (c *cubo) cobra(n int, ahora time.Time) {
	if n <= 0 {
		return
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	if d := ahora.Sub(c.ultimo).Seconds(); d > 0 {
		c.tokens = math.Min(c.cap, c.tokens+d*c.rps)
		c.ultimo = ahora
	}
	c.tokens = math.Max(0, c.tokens-float64(n))
}

// cobroClave es lo que conAuth deja en el ctx para cobrar el coste (preguntas) de la petición a la clave que la hizo.
type cobroClave struct {
	k     *claveViva
	ahora func() time.Time
}

type ctxCobro struct{}

func cobroDe(ctx context.Context) *cobroClave {
	c, _ := ctx.Value(ctxCobro{}).(*cobroClave)
	return c
}

func (c *cobroClave) cobra(n int) {
	if c != nil {
		c.k.cubo.cobra(n, c.ahora())
	}
}

// id es el id de la clave autenticada ("" si /v1/decide está abierto).
func (c *cobroClave) id() string {
	if c == nil {
		return ""
	}
	return c.k.id
}

type claveViva struct {
	id   string
	hash [sha256.Size]byte
	cubo *cubo
}

// autenticador valida Authorization: Bearer <clave> contra las claves de la config y aplica el cubo de cada una.
type autenticador struct {
	claves []claveViva
	ahora  func() time.Time
}

func nuevoAutenticador(ks []ClaveAPI, ahora func() time.Time) *autenticador {
	return nuevoAutenticadorDe(ks, ahora, nil)
}

// nuevoAutenticadorDe es nuevoAutenticador reutilizando los cubos de prev para las claves con el mismo id y hash (la recarga
// no debe rellenarlos); cap y rps se actualizan por si cambiaron. ahora nil = el reloj de prev, o el real.
func nuevoAutenticadorDe(ks []ClaveAPI, ahora func() time.Time, prev *autenticador) *autenticador {
	if len(ks) == 0 {
		return nil
	}
	if ahora == nil && prev != nil {
		ahora = prev.ahora
	}
	if ahora == nil {
		ahora = time.Now
	}
	a := &autenticador{ahora: ahora}
	for _, k := range ks {
		raf := k.Rafaga
		if raf < 1 {
			raf = int(math.Ceil(k.RPS))
		}
		cv := claveViva{id: k.ID}
		b, _ := hex.DecodeString(strings.ToLower(k.HashSHA256))
		copy(cv.hash[:], b)
		if prev != nil {
			for _, p := range prev.claves {
				if p.id == cv.id && p.hash == cv.hash {
					p.cubo.reajusta(float64(raf), k.RPS)
					cv.cubo = p.cubo
					break
				}
			}
		}
		if cv.cubo == nil {
			cv.cubo = &cubo{tokens: float64(raf), cap: float64(raf), rps: k.RPS, ultimo: ahora()}
		}
		a.claves = append(a.claves, cv)
	}
	return a
}

// busca devuelve la clave cuyo hash coincide con el de la presentada. Recorre todas con comparación en tiempo constante.
func (a *autenticador) busca(presentada string) *claveViva {
	h := sha256.Sum256([]byte(presentada))
	var hallada *claveViva
	for i := range a.claves {
		if subtle.ConstantTimeCompare(h[:], a.claves[i].hash[:]) == 1 {
			hallada = &a.claves[i]
		}
	}
	return hallada
}

// ConClaves cambia las claves de API del modelo en servicio (nil/vacío = /v1/decide abierto). Se llama antes de servir;
// las recargas traen las suyas en Armado.APIKeys. ahora puede ser nil (reloj real).
func (s *Servidor) ConClaves(ks []ClaveAPI, ahora func() time.Time) *Servidor {
	v := s.cur.Load()
	v.auth = nuevoAutenticador(ks, ahora)
	return s
}

// conAuth protege un handler con las claves de API. Sin claves configuradas, pasa todo como antes.
func (s *Servidor) conAuth(h http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		a := s.cur.Load().auth
		if a == nil {
			h(w, r)
			return
		}
		got, ok := bearer(r.Header.Get("Authorization"))
		var k *claveViva
		if ok {
			k = a.busca(got)
		}
		if k == nil {
			s.Met.AuthRechazo()
			w.Header().Set("WWW-Authenticate", "Bearer")
			s.fallo(w, http.StatusUnauthorized, ErrNoAutorizado, "", "clave de API ausente o incorrecta: use Authorization: Bearer <clave>")
			return
		}
		if ok, espera := k.cubo.toma(a.ahora()); !ok {
			s.Met.Clave(k.id, "limitada")
			w.Header().Set("Retry-After", strconv.Itoa(espera))
			s.fallo(w, http.StatusTooManyRequests, ErrLimitada, "", "límite de tasa de la clave %q superado: reintente en %d s", k.id, espera)
			return
		}
		s.Met.Clave(k.id, "ok")
		h(w, r.WithContext(context.WithValue(r.Context(), ctxCobro{}, &cobroClave{k: k, ahora: a.ahora})))
	}
}
