package main

func hostMem() int64 {
	t, _ := meminfo()
	return t
}
