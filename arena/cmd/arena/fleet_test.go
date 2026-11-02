package main

import (
	"context"
	"os"
	"path/filepath"
	"os/exec"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"testing"
	"time"
)

func TestDrainLinesToleraMenorDeUnMiB(t *testing.T) {
	long := strings.Repeat("x", 100<<10)
	var got []string
	drainLines(strings.NewReader(long+"\nfin\n"), func(s string) { got = append(got, s) })
	if len(got) != 2 || len(got[0]) != len(long) || got[1] != "fin" {
		t.Fatalf("línea de 100 KiB perdida: %d líneas", len(got))
	}
}

func TestDrainLinesVaciaTuberiaTrasLineaEnorme(t *testing.T) {
	// Una línea >1 MiB no debe dejar la tubería sin leer (bloquearía al hijo).
	cmd := exec.Command("sh", "-c", "head -c 3000000 /dev/zero | tr '\\0' x; echo; echo fin")
	out, _ := cmd.StdoutPipe()
	if err := cmd.Start(); err != nil {
		t.Fatal(err)
	}
	done := make(chan struct{})
	go func() { drainLines(out, func(string) {}); close(done) }()
	select {
	case <-done:
	case <-time.After(10 * time.Second):
		t.Fatal("la tubería no se vació")
	}
	cmd.Wait()
}

func TestDrainLinesSigueTrasLineaDeDosMiB(t *testing.T) {
	var got []string
	in := "a\n" + strings.Repeat("x", 2<<20) + "\nLISTEN 127.0.0.1:1\nb\n"
	drainLines(strings.NewReader(in), func(s string) { got = append(got, s) })
	if len(got) != 4 || got[0] != "a" || len(got[1]) != 1<<20 || got[2] != "LISTEN 127.0.0.1:1" || got[3] != "b" {
		t.Fatalf("líneas tras la larga perdidas: %d", len(got))
	}
}

func TestStopNoMataTrasRecoger(t *testing.T) {
	// Tras reap() el líder está recogido: Stop no debe enviar señales al pgid.
	cmd := exec.Command("true")
	cmd.SysProcAttr = sysProcAttr()
	if err := cmd.Start(); err != nil {
		t.Fatal(err)
	}
	h := &procHandle{cmd: cmd, log: &procLog{}, done: make(chan struct{})}
	h.reap()
	if !h.reaped {
		t.Fatal("reap no marcó reaped")
	}
	// done sin cerrar: solo el indicador bajo cerrojo impide el Kill (si matara, esperaría 2 s).
	start := time.Now()
	(&procLauncher{}).Stop(&replica{handle: h})
	if time.Since(start) > time.Second {
		t.Fatal("Stop intentó matar un hijo ya recogido")
	}
}

func TestStopNoMataSiYaTermino(t *testing.T) {
	// Un sleep en su propio grupo; marcamos done sin matarlo: Stop no debe tocarlo.
	cmd := exec.Command("sleep", "30")
	cmd.SysProcAttr = sysProcAttr()
	if err := cmd.Start(); err != nil {
		t.Fatal(err)
	}
	exited := make(chan struct{})
	go func() { cmd.Wait(); close(exited) }()
	defer func() { cmd.Process.Kill(); <-exited }()
	h := &procHandle{cmd: cmd, log: &procLog{}, done: make(chan struct{})}
	close(h.done)
	h.reaped = true
	if err := (&procLauncher{}).Stop(&replica{handle: h}); err != nil {
		t.Fatal(err)
	}
	select {
	case <-exited:
		t.Fatal("Stop mató un grupo cuyo líder ya estaba recogido")
	case <-time.After(500 * time.Millisecond):
	}
}

// Un nieto que hereda las tuberías y sobrevive al líder no impide recoger al líder
// ni que Start vea «salió»; done se cierra cuando el nieto suelta las tuberías.
func TestVigilarRecogeAlLiderConNietoVivo(t *testing.T) {
	cmd := exec.Command("sh", "-c", "sleep 30 & echo $! ; exit 0")
	cmd.SysProcAttr = sysProcAttr()
	out, err := cmd.StdoutPipe()
	if err != nil {
		t.Fatal(err)
	}
	if err := cmd.Start(); err != nil {
		t.Fatal(err)
	}
	h := &procHandle{cmd: cmd, log: &procLog{}, done: make(chan struct{}), salio: make(chan struct{})}
	var rd sync.WaitGroup
	rd.Add(1)
	nieto := make(chan string, 1)
	go func() { defer rd.Done(); drainLines(out, func(l string) { nieto <- l }) }()
	h.vigilar(&rd)
	select {
	case <-h.salio:
	case <-time.After(3 * time.Second):
		t.Fatal("el líder no se recogió con el nieto vivo")
	}
	select {
	case <-h.done:
		t.Fatal("done se cerró con las tuberías aún abiertas")
	default:
	}
	pid, _ := strconv.Atoi(strings.TrimSpace(<-nieto))
	if pid > 0 {
		syscall.Kill(pid, syscall.SIGKILL)
	}
	select {
	case <-h.done:
	case <-time.After(3 * time.Second):
		t.Fatal("done no se cerró al soltar el nieto las tuberías")
	}
}

// Si el detector sale antes de escuchar, el error cita la última línea de su stderr (los lectores ya vaciaron la tubería).
func TestStartCitaUltimaLineaDeStderr(t *testing.T) {
	exe := filepath.Join(t.TempDir(), "falso.sh")
	script := "#!/bin/sh\nhead -c 500000 /dev/zero | tr '\\0' x >&2\necho >&2; echo ULTIMA-LINEA >&2\nexit 3\n"
	if err := os.WriteFile(exe, []byte(script), 0o755); err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 5; i++ {
		_, err := (&procLauncher{exe: exe}).Start(context.Background(), &replica{id: "r1"})
		if err == nil || !strings.Contains(err.Error(), "ULTIMA-LINEA") {
			t.Fatalf("el error no cita la última línea de stderr: %v", err)
		}
	}
}
