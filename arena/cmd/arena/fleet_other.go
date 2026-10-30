//go:build !linux

package main

import "syscall"

// sysProcAttr: grupo propio (sin Pdeathsig, que solo existe en Linux).
func sysProcAttr() *syscall.SysProcAttr {
	return &syscall.SysProcAttr{Setpgid: true}
}
