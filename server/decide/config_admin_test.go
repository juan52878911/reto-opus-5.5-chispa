package decide

import (
	"strings"
	"testing"
)

const tok32 = "0123456789abcdef0123456789abcdef"

func TestConfigAdminTokenHashYLongitud(t *testing.T) {
	malos := map[string]string{
		`{"admin_token":"a"}`:                                                             "mínimo",
		`{"admin_token":"` + tok32[:31] + `"}`:                                            "mínimo",
		`{"admin_token_sha256":"abc"}`:                                                    "64 caracteres",
		`{"admin_token_sha256":"` + strings.Repeat("z", 64) + `"}`:                        "64 caracteres",
		`{"admin_token":"` + tok32 + `","admin_token_sha256":"` + HashClave(tok32) + `"}`: "a la vez",
		`{"cache_esquemas_mb":-1}`:                                                        "cache_esquemas_mb",
		`{"cache_respuestas_mb":-5}`:                                                      "cache_respuestas_mb",
		`{"cache_respuestas_mb":99999999999}`:                                             "cache_respuestas_mb",
	}
	for js, quiero := range malos {
		if _, err := CargarConfig(escribirConfig(t, js)); err == nil || !strings.Contains(err.Error(), quiero) {
			t.Errorf("%s: error %v, quería %q", js, err, quiero)
		}
	}
	buenos := []string{
		`{"admin_token":"` + tok32 + `"}`,
		`{"admin_token_sha256":"` + HashClave("a") + `"}`,
		`{"admin_token_sha256":"` + strings.ToUpper(HashClave("a")) + `"}`,
		`{"cache_esquemas_mb":32,"cache_respuestas_mb":16}`,
		`{}`,
	}
	for _, js := range buenos {
		if _, err := CargarConfig(escribirConfig(t, js)); err != nil {
			t.Errorf("%s: %v", js, err)
		}
	}
	c, _ := CargarConfig(escribirConfig(t, `{}`))
	if c.CacheEsquemasMB != 0 || c.CacheRespuestasMB != 0 || c.AdminToken != "" || c.AdminTokenSHA256 != "" {
		t.Errorf("los defaults cambiaron: %+v", c)
	}
}
