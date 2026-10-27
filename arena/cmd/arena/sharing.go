package main

import "github.com/juan52878911/chispa/contracts"

// fillSharing rellena el ahorro de memoria por compartir pesos. «Ingenuo» es
// lo que costaría si cada réplica tuviera su RAM de VM entera; «real» es la
// memoria usada medida (en Linux, la del host, que incluye el copy-on-write).
func fillSharing(m *contracts.Metrics, sc *scaler) {
	// DECISIÓN — en modo proceso no hay snapshot ni copy-on-write: no se
	// rellena nada. El ahorro solo se publica medido (PSS/RSS) en microVMs.
}
