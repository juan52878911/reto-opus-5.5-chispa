package decide

import (
	"net/http"
	"strings"
	"testing"
	"time"
)

func servidorAdminHash(t *testing.T, token string) (*Servidor, http.Handler, *armadorModelos) {
	t.Helper()
	a := &armadorModelos{etiquetas: []string{"v1", "v2", "v3"}}
	a.t, a.met = t, NuevasMetricas()
	ar, err := a.armar()
	if err != nil {
		t.Fatal(err)
	}
	ar.AdminTokenSHA256 = HashClave(token)
	s := NuevoServidorDe(ar, a.met).ConRecargaDe(a.armar, ar)
	return s, s.Handler(), a
}

// R7 #10: con admin_token_sha256 el token en claro abre la ruta y el hash presentado como token no.
func TestR7AdminTokenConHash(t *testing.T) {
	s, h, _ := servidorAdminHash(t, tok32)
	if rr := recargar(h, "Bearer "+HashClave(tok32)); rr.Code != 401 {
		t.Fatalf("el hash como token: %d", rr.Code)
	}
	if rr := recargar(h, "Bearer "+tok32); rr.Code != 200 || s.Generacion() != 2 {
		t.Fatalf("token correcto: %d %s", rr.Code, rr.Body)
	}
}

// R7 #10: la fuerza bruta se corta con 429 (aun con el token correcto mientras dure) y se cuenta.
func TestR7AdminIntentosLimitadosYMetrica(t *testing.T) {
	s, h, _ := servidorAdminHash(t, tok32)
	var limitados int
	for i := 0; i < 40; i++ {
		rr := recargar(h, "Bearer mal")
		if rr.Code == 429 {
			limitados++
			if rr.Header().Get("Retry-After") == "" {
				t.Fatal("429 sin Retry-After")
			}
		} else if rr.Code != 401 {
			t.Fatalf("intento %d: %d", i, rr.Code)
		}
	}
	if limitados < 25 {
		t.Fatalf("solo %d de 40 intentos limitados", limitados)
	}
	if rr := recargar(h, "Bearer "+tok32); rr.Code != 429 || s.Generacion() != 1 {
		t.Fatalf("con el cubo vacío el token correcto debe esperar: %d", rr.Code)
	}
	if n := s.Met.AdminRechazos(); n != 41 {
		t.Fatalf("chispa_admin_rechazos_total = %d, quería 41", n)
	}
	var sb strings.Builder
	s.Met.EscribeAdmin(&sb)
	if !strings.Contains(sb.String(), "chispa_admin_rechazos_total 41") {
		t.Fatalf("métrica: %s", sb.String())
	}
}

// Un acierto devuelve su ficha: el uso legítimo repetido no se agota.
func TestR7AdminAciertosNoGastanCubo(t *testing.T) {
	_, h, _ := servidorAdminHash(t, tok32)
	for i := 0; i < 30; i++ {
		if rr := recargar(h, "Bearer "+tok32); rr.Code != 200 {
			t.Fatalf("recarga %d: %d", i, rr.Code)
		}
	}
}

func TestR7AdminCuboSeRellena(t *testing.T) {
	e := &adminCubo{fichas: adminRafaga}
	t0 := time.Unix(1000, 0)
	for i := 0; i < adminRafaga; i++ {
		if !e.toma(t0) {
			t.Fatal("ráfaga")
		}
	}
	if e.toma(t0) || !e.toma(t0.Add(1100*time.Millisecond)) {
		t.Fatal("1 intento/s")
	}
}

// R7 #10: «no rota sin reiniciar»: una recarga con otro admin_token_sha256 cambia el token vigente.
func TestR7AdminRotaConRecarga(t *testing.T) {
	a := &armadorModelos{etiquetas: []string{"v1", "v2", "v3"}}
	a.t, a.met = t, NuevasMetricas()
	nuevo := "fedcba9876543210fedcba9876543210"
	ar, _ := a.armar()
	ar.AdminTokenSHA256 = HashClave(tok32)
	llamada := 0
	arm := func() (*Armado, error) {
		x, err := a.armar()
		llamada++
		x.AdminTokenSHA256 = HashClave(nuevo)
		return x, err
	}
	s := NuevoServidorDe(ar, a.met).ConRecargaDe(arm, ar)
	h := s.Handler()
	if rr := recargar(h, "Bearer "+tok32); rr.Code != 200 {
		t.Fatalf("token viejo: %d", rr.Code)
	}
	if rr := recargar(h, "Bearer "+tok32); rr.Code != 401 {
		t.Fatalf("el token viejo sigue valiendo tras rotar: %d", rr.Code)
	}
	if rr := recargar(h, "Bearer "+nuevo); rr.Code != 200 {
		t.Fatalf("token nuevo: %d", rr.Code)
	}
}

// R7 #7: cache_respuestas_mb acota la caché de nonces en bytes.
func TestR7NoncesAcotadasPorBytes(t *testing.T) {
	c := nuevosNonces(100000, 1<<20)
	for i := 0; i < 400; i++ {
		c.Put(strings.Repeat("k", 8)+string(rune('a'+i%26))+strings.Repeat("x", i), make([]byte, 20000))
	}
	if b := c.Bytes(); b > 1<<20 || b == 0 {
		t.Fatalf("bytes = %d, tope %d", b, 1<<20)
	}
}
