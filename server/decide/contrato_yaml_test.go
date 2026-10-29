package decide

import (
	"encoding/json"
	"os"
	"os/exec"
	"reflect"
	"strings"
	"testing"
)

// pythonYAML devuelve un intérprete con PyYAML (CHISPA_PYTHON, el venv del orquestador o python3), o "".
func pythonYAML() string {
	cands := []string{os.Getenv("CHISPA_PYTHON"), os.ExpandEnv("$HOME/orquestador/herr/venv/bin/python"), "python3"}
	for _, c := range cands {
		if c == "" {
			continue
		}
		if exec.Command(c, "-c", "import yaml").Run() == nil {
			return c
		}
	}
	return ""
}

// El fichero tiene que ser YAML de verdad (no solo lo que lee el lector mínimo de los tests): se parsea con PyYAML y el
// resultado debe coincidir con el del lector mínimo, así que los dos entienden igual las cadenas entre comillas con escapes.
func TestOpenAPIEsYAMLValido(t *testing.T) {
	py := pythonYAML()
	if py == "" {
		t.Skip("sin PyYAML (CHISPA_PYTHON): el lector mínimo es lo único que valida el YAML")
	}
	out, err := exec.Command(py, "-I", "-c",
		"import sys,json,yaml; json.dump(yaml.safe_load(open(sys.argv[1],encoding='utf-8')), sys.stdout)", "../api/openapi.yaml").Output()
	if err != nil {
		t.Fatalf("openapi.yaml no es YAML válido: %v", err)
	}
	var real any
	if err := json.Unmarshal(out, &real); err != nil {
		t.Fatal(err)
	}
	src, err := os.ReadFile("../api/openapi.yaml")
	if err != nil {
		t.Fatal(err)
	}
	mini, err := leerYAML(string(src))
	if err != nil {
		t.Fatalf("el lector mínimo no lee openapi.yaml: %v", err)
	}
	// Normaliza a JSON para comparar (el lector mínimo da map[string]any/[]any/float64/bool/string).
	b, _ := json.Marshal(mini)
	var m any
	json.Unmarshal(b, &m)
	if !reflect.DeepEqual(real, m) {
		t.Errorf("PyYAML y el lector mínimo leen cosas distintas:\n%s", difiere("$", real, m))
	}
	if !strings.Contains(string(src), "multi") {
		t.Error("openapi.yaml sin multi")
	}
}

func difiere(at string, a, b any) string {
	switch x := a.(type) {
	case map[string]any:
		y, ok := b.(map[string]any)
		if !ok {
			return at + ": tipos distintos"
		}
		for k, v := range x {
			w, ok := y[k]
			if !ok {
				return at + "." + k + ": falta en el lector mínimo"
			}
			if d := difiere(at+"."+k, v, w); d != "" {
				return d
			}
		}
		for k := range y {
			if _, ok := x[k]; !ok {
				return at + "." + k + ": sobra en el lector mínimo"
			}
		}
	case []any:
		y, ok := b.([]any)
		if !ok || len(x) != len(y) {
			return at + ": listas distintas"
		}
		for i := range x {
			if d := difiere(at, x[i], y[i]); d != "" {
				return d
			}
		}
	default:
		if !reflect.DeepEqual(a, b) {
			return at + ": " + jsonS(a) + " ≠ " + jsonS(b)
		}
	}
	return ""
}

func jsonS(v any) string { b, _ := json.Marshal(v); return string(b) }
