package dataset

import (
	"bufio"
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"testing"

	"github.com/juan52878911/chispa/contracts"
)

func TestGenerate(t *testing.T) {
	d1, d2 := t.TempDir(), t.TempDir()
	st, err := Generate(d1, 7)
	if err != nil {
		t.Fatal(err)
	}
	st2, err := Generate(d2, 7)
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(st, st2) {
		t.Fatal("stats no deterministas")
	}
	for dim, labels := range contracts.Dimensions {
		tplSplit := map[string]string{}
		ids := map[string]bool{}
		for _, l := range labels {
			tot := 0
			for _, sp := range []string{"train", "valid", "test"} {
				n := st.Counts[dim][sp][l]
				if n == 0 {
					t.Errorf("%s/%s sin ejemplos en %s", dim, l, sp)
				}
				tot += n
			}
			if tot < 400 {
				t.Errorf("%s/%s: %d < 400", dim, l, tot)
			}
		}
		for _, sp := range []string{"train", "valid", "test"} {
			p := filepath.Join(dim, sp+".jsonl")
			a, _ := os.ReadFile(filepath.Join(d1, p))
			b, _ := os.ReadFile(filepath.Join(d2, p))
			if string(a) != string(b) || len(a) == 0 {
				t.Fatalf("%s no determinista o vacío", p)
			}
			f, _ := os.Open(filepath.Join(d1, p))
			sc := bufio.NewScanner(f)
			for sc.Scan() {
				var e contracts.Example
				if err := json.Unmarshal(sc.Bytes(), &e); err != nil {
					t.Fatal(err)
				}
				if ids[e.ID] {
					t.Fatalf("id duplicado %s", e.ID)
				}
				ids[e.ID] = true
				if prev, ok := tplSplit[e.Template]; ok && prev != sp {
					t.Fatalf("plantilla %s en %s y %s", e.Template, prev, sp)
				}
				tplSplit[e.Template] = sp
			}
			f.Close()
		}
	}
	if len(BenignPool()) < 150 {
		t.Fatal("pool pequeño")
	}
}
