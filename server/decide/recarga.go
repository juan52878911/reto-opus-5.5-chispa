package decide

import (
	"crypto/subtle"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strings"
	"sync"
)

// Armado es un modelo completo listo para servir: lo que devuelve un Armador. Todo lo que depende del modelo (L0, L1, L2, sus
// cachés de esquemas y de torres) cuelga de Cascada, así que cada Armado trae cachés nuevas.
type Armado struct {
	Cascada         *Cascada
	CacheRespuestas int
	Limites         Limites
	AdminToken      string       // admin_token de la config (solo se lee del arranque)
	L0              *L0          // para la métrica de la caché de esquemas (puede ser nil)
	Cerrar          func() error // libera el .chispa; se llama cuando ya no quedan peticiones sobre este modelo (puede ser nil)
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
	s.cur.Store(s.nuevoVivo(a, 1))
	return s
}

// ConRecarga activa Recargar con este armador. token, si no está vacío, abre POST /v1/admin/recargar (cabecera
// Authorization: Bearer <token>); vacío = esa ruta no existe (404). Se llama antes de servir.
func (s *Servidor) ConRecarga(arm Armador, token string) *Servidor {
	s.armador, s.adminToken = arm, token
	return s
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
	nv := s.nuevoVivo(a, old.gen+1)
	s.cur.Store(nv)
	old.retirar()
	s.Met.Recarga("ok")
	log.Printf("recarga: modelo %d en servicio", nv.gen)
	return nil
}

func (s *Servidor) nuevoVivo(a *Armado, gen uint64) *vivo {
	n := a.CacheRespuestas
	if n < 1 {
		n = 1
	}
	if a.L0 != nil {
		s.Met.FijaEsquemas(a.L0.Hits.Load, a.L0.Misses.Load)
	}
	return &vivo{casc: a.Cascada, nonces: NewLRU[[]byte](n), lim: normalizaLimites(a.Limites), gen: gen, cerrar: a.Cerrar}
}

// admin atiende POST /v1/admin/recargar.
func (s *Servidor) admin(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		w.Header().Set("Allow", "POST")
		s.fallo(w, http.StatusMethodNotAllowed, ErrMetodo, "", "método %s no permitido: usa POST", r.Method)
		return
	}
	got, ok := strings.CutPrefix(r.Header.Get("Authorization"), "Bearer ")
	if !ok || subtle.ConstantTimeCompare([]byte(got), []byte(s.adminToken)) != 1 {
		w.Header().Set("WWW-Authenticate", "Bearer")
		s.fallo(w, http.StatusUnauthorized, ErrNoAutorizado, "", "token de administración ausente o incorrecto")
		return
	}
	if err := s.Recargar(); err != nil {
		s.fallo(w, http.StatusInternalServerError, ErrRecargaFallida, "", "recarga fallida, sigue el modelo anterior: %v", err)
		return
	}
	s.Met.Peticion(http.StatusOK)
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]any{"status": "ok", "generation": s.Generacion()})
}
