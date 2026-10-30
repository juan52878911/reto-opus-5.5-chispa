package tok

import (
	"sort"
	"strconv"
)

// IdsEnteros dice si todos los ids son enteros (y hay al menos uno).
func IdsEnteros(ids []string) bool {
	for _, id := range ids {
		if _, err := strconv.Atoi(id); err != nil {
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
