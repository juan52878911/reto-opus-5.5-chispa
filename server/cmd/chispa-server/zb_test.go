package main

import (
	"strings"
	"testing"

	"github.com/juan52878911/chispa/server/decide"
)

// ZB-4: la línea de arranque (y la de recarga, que usa la misma) nombra el motivo de la torre al vuelo desactivada.
func TestZBResumenCapasMotivoTorre(t *testing.T) {
	cp := decide.Capacidades{Capas: map[string]bool{"L1": true, "L2": true}, TorreAlVueloMotivo: "texto_torre_inconsistente"}
	msg := resumenCapas(0, cp)
	if !strings.Contains(msg, "torre al vuelo desactivada (texto_torre_inconsistente)") {
		t.Fatal(msg)
	}
	if msg := resumenCapas(0, decide.Capacidades{Capas: map[string]bool{"L1": true}}); strings.Contains(msg, "desactivada") {
		t.Fatal(msg)
	}
}
