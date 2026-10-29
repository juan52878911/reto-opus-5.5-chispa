//go:build ort

package main

import (
	"fmt"
	"os"
	"os/exec"
	"strings"
	"testing"

	"chispa/format/chispa3"
	"github.com/juan52878911/chispa/server/decide"
	"github.com/juan52878911/chispa/server/torre"
)

type tokFijo struct{}

func (tokFijo) IDsPasaje(t string) []int64 { return []int64{0, 5, int64(len(t)) + 3, 2} }

// El entorno ORT se inicializa una vez por proceso: cada origen de la ruta se prueba en un proceso hijo (este mismo binario de test).
// El hijo resuelve la ruta como main, abre la torre sintética y calcula una torre: sin ruta válida no hay torre.
func TestRutaORTHija(t *testing.T) {
	if os.Getenv("CHISPA_HIJO_ORT") == "" {
		t.Skip("solo como proceso hijo")
	}
	if v := os.Getenv("CHISPA_HIJO_LDFLAGS"); v != "" {
		decide.RutaORT = v // lo que dejaría -ldflags -X …decide.RutaORT=
	}
	ruta, origen := fijarRutaORT(os.Getenv("CHISPA_HIJO_FLAG"))
	onnx, err := os.ReadFile("../../torre/testdata/sintetico.onnx")
	if err != nil {
		t.Fatal(err)
	}
	c, err := torre.Abrir(chispa3.Torre{Dim: 256, MaxLen: 128, Prefijo: "passage: ", ONNX: onnx}, tokFijo{})
	if err != nil {
		t.Fatalf("la torre no abre ORT con ruta %q (%s): %v", ruta, origen, err)
	}
	defer c.Close()
	calculadas := 0
	for _, txt := range []string{"a · b", "c · d"} {
		if h, err := c.Torre(txt); err != nil || len(h) != 256 {
			t.Fatalf("%v %d", err, len(h))
		}
		calculadas++
	}
	if decide.RutaORT != ruta || torre.RutaORT != ruta {
		t.Fatalf("decide %q torre %q ruta %q", decide.RutaORT, torre.RutaORT, ruta)
	}
	fmt.Printf("ORIGEN=%s CALCULADAS=%d\n", origen, calculadas)
}

func TestTorreCalculaConRutaPorCadaOrigen(t *testing.T) {
	lib := os.Getenv("CHISPA_ORT_LIB")
	if lib == "" {
		t.Skip("falta CHISPA_ORT_LIB (receta en server/README.md)")
	}
	casos := []struct{ nombre, flag, env, ldflags, origen string }{
		{"solo flag", lib, "", "", "-ort-lib"},
		{"solo variable", "", lib, "", "CHISPA_ORT_LIB"},
		{"solo ldflags", "", "", lib, "ldflags"},
		{"flag gana a variable y ldflags", lib, "/no/existe.so", "/tampoco.so", "-ort-lib"},
		{"variable gana a ldflags", "", lib, "/tampoco.so", "CHISPA_ORT_LIB"},
	}
	for _, c := range casos {
		t.Run(c.nombre, func(t *testing.T) {
			cmd := exec.Command(os.Args[0], "-test.run=^TestRutaORTHija$", "-test.v")
			env := []string{"CHISPA_HIJO_ORT=1", "CHISPA_HIJO_FLAG=" + c.flag, "CHISPA_HIJO_LDFLAGS=" + c.ldflags, "LD_LIBRARY_PATH="}
			for _, e := range os.Environ() {
				if !strings.HasPrefix(e, "CHISPA_ORT_LIB=") && !strings.HasPrefix(e, "LD_LIBRARY_PATH=") {
					env = append(env, e)
				}
			}
			if c.env != "" {
				env = append(env, "CHISPA_ORT_LIB="+c.env)
			}
			cmd.Env = env
			out, err := cmd.CombinedOutput()
			if err != nil || !strings.Contains(string(out), "ORIGEN="+c.origen+" CALCULADAS=2") {
				t.Fatalf("%v\n%s", err, out)
			}
		})
	}
}
