package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/juan52878911/chispa/internal/detectors"
	"github.com/juan52878911/chispa/internal/detsrv"
)

// DetPort es donde escucha el detector dentro de la microVM.
const DetPort = 9000

func kling(ctx context.Context, args ...string) (string, error) {
	out, err := exec.CommandContext(ctx, "kling", args...).CombinedOutput()
	if err != nil {
		return string(out), fmt.Errorf("kling %s: %v: %s", strings.Join(args, " "), err, strings.TrimSpace(string(out)))
	}
	return string(out), nil
}

func klingIP(ctx context.Context, name string) (string, error) {
	out, err := kling(ctx, "inspect", name)
	if err != nil {
		return "", err
	}
	var m struct {
		IP string `json:"ip"`
	}
	if err := json.Unmarshal([]byte(out), &m); err != nil || m.IP == "" {
		return "", fmt.Errorf("inspect %s: sin ip", name)
	}
	return m.IP, nil
}

// vmLauncher: cada réplica es una microVM restaurada del snapshot dorado
// (`kling run -from`). El detector arranca vacío y recibe su modelo por HTTP;
// con bank=true el snapshot ya trae todos los pesos y /configure va sin cuerpo
// (páginas compartidas entre réplicas).
type vmLauncher struct {
	snapshot, models string
	mem              int
	bank             bool
	cpuPct           int // tope de CPU por VM (% de un núcleo); kindling pone 50 si no

	mu sync.Mutex // protege snapshot
}

// SetSnapshot cambia el snapshot desde el que se restauran las réplicas nuevas.
func (v *vmLauncher) SetSnapshot(name string) {
	v.mu.Lock()
	v.snapshot = name
	v.mu.Unlock()
}

func (v *vmLauncher) snap() string {
	v.mu.Lock()
	defer v.mu.Unlock()
	return v.snapshot
}

func (v *vmLauncher) Name() string { return "microvm" }
func (v *vmLauncher) MemMiB() int  { return v.mem }
func (v *vmLauncher) VCPUs() int   { return 1 }

func vmName(id string) string { return "arena-" + id }

func (v *vmLauncher) Start(ctx context.Context, r *replica) (string, error) {
	name := vmName(r.id)
	kling(ctx, "rm", name) // restos de una vida anterior
	args := []string{"run", "-from", v.snap(), "-name", name, "-label", "app=chispa-arena"}
	if v.cpuPct > 0 {
		args = append(args, "-cpu-pct", fmt.Sprint(v.cpuPct))
	}
	if _, err := kling(ctx, args...); err != nil {
		return "", err
	}
	ip, err := klingIP(ctx, name)
	if err != nil {
		return "", err
	}
	base := fmt.Sprintf("http://%s:%d", ip, DetPort)
	if err := v.configure(ctx, r, base); err != nil {
		return "", err
	}
	return base, nil
}

func (v *vmLauncher) configure(ctx context.Context, r *replica, base string) error {
	return v.configureWith(ctx, r, base, v.bank)
}

func (v *vmLauncher) configureWith(ctx context.Context, r *replica, base string, fromBank bool) error {
	var model []byte
	if r.kind != detectors.KindRules && !fromBank {
		b, err := os.ReadFile(detectors.ModelPath(v.models, r.dim, r.kind))
		if err != nil {
			return err
		}
		model = b
	}
	c := detsrv.NewClient(base)
	var err error
	for i := 0; i < 100; i++ { // el proceso viene vivo del snapshot; reintento corto
		if err = c.Configure(ctx, r.id, r.dim, r.kind, model); err == nil {
			return nil
		}
		time.Sleep(20 * time.Millisecond)
	}
	return err
}

func (v *vmLauncher) Stop(r *replica) error {
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	_, err := kling(ctx, "rm", vmName(r.id))
	return err
}

// Reload empuja el modelo promocionado a la microVM, sin reiniciarla. Va
// siempre con los bytes (copia privada): en modo banco el modelo nuevo no está
// en el snapshot viejo; el integrador reemplaza las réplicas desde el golden
// nuevo (SetSnapshot + Start) para recuperar el compartido.
func (v *vmLauncher) Reload(ctx context.Context, r *replica) error {
	return v.configureWith(ctx, r, r.client.Base, false)
}

// GoldenOpts configura la construcción del snapshot dorado.
type GoldenOpts struct {
	Image      string // rootfs (default "min")
	Name       string // nombre base (default "arena-det")
	Mem        int    // MiB por microVM (default 128)
	Bin        string // binario linux de arena (default: este)
	Models     string // directorio del banco; vacío = detector vacío sin banco
	Generation int    // generación del banco; >0 añade el snapshot <Name>-g<N>
}

// klingSave congela una microVM: `kling save` (v0.17+) y, si no existe,
// `kling commit`.
func klingSave(ctx context.Context, vm, snap string) error {
	if _, err := kling(ctx, "save", "-replace", vm, snap); err == nil {
		return nil
	}
	_, err := kling(ctx, "commit", "-replace", vm, snap)
	return err
}

// BuildGolden construye el snapshot dorado: una microVM con `arena detector`
// ya sirviendo en :9000 (con el banco de modelos cargado si opts.Models != "")
// congelada. Con Generation>0 deja <Name>-g<N> y también <Name> apuntando al
// último. Devuelve el nombre del snapshot específico (g<N> si lo hay).
func BuildGolden(ctx context.Context, opts GoldenOpts) (string, error) {
	if opts.Image == "" {
		opts.Image = "min"
	}
	if opts.Name == "" {
		opts.Name = "arena-det"
	}
	if opts.Mem == 0 {
		opts.Mem = 128
	}
	if opts.Bin == "" {
		exe, err := os.Executable()
		if err != nil {
			return "", err
		}
		opts.Bin = exe
	}
	tmp := "arena-golden"
	kling(ctx, "rm", tmp)
	if _, err := kling(ctx, "run", "-image", opts.Image, "-name", tmp, "-mem", fmt.Sprint(opts.Mem), "-allow-exec"); err != nil {
		return "", err
	}
	defer kling(context.Background(), "rm", tmp)
	if _, err := kling(ctx, "cp", opts.Bin, tmp+":/arena"); err != nil {
		return "", err
	}
	start := fmt.Sprintf("chmod +x /arena; nohup /arena detector -addr 0.0.0.0:%d >/tmp/arena.log 2>&1 &", DetPort)
	if opts.Models != "" {
		files, err := filepath.Glob(filepath.Join(opts.Models, "*.chispa"))
		if err != nil || len(files) == 0 {
			return "", fmt.Errorf("sin modelos .chispa en %s", opts.Models)
		}
		if _, err := kling(ctx, "exec", tmp, "--", "sh", "-c", "mkdir -p /models"); err != nil {
			return "", err
		}
		for _, f := range files {
			if _, err := kling(ctx, "cp", f, tmp+":/models/"+filepath.Base(f)); err != nil {
				return "", err
			}
		}
		start = fmt.Sprintf("chmod +x /arena; nohup /arena detector -bank /models -generation %d -addr 0.0.0.0:%d >/tmp/arena.log 2>&1 &",
			opts.Generation, DetPort)
	}
	if _, err := kling(ctx, "exec", tmp, "--", "sh", "-c", start); err != nil {
		return "", err
	}
	ip, err := klingIP(ctx, tmp)
	if err != nil {
		return "", err
	}
	url := fmt.Sprintf("http://%s:%d/health", ip, DetPort)
	ok := false
	for i := 0; i < 100 && !ok; i++ {
		if res, err := http.Get(url); err == nil {
			res.Body.Close()
			ok = res.StatusCode == 200
		}
		time.Sleep(100 * time.Millisecond)
	}
	if !ok {
		out, _ := kling(ctx, "exec", tmp, "--", "cat", "/tmp/arena.log")
		return "", fmt.Errorf("el detector no contestó en %s: %s", url, out)
	}
	snap := opts.Name
	if opts.Generation > 0 {
		snap = fmt.Sprintf("%s-g%d", opts.Name, opts.Generation)
	}
	if err := klingSave(ctx, tmp, snap); err != nil {
		return "", err
	}
	if snap != opts.Name {
		if err := klingSave(ctx, tmp, opts.Name); err != nil {
			return "", err
		}
	}
	return snap, nil
}

// golden es el subcomando `arena golden`.
func golden(args []string) error {
	fs := flag.NewFlagSet("golden", flag.ExitOnError)
	o := GoldenOpts{}
	fs.StringVar(&o.Image, "image", "min", "rootfs image")
	fs.StringVar(&o.Name, "name", "arena-det", "snapshot name")
	fs.IntVar(&o.Mem, "mem", 128, "MiB per microVM")
	fs.StringVar(&o.Bin, "bin", "", "linux arena binary to copy (default: this one)")
	fs.StringVar(&o.Models, "models", "", "model bank dir to bake into the snapshot (shared weights)")
	fs.IntVar(&o.Generation, "generation", 0, "bank generation (>0 also saves <name>-g<N>)")
	fs.Parse(args)
	snap, err := BuildGolden(context.Background(), o)
	if err != nil {
		return err
	}
	fmt.Printf("snapshot %s listo (detector vivo en :%d dentro)\n", snap, DetPort)
	return nil
}

// startVON restaura una réplica VON y devuelve su URL OpenAI-compatible.
func startVON(ctx context.Context, snapshot string) (string, func(), error) {
	name := "arena-von"
	kling(ctx, "rm", name)
	if _, err := kling(ctx, "run", "-from", snapshot, "-name", name, "-label", "app=chispa-arena"); err != nil {
		return "", nil, err
	}
	ip, err := klingIP(ctx, name)
	if err != nil {
		return "", nil, err
	}
	stop := func() {
		c, cancel := context.WithTimeout(context.Background(), 20*time.Second)
		defer cancel()
		kling(c, "rm", name)
	}
	return fmt.Sprintf("http://%s:8000", ip), stop, nil
}
