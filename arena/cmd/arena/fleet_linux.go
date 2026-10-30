//go:build linux

package main

import "syscall"

// sysProcAttr: grupo propio y muerte del hijo con el padre.
func sysProcAttr() *syscall.SysProcAttr {
	return &syscall.SysProcAttr{Setpgid: true, Pdeathsig: syscall.SIGKILL}
}
