//go:build linux

package main

import (
	"bufio"
	"context"
	"os"
	"os/exec"
	"regexp"
	"strconv"
	"strings"
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
	b, err := os.ReadFile("/proc/" + strconv.Itoa(pid) + "/smaps_rollup")
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
