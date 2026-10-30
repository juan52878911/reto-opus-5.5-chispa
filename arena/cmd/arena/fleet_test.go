package main

import (
	"os/exec"
	"strings"
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
	if err := (&procLauncher{}).Stop(&replica{handle: h}); err != nil {
		t.Fatal(err)
	}
	select {
	case <-exited:
		t.Fatal("Stop mató un grupo cuyo líder ya estaba recogido")
	case <-time.After(500 * time.Millisecond):
	}
}
