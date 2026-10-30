package tok

import (
	"sort"
	"strconv"
)

// EnteroCanonico devuelve el entero de id si está en forma canónica (strconv.Itoa(n) == id: sin «01» ni «+1»).
func EnteroCanonico(id string) (int, bool) {
	n, err := strconv.Atoi(id)
	return n, err == nil && strconv.Itoa(n) == id
}

// IdsEnteros dice si todos los ids son enteros canónicos (y hay al menos uno).
func IdsEnteros(ids []string) bool {
	for _, id := range ids {
		if _, ok := EnteroCanonico(id); !ok {
			return false
		}
	}
	return len(ids) > 0
}

// OrdenNivel devuelve los ids de un score ordenados por nivel: numérico y estable ("2" < "10") si todos son enteros; si alguno no
// lo es, el orden declarado sin tocarlo (nunca lexicográfico). No modifica ids.
func OrdenNivel(ids []string) []string {
	out := make([]string, len(ids))
	copy(out, ids)
	if !IdsEnteros(out) {
		return out
	}
	sort.SliceStable(out, func(i, j int) bool {
		a, _ := strconv.Atoi(out[i])
		b, _ := strconv.Atoi(out[j])
		return a < b
	})
	return out
}
