package decide

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"sync/atomic"

	"github.com/juan52878911/kindling/pkg/chispa"
)

// L0 es el Chispa lineal. Carga uno o varios .chispa; para cada pregunta usa
// el modelo cuyo conjunto de etiquetas coincide con los ids de las opciones
// (un modelo por esquema). Sin modelo para el esquema, no opina.
type L0 struct {
	modelos []modelo
	cache   *LRU[*chispa.Model] // clave de esquema → modelo (nil = sin modelo)
	Hits    atomic.Uint64
	Misses  atomic.Uint64
}

type modelo struct {
	nombre string
	firma  string
	m      *chispa.Model
}

func firma(ids []string) string {
	s := append([]string(nil), ids...)
	sort.Strings(s)
	return strings.Join(s, "\x00")
}

func NuevoL0(cacheEsquemas int) *L0 {
	return &L0{cache: NewLRU[*chispa.Model](cacheEsquemas)}
}

// Anadir registra un modelo ya cargado.
func (l *L0) Anadir(nombre string, m *chispa.Model) error {
	f := firma(m.Labels)
	for _, x := range l.modelos {
		if x.firma == f {
			return fmt.Errorf("L0: %s y %s tienen las mismas etiquetas %v", x.nombre, nombre, m.Labels)
		}
	}
	l.modelos = append(l.modelos, modelo{nombre, f, m})
	return nil
}

// Cargar lee ficheros .chispa.
func (l *L0) Cargar(paths ...string) error {
	for _, p := range paths {
		m, err := chispa.LoadFile(p)
		if err != nil {
			return fmt.Errorf("L0: %s: %w", p, err)
		}
		if err := l.Anadir(p, m); err != nil {
			return err
		}
	}
	return nil
}

func (l *L0) Nombre() string { return "L0" }

func (l *L0) NumModelos() int { return len(l.modelos) }

func (l *L0) buscar(p Pregunta) *chispa.Model {
	k := ClaveEsquema(p)
	if m, ok := l.cache.Get(k); ok {
		l.Hits.Add(1)
		return m
	}
	l.Misses.Add(1)
	ids := make([]string, len(p.Opciones))
	for i, o := range p.Opciones {
		ids[i] = o.ID
	}
	f := firma(ids)
	var found *chispa.Model
	for _, x := range l.modelos {
		if x.firma == f {
			found = x.m
			break
		}
	}
	l.cache.Put(k, found)
	return found
}

func (l *L0) Decidir(ctx context.Context, p Pregunta) (Respuesta, error) {
	m := l.buscar(p)
	if m == nil {
		return Respuesta{}, nil
	}
	pred := m.PredictFull(chispa.Input{Text: p.Estado}, 0)
	probs := make(map[string]float64, len(pred.Probs))
	for _, cp := range pred.Probs {
		probs[cp.Label] = cp.Prob
	}
	return Respuesta{Answer: pred.Label, Probs: probs, Conf: pred.Prob}, nil
}
