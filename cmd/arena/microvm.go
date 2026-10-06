package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"strings"
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
// (`kling run -from`). El detector arranca vacío y recibe su modelo por HTTP.
type vmLauncher struct {
	snapshot, models string
	mem              int
}

func (v *vmLauncher) Name() string { return "microvm" }
func (v *vmLauncher) MemMiB() int  { return v.mem }
func (v *vmLauncher) VCPUs() int   { return 1 }

func vmName(id string) string { return "arena-" + id }

func (v *vmLauncher) Start(ctx context.Context, r *replica) (string, error) {
	name := vmName(r.id)
	kling(ctx, "rm", name) // restos de una vida anterior
	if _, err := kling(ctx, "run", "-from", v.snapshot, "-name", name, "-label", "app=chispa-arena"); err != nil {
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
	var model []byte
	if r.kind != detectors.KindRules {
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

// Reload empuja el modelo promocionado a la microVM, sin reiniciarla.
func (v *vmLauncher) Reload(ctx context.Context, r *replica) error {
	return v.configure(ctx, r, r.client.Base)
}

// golden construye el snapshot dorado del detector: una microVM con el binario
// `arena` ya sirviendo en :9000, congelada con `kling commit`.
func golden(args []string) error {
	fs := flag.NewFlagSet("golden", flag.ExitOnError)
	image := fs.String("image", "min", "rootfs image")
	name := fs.String("name", "arena-det", "snapshot name")
	mem := fs.Int("mem", 128, "MiB per microVM")
	bin := fs.String("bin", "", "linux arena binary to copy (default: this one)")
	fs.Parse(args)
	ctx := context.Background()
	if *bin == "" {
		exe, err := os.Executable()
		if err != nil {
			return err
		}
		*bin = exe
	}
	tmp := "arena-golden"
	kling(ctx, "rm", tmp)
	if _, err := kling(ctx, "run", "-image", *image, "-name", tmp, "-mem", fmt.Sprint(*mem), "-allow-exec"); err != nil {
		return err
	}
	defer kling(ctx, "rm", tmp)
	if _, err := kling(ctx, "cp", *bin, tmp+":/arena"); err != nil {
		return err
	}
	start := fmt.Sprintf("chmod +x /arena; nohup /arena detector -addr 0.0.0.0:%d >/tmp/arena.log 2>&1 &", DetPort)
	if _, err := kling(ctx, "exec", tmp, "--", "sh", "-c", start); err != nil {
		return err
	}
	ip, err := klingIP(ctx, tmp)
	if err != nil {
		return err
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
		return fmt.Errorf("el detector no contestó en %s: %s", url, out)
	}
	if _, err := kling(ctx, "commit", "-replace", tmp, *name); err != nil {
		return err
	}
	fmt.Printf("snapshot %s listo (detector vivo en :%d dentro)\n", *name, DetPort)
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
