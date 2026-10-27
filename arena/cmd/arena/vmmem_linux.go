//go:build linux

package main

import (
	"bufio"
	"context"
	"encoding/json"
	"os"
	"os/exec"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"
)

var vmNameRe = regexp.MustCompile(`arena-[A-Za-z0-9_.-]+`)

// measureVMMem devuelve la memoria Pss (reparto justo con CoW) en bytes por
// microVM `arena-*`, leyendo /proc/<pid>/smaps_rollup de sus procesos firecracker.
func measureVMMem(ctx context.Context) (map[string]int64, error) {
	d, err := measureVMMemDetail(ctx)
	if err != nil {
		return nil, err
	}
	out := make(map[string]int64, len(d))
	for k, v := range d {
		out[k] = v.Pss
	}
	return out, nil
}

// measureVMMemDetail devuelve Pss y Rss por microVM.
func measureVMMemDetail(ctx context.Context) (map[string]VMMem, error) {
	ps, err := exec.CommandContext(ctx, "ps", "-eo", "pid,args").Output()
	if err != nil {
		return nil, err
	}
	out := map[string]VMMem{}
	sc := bufio.NewScanner(strings.NewReader(string(ps)))
	for sc.Scan() {
		f := strings.Fields(sc.Text())
		if len(f) < 2 {
			continue
		}
		pid, err := strconv.Atoi(f[0])
		if err != nil || !strings.Contains(f[1], "firecracker") {
			continue
		}
		args := strings.Join(f[1:], " ")
		name := vmNameRe.FindString(args)
		if name == "" {
			// Con jailer el proceso no lleva el nombre: se cruza por pid con
			// `kling ps -json`.
			name = pidToName(ctx, pid)
		}
		if name == "" {
			continue
		}
		m, err := readSmapsRollup(pid)
		if err != nil {
			continue // la VM murió entre ps y lectura
		}
		cur := out[name]
		cur.Pss += m.Pss
		cur.Rss += m.Rss
		out[name] = cur
	}
	return out, nil
}

func readSmapsRollup(pid int) (VMMem, error) {
	path := "/proc/" + strconv.Itoa(pid) + "/smaps_rollup"
	b, err := os.ReadFile(path)
	if err != nil {
		// firecracker corre como el usuario del daemon (kindling): sin permiso
		// directo, se lee con sudo no interactivo (Lima no pide contraseña).
		b, err = exec.Command("sudo", "-n", "cat", path).Output()
	}
	if err != nil {
		return VMMem{}, err
	}
	var m VMMem
	for _, ln := range strings.Split(string(b), "\n") {
		f := strings.Fields(ln)
		if len(f) < 2 {
			continue
		}
		kb, err := strconv.ParseInt(f[1], 10, 64)
		if err != nil {
			continue
		}
		switch f[0] {
		case "Pss:":
			m.Pss = kb * 1024
		case "Rss:":
			m.Rss = kb * 1024
		}
	}
	return m, nil
}

var (
	idNamesMu sync.Mutex
	idNames   = map[int]string{}
	idNamesAt time.Time
)

// pidToName traduce el pid de firecracker al nombre de la máquina con
// `kling ps -json` (cacheado unos segundos). Solo devuelve nombres arena-*.
func pidToName(ctx context.Context, pid int) string {
	idNamesMu.Lock()
	defer idNamesMu.Unlock()
	if time.Since(idNamesAt) > 5*time.Second {
		idNamesAt = time.Now()
		out, err := exec.CommandContext(ctx, "kling", "ps", "-json").Output()
		if err == nil {
			var ms []struct {
				PID  int    `json:"pid"`
				Name string `json:"name"`
			}
			if json.Unmarshal(out, &ms) == nil {
				idNames = map[int]string{}
				for _, m := range ms {
					idNames[m.PID] = m.Name
				}
			}
		}
	}
	n := idNames[pid]
	if !strings.HasPrefix(n, "arena-") {
		return ""
	}
	return n
}
