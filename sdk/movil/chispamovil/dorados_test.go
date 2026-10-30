package chispamovil

import (
	"encoding/binary"
	"encoding/json"
	"hash/fnv"
	"math"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"sync"
	"testing"
)

// Conjunto dorado común, generado por el servidor amd64 (server/decide: go test ./decide -run Dorados -regenerar): aquí se comprueba
// que chispamovil da lo mismo con L0, L0TF, L1 y L2 (la parte que no es ONNX), en los cuatro tipos. La cascada con L3 falso solo
// existe en el servidor. Tolerancias: docs/07-rendimiento-y-limites.md (Determinismo).
const dirDorados = "../../../server/decide/testdata/dorados/"

// tolDoradoMovil: máxima diferencia absoluta admitida en probs y conf frente al servidor amd64.
// Medido: 0 (bit a bit) en amd64; en otras arquitecturas el FMA de Go puede mover el último bit, de ahí 1e-9.
const tolDoradoMovil = 1e-9

type peticionDorada struct {
	ID       string `json:"id"`
	Fichero  string `json:"fichero"`
	Capa     string `json:"capa"`
	Estado   string `json:"estado"`
	Pregunta string `json:"question"`
	Kind     string `json:"kind"`
	Opciones []struct {
		ID          string `json:"id"`
		Description string `json:"description,omitempty"`
	} `json:"options"`
}

type esperadoDorado struct {
	Opina   bool               `json:"opina"`
	Answer  string             `json:"answer"`
	Answers []string           `json:"answers"`
	Conf    float64            `json:"conf"`
	Probs   map[string]float64 `json:"probs"`
}

func (p peticionDorada) json() string {
	b, _ := json.Marshal(map[string]any{"question": p.Pregunta, "kind": p.Kind, "options": p.Opciones})
	return string(b)
}

// Las ranuras S del «ONNX» de L2 y las torres son funciones deterministas del texto (las mismas fórmulas que server/decide/dorados_test.go).
func dorRanuras(texto string) []byte {
	h := fnv.New64a()
	h.Write([]byte(texto))
	s := h.Sum64()
	ids := make([]int64, 4)
	for i := range ids {
		ids[i] = int64(s >> (16 * i) & 0xffff)
	}
	var b []byte
	for k := 0; k < 2; k++ {
		for j := 0; j < 4; j++ {
			b = binary.LittleEndian.AppendUint32(b, math.Float32bits(float32(ids[(2*k+j)%4]%257-128)/64))
		}
	}
	return b
}

func dorTorre(texto string) []byte {
	h := fnv.New64a()
	h.Write([]byte(texto))
	s := h.Sum64()
	var b []byte
	for i := 0; i < 4; i++ {
		b = binary.LittleEndian.AppendUint32(b, math.Float32bits(float32(int64(s>>(8*i)&0xff)-128)/64))
	}
	return b
}

type respDorada struct {
	Ok      bool               `json:"ok"`
	Opina   bool               `json:"opina"`
	Answer  string             `json:"answer"`
	Answers []string           `json:"answers"`
	Conf    float64            `json:"conf"`
	Probs   map[string]float64 `json:"probs"`
	Error   string             `json:"error"`
}

func decidirDorada(t testing.TB, c *Chispa, p peticionDorada) respDorada {
	var s string
	switch p.Capa {
	case "L0":
		s = c.DecidirL0(p.Estado, p.json())
	case "L1":
		s = c.Decidir(p.Estado, p.json())
	case "L2":
		var tors []byte
		var textos []string
		if err := json.Unmarshal([]byte(c.TextosTorreL2(p.json())), &textos); err != nil {
			t.Fatal(err)
		}
		for _, x := range textos {
			tors = append(tors, dorTorre(x)...)
		}
		if len(textos) > 0 && !c.InstalarTorresL2(p.json(), tors, len(textos)) {
			t.Fatalf("%s: InstalarTorresL2", p.ID)
		}
		s = c.PuntuarL2(p.json(), dorRanuras(p.Estado), 2)
	default:
		t.Fatalf("capa %q", p.Capa)
	}
	var r respDorada
	if err := json.Unmarshal([]byte(s), &r); err != nil {
		t.Fatalf("%s: %v (%s)", p.ID, err, s)
	}
	if !r.Ok {
		t.Fatalf("%s: %s", p.ID, s)
	}
	return r
}

func nulo(s []string) []string {
	if len(s) == 0 {
		return nil
	}
	return s
}

// compara devuelve la diferencia máxima y un texto si no coincide.
func comparaDorada(g respDorada, w esperadoDorado) (float64, string) {
	if g.Opina != w.Opina || g.Answer != w.Answer || !reflect.DeepEqual(nulo(g.Answers), nulo(w.Answers)) {
		return 0, "móvil " + string(mustB(g)) + " ≠ dorado " + string(mustB(w))
	}
	if !g.Opina {
		return 0, ""
	}
	peor := math.Abs(g.Conf - w.Conf)
	if len(g.Probs) != len(w.Probs) {
		return peor, "probs distintas"
	}
	for k, v := range w.Probs {
		x, ok := g.Probs[k]
		if !ok {
			return peor, "falta la prob de " + k
		}
		peor = math.Max(peor, math.Abs(x-v))
	}
	if peor > tolDoradoMovil {
		return peor, "diferencia máxima mayor que la tolerancia"
	}
	return peor, ""
}

func mustB(v any) []byte { b, _ := json.Marshal(v); return b }

func cargarDorados(t testing.TB) (ps []peticionDorada, sol struct {
	Capas map[string]esperadoDorado `json:"capas"`
}) {
	for n, v := range map[string]any{"peticiones.json": &ps, "esperado.json": &sol} {
		b, err := os.ReadFile(dirDorados + n)
		if err != nil {
			t.Fatal(err)
		}
		if err := json.Unmarshal(b, v); err != nil {
			t.Fatal(err)
		}
	}
	return
}

func abrirDorados(t testing.TB) map[string]*Chispa {
	m := map[string]*Chispa{}
	for _, f := range []string{"l0l1.chispa", "l0tf.chispa", "l2.chispa"} {
		c, err := Abrir(filepath.Join(dirDorados, f))
		if err != nil {
			t.Fatal(err)
		}
		if tt, ok := t.(*testing.T); ok {
			tt.Cleanup(func() { c.Cerrar() })
		}
		if c.Avisos() != "" {
			t.Fatalf("%s: avisos %q", f, c.Avisos())
		}
		m[f] = c
	}
	return m
}

func TestDorados(t *testing.T) {
	ps, sol := cargarDorados(t)
	cs := abrirDorados(t)
	var n int
	var peor float64
	opinan := map[string]int{}
	for _, p := range ps {
		if p.Capa == "cascada" {
			continue
		}
		n++
		g := decidirDorada(t, cs[p.Fichero], p)
		d, msg := comparaDorada(g, sol.Capas[p.ID])
		if msg != "" {
			t.Errorf("%s: %s", p.ID, msg)
		}
		peor = math.Max(peor, d)
		if g.Opina {
			opinan[strings.TrimSuffix(p.Fichero, ".chispa")+"/"+p.Capa+"/"+p.Kind]++
		}
	}
	if len(opinan) < 10 {
		t.Errorf("el dorado no ejercita todas las capas y tipos: %v", opinan)
	}
	t.Logf("%d peticiones; opinan %v; |Δ| máxima frente al servidor amd64 %.3g (tolerancia %g)", n, opinan, peor, tolDoradoMovil)
}

// 64 goroutines sobre el mismo *Chispa (cachés de torres y de esquemas compartidas) dan lo mismo que una, bit a bit.
func TestDoradosConcurrencia(t *testing.T) {
	ps, _ := cargarDorados(t)
	var capa []peticionDorada
	for _, p := range ps {
		if p.Capa != "cascada" {
			capa = append(capa, p)
		}
	}
	ref := make([]string, len(capa))
	c1 := abrirDorados(t)
	for i, p := range capa {
		ref[i] = string(mustB(decidirDorada(t, c1[p.Fichero], p)))
	}
	cs := abrirDorados(t) // frío
	var wg sync.WaitGroup
	ini := make(chan struct{})
	mal := make(chan string, 64*len(capa)*2)
	for g := 0; g < 64; g++ {
		wg.Add(1)
		go func(g int) {
			defer wg.Done()
			<-ini
			for r := 0; r < 2; r++ {
				for k := range capa {
					i := (k + 5*g) % len(capa)
					if got := string(mustB(decidirDorada(t, cs[capa[i].Fichero], capa[i]))); got != ref[i] {
						mal <- capa[i].ID + ": " + got + " ≠ " + ref[i]
					}
				}
			}
		}(g)
	}
	close(ini)
	wg.Wait()
	close(mal)
	n := 0
	for m := range mal {
		if n++; n <= 5 {
			t.Error(m)
		}
	}
	if n > 0 {
		t.Fatalf("%d respuestas distintas de las de 1 goroutine", n)
	}
}
