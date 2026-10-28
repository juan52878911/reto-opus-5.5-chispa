package decide

import (
	"encoding/json"
	"fmt"
	"os"
)

// Capa configura una capa de la cascada: su nombre y su umbral τ.
type Capa struct {
	Nombre string  `json:"nombre"`
	Tau    float64 `json:"tau"`
}

// Config es el JSON de configuración del servidor.
type Config struct {
	Capas           []Capa   `json:"capas"`
	Modelos         []string `json:"modelos"`          // ficheros .chispa para L0
	CacheEsquemas   int      `json:"cache_esquemas"`   // entradas del LRU de esquemas
	CacheRespuestas int      `json:"cache_respuestas"` // entradas del LRU de nonces
}

func ConfigPorDefecto() Config {
	return Config{
		Capas:         []Capa{{"L0", 0.80}, {"L1", 0.80}, {"L2", 0.70}, {"L3", 0.60}},
		CacheEsquemas: 1024, CacheRespuestas: 4096,
	}
}

func CargarConfig(path string) (Config, error) {
	c := ConfigPorDefecto()
	b, err := os.ReadFile(path)
	if err != nil {
		return c, err
	}
	if err := json.Unmarshal(b, &c); err != nil {
		return c, fmt.Errorf("config %s: %w", path, err)
	}
	return c, c.Validar()
}

func (c Config) Validar() error {
	if len(c.Capas) == 0 {
		return fmt.Errorf("config: hace falta al menos una capa")
	}
	seen := map[string]bool{}
	for _, l := range c.Capas {
		if l.Nombre == "" || seen[l.Nombre] {
			return fmt.Errorf("config: nombre de capa vacío o repetido: %q", l.Nombre)
		}
		seen[l.Nombre] = true
		if l.Tau < 0 || l.Tau > 1 {
			return fmt.Errorf("config: tau de %s fuera de [0,1]: %v", l.Nombre, l.Tau)
		}
	}
	if c.CacheEsquemas < 1 || c.CacheRespuestas < 1 {
		return fmt.Errorf("config: los tamaños de caché deben ser >= 1")
	}
	return nil
}
