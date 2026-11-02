package decide

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"chispa/format/chispa3"
)

func TestModelosConUnV3DiceQueEsperaOtraCosa(t *testing.T) {
	var buf bytes.Buffer
	if err := chispa3.Escribir(&buf, []chispa3.Seccion{{Tipo: chispa3.L1, Datos: make([]byte, 64)}}); err != nil {
		t.Fatal(err)
	}
	ruta := filepath.Join(t.TempDir(), "v3.chispa")
	if err := os.WriteFile(ruta, buf.Bytes(), 0o644); err != nil {
		t.Fatal(err)
	}
	err := NuevoL0(8).Cargar(ruta)
	if err == nil || !strings.Contains(err.Error(), "v3") || strings.Contains(err.Error(), "checksum") {
		t.Fatalf("quería error que nombre v3, salió %v", err)
	}
}
