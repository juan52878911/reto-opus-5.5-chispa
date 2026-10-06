package main

import "github.com/juan52878911/chispa/contracts"

// fillSharing rellena el ahorro de memoria por compartir pesos. «Ingenuo» es
// lo que costaría si cada réplica tuviera su RAM de VM entera; «real» es la
// memoria usada medida (en Linux, la del host, que incluye el copy-on-write).
func fillSharing(m *contracts.Metrics, sc *scaler) {
	sh := &m.Flow.Sharing
	live := int64(m.Scale.LiveVMs)
	if live == 0 {
		return
	}
	sh.NaiveMemBytes = live * int64(m.Scale.VMMemMiB) << 20
	sh.RealMemBytes = sc.vmMem()
	if sh.RealMemBytes > 0 {
		sh.MemPerVMBytes = sh.RealMemBytes / live
		if sh.NaiveMemBytes > 0 {
			sh.SavedPct = 100 * (1 - float64(sh.RealMemBytes)/float64(sh.NaiveMemBytes))
		}
	}
}
