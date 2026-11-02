package tok

import "strconv"

// NivelesScore devuelve los ids de un score ordenados por nivel ("1".."K") y ok=true solo si son exactamente 1..K: enteros
// canónicos (strconv.Itoa(n) == id: sin «01» ni «+1»), sin huecos ni repetidos, en cualquier orden. Con cualquier otro conjunto
// devuelve nil, false: la capa no opina y la cascada escala. No modifica ids.
func NivelesScore(ids []string) ([]string, bool) {
	k := len(ids)
	if k == 0 {
		return nil, false
	}
	out := make([]string, k)
	for _, id := range ids {
		n, err := strconv.Atoi(id)
		if err != nil || strconv.Itoa(n) != id || n < 1 || n > k || out[n-1] != "" {
			return nil, false
		}
		out[n-1] = id
	}
	return out, true
}
