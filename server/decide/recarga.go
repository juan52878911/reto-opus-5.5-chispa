package decide

import (
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

// Armado es un modelo completo listo para servir: lo que devuelve un Armador. Todo lo que depende del modelo (L0, L1, L2, sus
// cachés de esquemas y de torres) cuelga de Cascada, así que cada Armado trae cachés nuevas.
type Armado struct {
	Cascada          *Cascada
	CacheRespuestas  int
	BytesNonces      int // tope en bytes de la caché de nonces (cache_respuestas_mb); 0 = BytesCacheNoncesDefecto
	Limites          Limites
	APIKeys          []ClaveAPI   // api_keys de la config: se releen en cada recarga (los cubos de las claves que siguen se conservan)
	APIKeysAbierto   bool         // api_keys_abierto de la config: permite que una recarga deje /v1/decide sin claves
	AdminToken       string       // admin_token de la config (en claro; transición)
	AdminTokenSHA256 string       // admin_token_sha256 de la config; manda sobre AdminToken. Se relee en cada recarga (rota el token)
	L0               *L0          // para la métrica de la caché de esquemas (puede ser nil)
	Cerrar           func() error // libera el .chispa; se llama cuando ya no quedan peticiones sobre este modelo (puede ser nil)
}

// Armador construye un Armado desde cero (releyendo config y .chispa). Si falla, el servidor sigue con el modelo anterior.
type Armador func() (*Armado, error)

// vivo es el modelo que atiende peticiones: la cascada y todo lo que no debe cruzarse entre modelos. La caché de nonces es
// suya, así que un nonce de un modelo anterior no puede devolver su respuesta con el nuevo. Se cuenta cuántas peticiones lo usan
// para cerrar el fichero solo cuando la última del modelo viejo termina.
type vivo struct {
	casc   *Cascada
	nonces *LRU[[]byte]
	lim    Limites
	auth   *autenticador // nil = /v1/decide sin clave
	gen    uint64
	cerrar func() error

	mu       sync.Mutex
	refs     int
	retirado bool
	cerrado  bool
}

func (v *vivo) tomar() bool {
	v.mu.Lock()
	defer v.mu.Unlock()
	if v.cerrado {
		return false
	}
	v.refs++
	return true
}

func (v *vivo) soltar() {
	v.mu.Lock()
	v.refs--
	cerrar := v.retirado && v.refs == 0 && !v.cerrado
	if cerrar {
		v.cerrado = true
	}
	v.mu.Unlock()
	if cerrar {
		v.cierra()
	}
}

func (v *vivo) retirar() {
	v.mu.Lock()
	v.retirado = true
	cerrar := v.refs == 0 && !v.cerrado
	if cerrar {
		v.cerrado = true
	}
	v.mu.Unlock()
	if cerrar {
		v.cierra()
	}
}

func (v *vivo) cierra() {
	if v.cerrar == nil {
		return
	}
	if err := v.cerrar(); err != nil {
		log.Printf("recarga: cerrar el modelo %d: %v", v.gen, err)
	}
}

// adquirir devuelve el modelo actual con una referencia; hay que llamar a soltar. Si justo lo retiran y se cierra, reintenta
// con el nuevo.
func (s *Servidor) adquirir() *vivo {
	for {
		v := s.cur.Load()
		if v.tomar() {
			return v
		}
	}
}

// NuevoServidorDe es NuevoServidor con un Armado completo (incluye su Cerrar y su L0 para las métricas).
func NuevoServidorDe(a *Armado, met *Metricas) *Servidor {
	s := &Servidor{Met: met}
	met.adminEst().cred.Store(a.credencialAdmin())
	s.cur.Store(s.nuevoVivo(a, 1, nil))
	if n := len(a.APIKeys); n > 0 {
		log.Printf("arranque: %d claves de API activas", n)
	} else {
		log.Print("AVISO: arranque sin claves de API: /v1/decide está abierto")
	}
	return s
}

// ConRecarga activa Recargar con este armador. token, si no está vacío, abre POST /v1/admin/recargar (cabecera
// Authorization: Bearer <token>); vacío = esa ruta no existe (404). Se llama antes de servir.
func (s *Servidor) ConRecarga(arm Armador, token string) *Servidor {
	s.armador, s.adminToken = arm, token
	if token != "" {
		s.Met.adminEst().cred.Store(credDeToken(token))
	}
	return s
}

// ConRecargaDe es ConRecarga con las credenciales de admin del Armado de arranque: admite admin_token_sha256 (hash) además del
// token en claro. Sin ninguna de las dos la ruta no existe (404). Las recargas posteriores releen el token del Armado nuevo.
func (s *Servidor) ConRecargaDe(arm Armador, a *Armado) *Servidor {
	c := a.credencialAdmin()
	if c == nil {
		return s.ConRecarga(arm, "")
	}
	s.armador = arm
	if a.AdminTokenSHA256 == "" {
		s.adminToken = a.AdminToken
	} else {
		// http.go solo conoce un token en claro para abrir la ruta y para /metrics protegidas: se le da uno aleatorio que nadie
		// conoce. /metrics protegidas se abre con esa credencial vigente o con una api_key.
		var b [32]byte
		rand.Read(b[:])
		s.adminToken = hex.EncodeToString(b[:])
	}
	s.Met.adminEst().cred.Store(c)
	return s
}

// credAdmin es el SHA-256 del token de administración. Comparar hashes (y no el token) no revela su longitud.
type credAdmin struct{ h [sha256.Size]byte }

func credDeToken(t string) *credAdmin { return &credAdmin{sha256.Sum256([]byte(t))} }

func (a *Armado) credencialAdmin() *credAdmin {
	if a == nil {
		return nil
	}
	if a.AdminTokenSHA256 != "" {
		b, err := hex.DecodeString(strings.ToLower(a.AdminTokenSHA256))
		if err != nil || len(b) != sha256.Size {
			return nil
		}
		c := &credAdmin{}
		copy(c.h[:], b)
		return c
	}
	if a.AdminToken != "" {
		return credDeToken(a.AdminToken)
	}
	return nil
}

// Intentos de admin: un cubo por IP de origen (ráfaga adminRafaga, adminRPS por segundo). Con el cubo de la IP vacío se responde 429
// sin mirar el token (la fuerza bruta desde una IP no pasa de ~adminRPS intentos/s); un acierto devuelve su ficha. Como el cubo es por
// IP, un atacante no deja fuera al operador que llega de otra. Recomendado: -admin-addr en un puerto privado.
const (
	adminRafaga   = 10
	adminRPS      = 1.0
	adminMaxCubos = 4096 // IPs distintas recordadas; al llenarse se purgan las rellenas y, si no basta, comparten el cubo «desborde»
)

// adminCubo es un token bucket de intentos.
type adminCubo struct {
	mu     sync.Mutex
	fichas float64
	ultimo time.Time
}

// adminEstado es el estado de la ruta de admin de un Servidor (por *Metricas): credencial vigente, cubos por IP y contador de rechazos.
type adminEstado struct {
	rechazos atomic.Uint64
	cred     atomic.Pointer[credAdmin]
	mu       sync.Mutex
	ips      map[string]*adminCubo
	desborde adminCubo
}

var adminEstados sync.Map // *Metricas -> *adminEstado

func (m *Metricas) adminEst() *adminEstado {
	if v, ok := adminEstados.Load(m); ok {
		return v.(*adminEstado)
	}
	v, _ := adminEstados.LoadOrStore(m, &adminEstado{desborde: adminCubo{fichas: adminRafaga}})
	return v.(*adminEstado)
}

func (c *adminCubo) toma(ahora time.Time) bool {
	c.mu.Lock()
	defer c.mu.Unlock()
	if !c.ultimo.IsZero() {
		c.fichas += ahora.Sub(c.ultimo).Seconds() * adminRPS
		if c.fichas > adminRafaga {
			c.fichas = adminRafaga
		}
	}
	c.ultimo = ahora
	if c.fichas < 1 {
		return false
	}
	c.fichas--
	return true
}

func (c *adminCubo) devuelve() {
	c.mu.Lock()
	if c.fichas < adminRafaga {
		c.fichas++
	}
	c.mu.Unlock()
}

// cubo devuelve el cubo de la IP de origen de r (el de desborde si la tabla está llena de IPs con ficha pendiente de rellenar).
func (e *adminEstado) cubo(r *http.Request, ahora time.Time) *adminCubo {
	ip, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		ip = r.RemoteAddr
	}
	e.mu.Lock()
	defer e.mu.Unlock()
	if c, ok := e.ips[ip]; ok {
		return c
	}
	if e.ips == nil {
		e.ips = map[string]*adminCubo{}
	}
	if len(e.ips) >= adminMaxCubos {
		for k, c := range e.ips { // un cubo que ya estaría lleno no guarda nada: se olvida
			c.mu.Lock()
			lleno := c.fichas+ahora.Sub(c.ultimo).Seconds()*adminRPS >= adminRafaga
			c.mu.Unlock()
			if lleno {
				delete(e.ips, k)
			}
		}
		if len(e.ips) >= adminMaxCubos {
			return &e.desborde
		}
	}
	c := &adminCubo{fichas: adminRafaga}
	e.ips[ip] = c
	return c
}

// AdminRechazos son los intentos fallidos o limitados contra /v1/admin/recargar (chispa_admin_rechazos_total).
func (m *Metricas) AdminRechazos() uint64 { return m.adminEst().rechazos.Load() }

// EscribeAdmin añade chispa_admin_rechazos_total al texto de /metrics.
func (m *Metricas) EscribeAdmin(w io.Writer) {
	fmt.Fprintln(w, "# HELP chispa_admin_rechazos_total Intentos contra /v1/admin/recargar con token ausente o incorrecto, o rechazados por el cubo de intentos.")
	fmt.Fprintln(w, "# TYPE chispa_admin_rechazos_total counter")
	fmt.Fprintf(w, "chispa_admin_rechazos_total %d\n", m.AdminRechazos())
}

// Generacion es el número del modelo en servicio: 1 el de arranque, +1 por cada recarga que prospera.
func (s *Servidor) Generacion() uint64 { return s.cur.Load().gen }

// Recargar arma un modelo nuevo y lo sustituye atómicamente. Las peticiones en vuelo terminan sobre el viejo. Si armar falla,
// se queda el viejo, se registra el error y se cuenta chispa_recargas_total{resultado="error"}. Las recargas se serializan.
func (s *Servidor) Recargar() error {
	if s.armador == nil {
		return fmt.Errorf("recarga: el servidor no tiene armador")
	}
	s.recMu.Lock()
	defer s.recMu.Unlock()
	a, err := s.armador()
	if err == nil && (a == nil || a.Cascada == nil) {
		err = fmt.Errorf("el armador no devolvió cascada")
	}
	if err != nil {
		s.Met.Recarga("error")
		log.Printf("recarga fallida, sigue el modelo %d: %v", s.cur.Load().gen, err)
		return err
	}
	old := s.cur.Load()
	if old.auth != nil && len(a.APIKeys) == 0 && !a.APIKeysAbierto {
		err := fmt.Errorf("la config nueva no trae api_keys y dejaría /v1/decide abierto; se rechaza (ponga \"api_keys_abierto\": true si es a propósito)")
		if a.Cerrar != nil {
			a.Cerrar()
		}
		s.Met.Recarga("error")
		log.Printf("recarga rechazada, sigue el modelo %d con sus %d claves de API: %v", old.gen, len(old.auth.claves), err)
		return err
	}
	if s.adminToken != "" { // la ruta de admin existe: la recarga rota el token
		if c := a.credencialAdmin(); c != nil {
			s.Met.adminEst().cred.Store(c)
		} else {
			log.Print("AVISO: recarga: la config nueva no trae admin_token ni admin_token_sha256; sigue el token anterior")
		}
	}
	nv := s.nuevoVivo(a, old.gen+1, old.auth)
	s.cur.Store(nv)
	a.Cascada.PublicaCalib()
	old.retirar()
	s.Met.Recarga("ok")
	if nv.auth == nil {
		log.Printf("AVISO: recarga: modelo %d en servicio SIN claves de API: /v1/decide está abierto", nv.gen)
	} else {
		log.Printf("recarga: modelo %d en servicio, %d claves de API activas", nv.gen, len(nv.auth.claves))
	}
	return nil
}

func (s *Servidor) nuevoVivo(a *Armado, gen uint64, prev *autenticador) *vivo {
	n := a.CacheRespuestas
	if n < 1 {
		n = 1
	}
	if a.L0 != nil {
		s.Met.FijaEsquemas(a.L0.Hits.Load, a.L0.Misses.Load)
	}
	s.Met.FijaTauNuevo(a.Cascada.tauNuevo)
	if gen == 1 { // arranque: no hay modelo anterior al que mentir; las recargas publican tras sustituirlo (Recargar)
		a.Cascada.PublicaCalib()
	}
	return &vivo{casc: a.Cascada, nonces: nuevosNonces(n, a.BytesNonces), lim: normalizaLimites(a.Limites), auth: nuevoAutenticadorDe(a.APIKeys, nil, prev), gen: gen, cerrar: a.Cerrar}
}

func nuevosNonces(n, bytes int) *LRU[[]byte] {
	if bytes <= 0 {
		return NewLRU[[]byte](n)
	}
	c := newLRU[[]byte](n, bytes, func(v []byte) int { return len(v) })
	registraNonces(c)
	return c
}

// admin atiende POST /v1/admin/recargar.
func (s *Servidor) admin(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		w.Header().Set("Allow", "POST")
		s.fallo(w, http.StatusMethodNotAllowed, ErrMetodo, "", "método %s no permitido: usa POST", r.Method)
		return
	}
	est := s.Met.adminEst()
	cubo := est.cubo(r, time.Now())
	if !cubo.toma(time.Now()) {
		est.rechazos.Add(1)
		w.Header().Set("Retry-After", "1")
		s.fallo(w, http.StatusTooManyRequests, ErrLimitada, "", "demasiados intentos contra la ruta de administración")
		return
	}
	got, ok := bearer(r.Header.Get("Authorization"))
	cred := est.cred.Load()
	var gh [sha256.Size]byte
	if ok {
		gh = sha256.Sum256([]byte(got))
	}
	if !ok || cred == nil || subtle.ConstantTimeCompare(gh[:], cred.h[:]) != 1 {
		est.rechazos.Add(1)
		w.Header().Set("WWW-Authenticate", "Bearer")
		s.fallo(w, http.StatusUnauthorized, ErrNoAutorizado, "", "token de administración ausente o incorrecto")
		return
	}
	cubo.devuelve()
	if err := s.Recargar(); err != nil {
		s.fallo(w, http.StatusInternalServerError, ErrRecargaFallida, "", "recarga fallida, sigue el modelo anterior: %v", err)
		return
	}
	s.Met.Peticion(http.StatusOK)
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]any{"status": "ok", "generation": s.Generacion()})
}
