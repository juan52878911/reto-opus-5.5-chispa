package nucleo

import "testing"

// reps < 1 debe ser un error, no un pánico (en wasm un pánico mata el runtime de Go).
func TestMedirRepsInvalidas(t *testing.T) {
	for _, reps := range []int{0, -1} {
		if _, err := (&Demo{}).Medir(10, reps, `{}`); err == nil {
			t.Errorf("reps=%d: se esperaba error", reps)
		}
	}
}
