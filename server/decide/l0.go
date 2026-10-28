package decide

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"sync/atomic"

	"chispa/format/chispa3"
	"github.com/juan52878911/kindling/pkg/chispa"
)

// L0 es el Chispa lineal. Carga uno o varios .chispa; para cada pregunta usa
// el modelo cuyo conjunto de etiquetas coincide con los ids de las opciones
// (un modelo por esquema). Sin modelo para el esquema, no opina.
// Un modelo puede ser el Chispa de kindling o el TF-IDF de caracteres de la sección L0TF (T4.5c).
type L0 struct {
	modelos []modelo
	cache   *LRU[*modelo] // clave de esquema → modelo (nil = sin modelo)
	Hits    atomic.Uint64
	Misses  atomic.Uint64
}

type modelo struct {
	nombre string
	firma  string
	m      *chispa.Model       // el Chispa de kindling, o
	tf     *chispa3.L0TFModelo // el TF-IDF de caracteres (el que manda si el .chispa trae L0TF)
}

func firma(ids []string) string {
	s := append([]string(nil), ids...)
	sort.Strings(s)
	return strings.Join(s, "\x00")
}

func NuevoL0(cacheEsquemas int) *L0 {
	return &L0{cache: NewLRU[*modelo](cacheEsquemas)}
}

// Anadir registra un modelo ya cargado.
func (l *L0) Anadir(nombre string, m *chispa.Model) error {
	f := firma(m.Labels)
	for _, x := range l.modelos {
		if x.firma == f {
			return fmt.Errorf("L0: %s y %s tienen las mismas etiquetas %v", x.nombre, nombre, m.Labels)
		}
	}
	l.modelos = append(l.modelos, modelo{nombre: nombre, firma: f, m: m})
	return nil
}

// AnadirTF registra un L0 TF-IDF de la sección L0TF.
func (l *L0) AnadirTF(nombre string, m *chispa3.L0TFModelo) error {
	f := firma(m.Etiquetas)
	for _, x := range l.modelos {
		if x.firma == f {
			return fmt.Errorf("L0: %s y %s tienen las mismas etiquetas %v", x.nombre, nombre, m.Etiquetas)
		}
	}
	l.modelos = append(l.modelos, modelo{nombre: nombre, firma: f, tf: m})
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

func (l *L0) buscar(p Pregunta) *modelo {
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
	var found *modelo
	for i, x := range l.modelos {
		if x.firma == f {
			found = &l.modelos[i]
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
	if m.tf != nil {
		return respuestaTF(m.tf, p.Estado), nil
	}
	pred := m.m.PredictFull(chispa.Input{Text: p.Estado}, 0)
	probs := make(map[string]float64, len(pred.Probs))
	for _, cp := range pred.Probs {
		probs[cp.Label] = cp.Prob
	}
	return Respuesta{Answer: pred.Label, Probs: probs, Conf: pred.Prob}, nil
}

// respuestaTF: las probabilidades del TF-IDF con regresión logística; la respuesta es el primer máximo, como argmax.
func respuestaTF(m *chispa3.L0TFModelo, texto string) Respuesta {
	pr := m.Probs(texto)
	probs := make(map[string]float64, len(pr))
	top := 0
	for i, x := range pr {
		probs[m.Etiquetas[i]] = x
		if x > pr[top] {
			top = i
		}
	}
	return Respuesta{Answer: m.Etiquetas[top], Probs: probs, Conf: pr[top]}
}
