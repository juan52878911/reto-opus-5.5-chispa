// Package contracts congela los esquemas de la arena (§6 del PLAN). Solo la
// sesión principal los cambia: el resto de paquetes los consume.
package contracts

import "time"

// Dimensiones de la v1 y sus etiquetas, en orden estable.
var Dimensions = map[string][]string{
	"spam":      {"spam", "legit"},
	"injection": {"injection", "safe"},
	"urgencia":  {"alta", "media", "baja"},
	"emocion":   {"alegria", "enojo", "tristeza", "neutral"},
	"toxicidad": {"toxico", "respetuoso"},
	"intencion": {"compra", "soporte", "queja", "saludo"},
}

// DimensionOrder es el orden de presentación.
var DimensionOrder = []string{"spam", "injection", "urgencia", "emocion", "toxicidad", "intencion"}

// Example es una línea de los JSONL de data/<dim>/{train,valid,test}.jsonl.
// Mismo formato que chispa.Example, más el id de plantilla para el reparto
// sin fugas.
type Example struct {
	ID       string         `json:"id"`
	Text     string         `json:"text"`
	Label    string         `json:"label"`
	Fields   map[string]any `json:"fields,omitempty"`
	Template string         `json:"template"`
}

// --- §6.1 detector: POST /decide_batch, GET /health ---

type DecideItem struct {
	ID      string  `json:"id"`
	Text    string  `json:"text"`
	Context *string `json:"context"`
}

type DecideRequest struct {
	Items []DecideItem `json:"items"`
}

type DecideResult struct {
	ID        string             `json:"id"`
	Label     string             `json:"label"`
	Probs     map[string]float64 `json:"probs"`
	Escalate  bool               `json:"escalate"`
	LatencyMS float64            `json:"latency_ms"`
}

type DecideResponse struct {
	DetectorID   string         `json:"detector_id"`
	Dimension    string         `json:"dimension"`
	ModelVersion string         `json:"model_version"`
	Results      []DecideResult `json:"results"`
}

// Health añade al §6.1 el gasto del proceso (CPU y RSS), que el panel enseña.
type Health struct {
	Status       string  `json:"status"`
	ModelVersion string  `json:"model_version"`
	Loaded       bool    `json:"loaded"`
	PID          int     `json:"pid"`
	CPUSeconds   float64 `json:"cpu_seconds"`
	RSSBytes     int64   `json:"rss_bytes"`
	Decisions    int64   `json:"decisions"`
}

// --- §6.2 ataque ---

type Operator struct {
	Name   string         `json:"name"`
	Params map[string]any `json:"params,omitempty"`
}

type Attack struct {
	AttackID     string     `json:"attack_id"`
	SeedID       string     `json:"seed_id"`
	Dimension    string     `json:"dimension"`
	TrueLabel    string     `json:"true_label"`
	OriginalText string     `json:"original_text"`
	AttackedText string     `json:"attacked_text"`
	Generator    string     `json:"generator"` // "mutation" | "search"
	Operators    []Operator `json:"operators"`
	Iteration    int        `json:"iteration"`
	CreatedAt    time.Time  `json:"created_at"`
}

// --- §6.3 resultados ---

type DetectorResult struct {
	AttackID       string             `json:"attack_id"`
	DetectorID     string             `json:"detector_id"`
	PredictedLabel string             `json:"predicted_label"`
	Probs          map[string]float64 `json:"probs"`
	Escalate       bool               `json:"escalate"`
	Fooled         bool               `json:"fooled"`
	LatencyMS      float64            `json:"latency_ms"`
	Error          string             `json:"error,omitempty"` // detector caído
}

type SwarmResult struct {
	AttackID        string  `json:"attack_id"`
	Dimension       string  `json:"dimension"`
	SwarmLabel      string  `json:"swarm_label"`
	SwarmConfidence float64 `json:"swarm_confidence"`
	Escalated       bool    `json:"escalated"`
	Fooled          bool    `json:"fooled"`
	Voters          int     `json:"voters"` // detectores que contestaron
}

// --- §6.4 eventos SSE ---

const (
	EvAttackStarted  = "attack_started"
	EvDetectorResult = "detector_result"
	EvSwarmResult    = "swarm_result"
	EvVMStatus       = "vm_status"
	EvMetrics        = "metrics"
)

type Event struct {
	Type    string    `json:"type"`
	TS      time.Time `json:"ts"`
	Payload any       `json:"payload"`
}

// AttackRound es el payload de swarm_result en el SSE: el ataque completo con
// el voto de cada detector, para que el panel pinte una fila sin cruzar eventos.
type AttackRound struct {
	Attack    Attack           `json:"attack"`
	Detectors []DetectorResult `json:"detectors"`
	Swarm     SwarmResult      `json:"swarm"`
}

// VMStatus: estado de un detector (proceso local o microVM).
type VMStatus struct {
	DetectorID string `json:"detector_id"`
	Dimension  string `json:"dimension"`
	Kind       string `json:"kind"` // chispa-words | chispa-char | chispa-sub | rules
	Addr       string `json:"addr"`
	State      string `json:"state"` // up | down | starting
	Health     Health `json:"health"`
}

// --- §6.6 métricas ---

type DetectorMetrics struct {
	DetectorID    string  `json:"detector_id"`
	Dimension     string  `json:"dimension"`
	Kind          string  `json:"kind"`
	State         string  `json:"state"`
	Attacks       int64   `json:"attacks"`
	Fooled        int64   `json:"fooled"`
	ASR           float64 `json:"asr"`
	Escalations   int64   `json:"escalations"`
	Errors        int64   `json:"errors"`
	P50MS         float64 `json:"p50_ms"`
	P95MS         float64 `json:"p95_ms"`
	TestAccuracy  float64 `json:"test_accuracy"`
	CPUSeconds    float64 `json:"cpu_seconds"`
	RSSBytes      int64   `json:"rss_bytes"`
	Decisions     int64   `json:"decisions"`
	USPerDecision float64 `json:"us_per_decision"` // CPU-µs por decisión
}

type SwarmMetrics struct {
	Dimension      string  `json:"dimension"`
	Attacks        int64   `json:"attacks"`
	Fooled         int64   `json:"fooled"`
	ASR            float64 `json:"asr"`
	Escalated      int64   `json:"escalated"`
	EscalationRate float64 `json:"escalation_rate"`
	BestSingleASR  float64 `json:"best_single_asr"`
	BestSingleID   string  `json:"best_single_id"`
	MeanSingleASR  float64 `json:"mean_single_asr"`
}

type OperatorMetrics struct {
	Name   string  `json:"name"`
	Uses   int64   `json:"uses"`
	Fooled int64   `json:"fooled"` // engañó al menos a un detector
	Rate   float64 `json:"rate"`
}

type Cost struct {
	VCPUHourUSD        float64 `json:"vcpu_hour_usd"` // supuesto (flag)
	TotalCPUSeconds    float64 `json:"total_cpu_seconds"`
	TotalRSSBytes      int64   `json:"total_rss_bytes"`
	TotalDecisions     int64   `json:"total_decisions"`
	USDSoFar           float64 `json:"usd_so_far"`
	USDPerMillion      float64 `json:"usd_per_million"`
	LLMUSD             float64 `json:"llm_usd"` // siempre 0 en el MVP
	CPUMicrosPerDecide float64 `json:"cpu_us_per_decision"`
}

type Metrics struct {
	UptimeS       float64           `json:"uptime_s"`
	Attacks       int64             `json:"attacks"`
	AttacksPerSec float64           `json:"attacks_per_sec"`
	DecisionsPerS float64           `json:"decisions_per_sec"`
	Workers       int               `json:"workers"`
	Detectors     []DetectorMetrics `json:"detectors"`
	Swarms        []SwarmMetrics    `json:"swarms"`
	Operators     []OperatorMetrics `json:"operators"`
	Cost          Cost              `json:"cost"`
	Scale         Scale             `json:"scale"`
	Learning      Learning          `json:"learning"`
	Flow          Flow              `json:"flow"`
}

// --- v2: escala (microVMs) y aprendizaje (VON como maestro) ---

const (
	EvScaleStep  = "scale_step"
	EvLearnBatch = "learn_batch"
)

// ScalePoint es una muestra de la curva «más VMs → cuánto más poder».
type ScalePoint struct {
	TS            time.Time `json:"ts"`
	VMs           int       `json:"vms"`
	AttacksPerSec float64   `json:"attacks_per_sec"`
	DecisionsPerS float64   `json:"decisions_per_sec"`
	P95MS         float64   `json:"p95_ms"`
	HostCPUPct    float64   `json:"host_cpu_pct"` // CPU del host usada (0-100)
	VMMemBytes    int64     `json:"vm_mem_bytes"` // RAM asignada a las VMs
	BootMS        float64   `json:"boot_ms"`      // media de arranque/restore del último escalón
}

type Scale struct {
	Backend        string       `json:"backend"` // "process" | "microvm"
	HostMemBytes   int64        `json:"host_mem_bytes"`
	HostCPUs       int          `json:"host_cpus"`
	BudgetMemBytes int64        `json:"budget_mem_bytes"` // la mitad del host
	BudgetCPUs     int          `json:"budget_cpus"`
	VMMemMiB       int          `json:"vm_mem_mib"`
	VMVCPUs        int          `json:"vm_vcpus"`
	MaxVMs         int          `json:"max_vms"` // lo que cabe en el presupuesto
	TargetVMs      int          `json:"target_vms"`
	LiveVMs        int          `json:"live_vms"`
	Ramping        bool         `json:"ramping"`
	History        []ScalePoint `json:"history"`
	Note           string       `json:"note,omitempty"` // por qué paró la rampa
}

// LearnBatch es una ronda de corrección: ataques que engañaron → VON etiqueta
// → reentreno en sombra → se promociona solo si gana.
type LearnBatch struct {
	ID           int       `json:"id"`
	TS           time.Time `json:"ts"`
	Dimension    string    `json:"dimension"`
	Size         int       `json:"size"`          // ataques que engañaron en el lote
	Teacher      string    `json:"teacher"`       // modelo VON
	TeacherAgree int       `json:"teacher_agree"` // VON confirma la etiqueta verdadera
	Discarded    int       `json:"discarded"`     // VON dice que cambió el significado
	TeacherMS    float64   `json:"teacher_ms"`
	TrainMS      float64   `json:"train_ms"`
	ASRBefore    float64   `json:"asr_before"` // del enjambre sobre el lote de reto
	ASRAfter     float64   `json:"asr_after"`
	CleanBefore  float64   `json:"clean_acc_before"` // exactitud en test limpio
	CleanAfter   float64   `json:"clean_acc_after"`
	Promoted     bool      `json:"promoted"`
	Generation   int       `json:"generation"` // generación de modelos tras el lote
	Note         string    `json:"note,omitempty"`
}

type Learning struct {
	Enabled    bool         `json:"enabled"`
	Teacher    string       `json:"teacher"`
	TeacherUp  bool         `json:"teacher_up"`
	Generation int          `json:"generation"`
	Pending    int          `json:"pending"` // ataques exitosos esperando lote
	BatchSize  int          `json:"batch_size"`
	Batches    []LearnBatch `json:"batches"`
}

// --- v3: flujo Chispa → VON, eficiencia en el tiempo y pesos compartidos ---

const EvEfficiency = "efficiency"

// VONPool: réplicas VON restauradas del mismo snapshot (comparten los pesos
// del GGUF por copy-on-write) que etiquetan lo que Chispa no resuelve.
type VONPool struct {
	Snapshot   string  `json:"snapshot"`
	Replicas   int     `json:"replicas"`
	Calls      int64   `json:"calls"`      // peticiones reales a VON
	CacheHits  int64   `json:"cache_hits"` // etiquetas reutilizadas (mismo texto)
	Queue      int     `json:"queue"`      // esperando etiqueta
	AvgMS      float64 `json:"avg_ms"`     // latencia media por etiqueta
	P95MS      float64 `json:"p95_ms"`
	TokensIn   int64   `json:"tokens_in"`
	TokensOut  int64   `json:"tokens_out"`
	MemBytes   int64   `json:"mem_bytes"` // memoria real de todas las réplicas
	SharedNote string  `json:"shared_note,omitempty"`
}

// EfficiencyPoint: cómo mejora el sistema con cada generación de Chispa.
type EfficiencyPoint struct {
	TS             time.Time `json:"ts"`
	Generation     int       `json:"generation"`
	EscalationRate float64   `json:"escalation_rate"` // fracción que Chispa no resuelve
	VONPer1K       float64   `json:"von_per_1k"`      // llamadas a VON por 1000 decisiones
	SwarmASR       float64   `json:"swarm_asr"`
	CleanAcc       float64   `json:"clean_acc"`
	USDPerMillion  float64   `json:"usd_per_million"` // incluye CPU de VON
	TrainExamples  int       `json:"train_examples"`
}

// WeightSharing: cuánta memoria ahorra restaurar todas las réplicas del mismo
// snapshot con los pesos ya cargados.
type WeightSharing struct {
	ChispaSnapshot   string  `json:"chispa_snapshot"`   // snapshot con el banco de modelos
	ChispaGeneration int     `json:"chispa_generation"` // generación horneada en el snapshot
	ModelBankBytes   int64   `json:"model_bank_bytes"`  // tamaño de los pesos Chispa
	MemPerVMBytes    int64   `json:"mem_per_vm_bytes"`  // memoria real por réplica
	NaiveMemBytes    int64   `json:"naive_mem_bytes"`   // sin compartir (réplicas × RAM de VM)
	RealMemBytes     int64   `json:"real_mem_bytes"`    // medido
	SavedPct         float64 `json:"saved_pct"`
}

// Flow es el estado del bucle Chispa → VON → reentreno que va en Metrics.
type Flow struct {
	VON        VONPool           `json:"von"`
	Efficiency []EfficiencyPoint `json:"efficiency"`
	Sharing    WeightSharing     `json:"sharing"`
	Escalated  int64             `json:"escalated"` // decisiones que Chispa escaló a VON
}
