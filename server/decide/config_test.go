package decide

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func escribirConfig(t *testing.T, s string) string {
	t.Helper()
	p := filepath.Join(t.TempDir(), "config.json")
	if err := os.WriteFile(p, []byte(s), 0o600); err != nil {
		t.Fatal(err)
	}
	return p
}

func TestCargarConfigRechazaClavesDesconocidas(t *testing.T) {
	casos := map[string]string{
		"tau_l2_esquema_nueva": `{"tau_l2_esquema_nueva":0.95}`,
		"cache_torre":          `{"cache_torre":5}`,
		"limite":               `{"limite":{"max_estado":10}}`,
		"max_estad":            `{"limites":{"max_estad":10}}`,
	}
	for clave, js := range casos {
		_, err := CargarConfig(escribirConfig(t, js))
		if err == nil || !strings.Contains(err.Error(), clave) {
			t.Errorf("%s: err=%v, quería error con el nombre de la clave", clave, err)
		}
	}
}

func TestCargarConfigValidaSigueAceptada(t *testing.T) {
	c, err := CargarConfig(escribirConfig(t, `{"cache_torres":400,"limites":{"max_estado":10},"tau_l2_esquema_nuevo":0.9}`))
	if err != nil || c.CacheTorres != 400 || c.Limites.MaxEstado != 10 || c.TauL2EsquemaNuevo == nil {
		t.Fatalf("c=%+v err=%v", c, err)
	}
}
