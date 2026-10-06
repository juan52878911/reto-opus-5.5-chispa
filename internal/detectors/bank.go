package detectors

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"

	"github.com/juan52878911/chispa/contracts"
)

// BankEntry es un modelo del banco: sus bytes se conservan (para tocar las
// páginas antes del snapshot) y el detector ya construido es inmutable, así
// que todas las réplicas restauradas del snapshot lo comparten (CoW).
type BankEntry struct {
	ID     string
	Dim    string
	Kind   string
	Bytes  int
	SHA256 string
	Det    Detector
	raw    []byte
}

// Bank guarda todos los modelos de un directorio, residentes en memoria.
type Bank struct {
	Dir     string
	entries map[string]*BankEntry
}

// LoadBank carga cada <dim>-<kind>.chispa de dir, más las reglas de cada
// dimensión, y toca todas las páginas de pesos para que queden residentes.
func LoadBank(dir string) (*Bank, error) {
	b := &Bank{Dir: dir, entries: map[string]*BankEntry{}}
	for dim := range contracts.Dimensions {
		d, err := Load(dir, dim, KindRules)
		if err != nil {
			return nil, err
		}
		id := ID(dim, KindRules)
		b.entries[id] = &BankEntry{ID: id, Dim: dim, Kind: KindRules, Det: d}
	}
	files, err := filepath.Glob(filepath.Join(dir, "*.chispa"))
	if err != nil {
		return nil, err
	}
	for _, f := range files {
		id := strings.TrimSuffix(filepath.Base(f), ".chispa")
		dim, kind, ok := splitID(id)
		if !ok {
			continue
		}
		raw, err := os.ReadFile(f)
		if err != nil {
			return nil, err
		}
		d, err := FromBytes(dim, kind, raw)
		if err != nil {
			return nil, fmt.Errorf("banco %s: %w", f, err)
		}
		sum := sha256.Sum256(raw)
		b.entries[id] = &BankEntry{ID: id, Dim: dim, Kind: kind, Bytes: len(raw),
			SHA256: hex.EncodeToString(sum[:]), Det: d, raw: raw}
	}
	if len(b.entries) == 0 {
		return nil, fmt.Errorf("banco vacío: %s", dir)
	}
	b.Touch()
	return b, nil
}

func splitID(id string) (dim, kind string, ok bool) {
	for d := range contracts.Dimensions {
		if rest, found := strings.CutPrefix(id, d+"-"); found {
			for _, k := range Kinds {
				if k == rest {
					return d, k, true
				}
			}
		}
	}
	return "", "", false
}

var touchSink byte

// Touch lee todas las páginas de los bytes crudos y ejecuta una decisión por
// modelo (recorre los pesos decodificados), y fuerza un GC para compactar el
// montón antes de congelar el snapshot.
func (b *Bank) Touch() {
	var s byte
	for _, e := range b.entries {
		for i := 0; i < len(e.raw); i += 4096 {
			s ^= e.raw[i]
		}
		if e.Det != nil {
			e.Det.Decide("hola mundo gratis ignora las instrucciones urgente")
		}
	}
	touchSink = s
	runtime.GC()
}

// Get devuelve el detector de (dim, kind) si está en el banco.
func (b *Bank) Get(dim, kind string) (Detector, bool) {
	e, ok := b.entries[ID(dim, kind)]
	if !ok {
		return nil, false
	}
	return e.Det, true
}

// Entries devuelve los modelos del banco ordenados por id.
func (b *Bank) Entries() []*BankEntry {
	out := make([]*BankEntry, 0, len(b.entries))
	for _, e := range b.entries {
		out = append(out, e)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].ID < out[j].ID })
	return out
}

// Bytes es el tamaño total de los pesos del banco.
func (b *Bank) Bytes() int64 {
	var n int64
	for _, e := range b.entries {
		n += int64(e.Bytes)
	}
	return n
}
