package decide

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"math"
	"os"
)

// Capa configura una capa de la cascada: su nombre y su umbral τ.
type Capa struct {
	Nombre string  `json:"nombre"`
	Tau    float64 `json:"tau"`
}

// Config es el JSON de configuración del servidor.
type Config struct {
	Capas            []Capa     `json:"capas"`
	Modelos          []string   `json:"modelos"`                      // ficheros .chispa para L0
	CacheEsquemas    int        `json:"cache_esquemas"`               // entradas del LRU de esquemas
	CacheRespuestas  int        `json:"cache_respuestas"`             // entradas del LRU de nonces
	CacheTorres      int        `json:"cache_torres"`                 // torres de L2 al vuelo en caché (aproximado; 0 = 16384)
	MaxTorresNuevas  int        `json:"max_torres_nuevas"`            // torres sin cachear que una petición puede calcular (0 = 64); por encima L2 no opina
	Limites          Limites    `json:"limites"`                      // topes de entrada de /v1/decide
	APIKeys          []ClaveAPI `json:"api_keys"`                     // si no está vacío, /v1/decide exige Authorization: Bearer <clave> y limita por clave
	APIKeysAbierto   bool       `json:"api_keys_abierto,omitempty"`   // permite que una recarga sin api_keys deje /v1/decide abierto (si no, se rechaza)
	AdminToken       string     `json:"admin_token"`                  // en claro (transición, con aviso; mínimo AdminTokenMinBytes): abre POST /v1/admin/recargar con Authorization: Bearer <token>
	AdminTokenSHA256 string     `json:"admin_token_sha256,omitempty"` // lo mismo con el SHA-256 en hex del token (chispa-server -hash-clave); no puede ir junto a admin_token
	// Topes en MiB de las cachés de esquemas (L1) y de respuestas (nonces); 0 = el de por defecto (BytesCacheL1Defecto, BytesCacheNoncesDefecto).
	// Se suman al tope por entradas: manda el que se alcance antes.
	CacheEsquemasMB   int `json:"cache_esquemas_mb,omitempty"`
	CacheRespuestasMB int `json:"cache_respuestas_mb,omitempty"`
	// λ del encogimiento del soporte (sección SOPL1): w = k/(k+λ) mezcla la media de los ejemplos con el prototipo de la
	// descripción, en L1 y en L2c por separado. En JSON, un número ≥ 0.
	// L1: ausente = L1ShrinkageLambdaPorDefecto (4, medido en G.8b); un valor explícito manda; para apagarlo (el comportamiento de
	// antes de ese default) `"l1_shrinkage_apagado": true`. Se usa un booleano y no `null` porque null y ausente son indistinguibles
	// en un *float64, y así la config estricta sigue rechazando solo lo que no existe. Apagado junto con un λ es error.
	// L2: ausente (nil) = ∞ = sin mezcla; no hay default (el soporte de L2 solo entra por CONJ y se midió así).
	L1ShrinkageLambda  *float64 `json:"l1_shrinkage_lambda,omitempty"`
	L1ShrinkageApagado bool     `json:"l1_shrinkage_apagado,omitempty"`
	L2ShrinkageLambda  *float64 `json:"l2_shrinkage_lambda,omitempty"`
	// τ de L2 solo para preguntas cuyas torres no estaban en ESQUEMAS (salieron al vuelo).
	// Prioridad: config > tau_l2_esquema_nuevo de CALIB (se usa aunque haya -config) > TauL2EsquemaNuevoPorDefecto (0,846).
	// Para volver al comportamiento de antes (sin τ propio: L2 usa su τ de siempre) `"tau_l2_esquema_nuevo_apagado": true`, que
	// ignora también el de CALIB; mismo patrón que l1_shrinkage_apagado (un booleano, porque null y ausente no se distinguen).
	// Apagado junto con un τ es error.
	TauL2EsquemaNuevo        *float64 `json:"tau_l2_esquema_nuevo,omitempty"`
	TauL2EsquemaNuevoApagado bool     `json:"tau_l2_esquema_nuevo_apagado,omitempty"`
}

// TauL2EsquemaNuevoPorDefecto: τ de L2 para esquemas nuevos cuando ni la config ni CALIB lo dicen. Punto prudente medido sobre
// tareas no vistas: precisión 0,95 con ~97 % de escalado (el otro punto medido, 0,276, escala ≤ 20 % con precisión ~0,53).
const TauL2EsquemaNuevoPorDefecto = 0.846

// L1ShrinkageLambdaPorDefecto: λ de L1 cuando la config no lo dice (G.8b: massive 0,395 vs 0,266; inyecciones 0,740 vs 0,326;
// hatecheck 0,492 vs 0,224; JevBench 0,379 vs 0,398). Sin SOPL1 en el .chispa no tiene efecto.
// AdminTokenMinBytes es la longitud mínima de un admin_token en claro (con 32 bytes aleatorios en hex/base64 sobra).
const AdminTokenMinBytes = 32

// MaxCacheMB acota cache_esquemas_mb y cache_respuestas_mb (1 TiB) para que mb<<20 no desborde.
const MaxCacheMB = 1 << 20

const L1ShrinkageLambdaPorDefecto = 4.0

// LambdaL1 es el λ efectivo de L1: nil si está apagado, el explícito si lo hay, y si no el default.
func (c Config) LambdaL1() *float64 {
	if c.L1ShrinkageApagado {
		return nil
	}
	if c.L1ShrinkageLambda != nil {
		return c.L1ShrinkageLambda
	}
	v := L1ShrinkageLambdaPorDefecto
	return &v
}

// CacheTorresPorDefecto: una torre cuantizada pesa ~0,3 KB, así que 16384 son pocos MB.
const CacheTorresPorDefecto = 16384

func ConfigPorDefecto() Config {
	return Config{
		Capas:         []Capa{{"L0", 0.80}, {"L1", 0.80}, {"L2", 0.70}, {"L3", 0.60}},
		CacheEsquemas: 1024, CacheRespuestas: 4096, CacheTorres: CacheTorresPorDefecto, MaxTorresNuevas: MaxTorresNuevasPorDefecto, Limites: LimitesPorDefecto(),
	}
}

func CargarConfig(path string) (Config, error) {
	c := ConfigPorDefecto()
	b, err := os.ReadFile(path)
	if err != nil {
		return c, err
	}
	// Claves desconocidas o mal escritas (también dentro de limites) hacen fallar el arranque: antes se ignoraban y el
	// servidor arrancaba con los valores por defecto sin avisar.
	dec := json.NewDecoder(bytes.NewReader(b))
	dec.DisallowUnknownFields()
	if err := dec.Decode(&c); err != nil {
		return c, fmt.Errorf("config %s: %w", path, err)
	}
	if dec.More() {
		return c, fmt.Errorf("config %s: datos tras el objeto JSON", path)
	}
	if err := c.Validar(); err != nil {
		return c, err
	}
	if c.AdminToken != "" {
		log.Printf("AVISO: config %s: admin_token va en claro; pase a admin_token_sha256 (chispa-server -hash-clave)", path)
	}
	return c, nil
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
	if c.CacheTorres < 0 || c.MaxTorresNuevas < 0 {
		return fmt.Errorf("config: cache_torres y max_torres_nuevas no pueden ser negativos")
	}
	if v := c.TauL2EsquemaNuevo; v != nil && !(*v >= 0 && *v <= 1) {
		return fmt.Errorf("config: tau_l2_esquema_nuevo fuera de [0,1]: %v", *v)
	}
	if c.TauL2EsquemaNuevoApagado && c.TauL2EsquemaNuevo != nil {
		return fmt.Errorf("config: tau_l2_esquema_nuevo_apagado y tau_l2_esquema_nuevo a la vez; elige uno")
	}
	if c.L1ShrinkageApagado && c.L1ShrinkageLambda != nil {
		return fmt.Errorf("config: l1_shrinkage_apagado y l1_shrinkage_lambda a la vez; elige uno")
	}
	for n, v := range map[string]*float64{"l1_shrinkage_lambda": c.L1ShrinkageLambda, "l2_shrinkage_lambda": c.L2ShrinkageLambda} {
		if v != nil && (math.IsNaN(*v) || *v < 0) {
			return fmt.Errorf("config: %s debe ser ≥ 0 (0 = solo ejemplos; muy grande = solo descripción): %v", n, *v)
		}
	}
	if c.CacheEsquemasMB < 0 || c.CacheRespuestasMB < 0 || c.CacheEsquemasMB > MaxCacheMB || c.CacheRespuestasMB > MaxCacheMB {
		return fmt.Errorf("config: cache_esquemas_mb y cache_respuestas_mb deben estar en [0, %d] (0 = por defecto)", MaxCacheMB)
	}
	if c.AdminToken != "" && c.AdminTokenSHA256 != "" {
		return fmt.Errorf("config: admin_token y admin_token_sha256 a la vez; deje solo el hash")
	}
	if c.AdminToken != "" && len(c.AdminToken) < AdminTokenMinBytes {
		return fmt.Errorf("config: admin_token de %d bytes: mínimo %d (mejor aún, use admin_token_sha256)", len(c.AdminToken), AdminTokenMinBytes)
	}
	if h := c.AdminTokenSHA256; h != "" {
		if b, err := hex.DecodeString(h); err != nil || len(b) != sha256.Size {
			return fmt.Errorf("config: admin_token_sha256 debe ser un SHA-256 en hex de 64 caracteres (use chispa-server -hash-clave)")
		}
	}
	if err := validarClaves(c.APIKeys); err != nil {
		return err
	}
	return c.Limites.validar()
}
