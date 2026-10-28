package decide

import "context"

// Stub es una capa sin modelo: siempre «sin opinión» (confianza 0). Se
// sustituye por el decisor real cuando llegue el modelo.
type Stub struct{ N string }

func (s Stub) Nombre() string { return s.N }

func (Stub) Decidir(context.Context, Pregunta) (Respuesta, error) { return Respuesta{}, nil }

func NuevoL1() Decisor { return Stub{"L1"} }
func NuevoL2() Decisor { return Stub{"L2"} }
func NuevoL3() Decisor { return Stub{"L3"} }
