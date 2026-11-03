package decide

import (
	"bytes"
	"context"
	"encoding/binary"
	"errors"
	"fmt"
	"io"
	"log"
	"os"
	"path/filepath"
	"slices"
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
	// Avisos: uno por fichero v3 de "modelos" que trae secciones que se ignoran (ya escritos en el log).
	Avisos []string
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

// Cargar lee ficheros .chispa con el tope de tamaño por defecto de chispa3.
func (l *L0) Cargar(paths ...string) error { return l.CargarCon(chispa3.Limites{}, paths...) }

// CargarCon lee ficheros .chispa: un v1/v2 de kindling, o un v3 solo-L0 (sección L0TF, o L0 si no hay), que se abre con chispa3
// respetando lim (max_fichero). Del v3 solo se usa su L0: CALIB, SOPL1, ESQUEMAS, CONJ y demás se ignoran con un aviso por fichero
// (en l.Avisos y en el log); L1, L2 o TORR son un error, porque ese fichero es un -modelo. META no se avisa: no cambia lo que se sirve.
func (l *L0) CargarCon(lim chispa3.Limites, paths ...string) error {
	for _, p := range paths {
		if esV3(p) {
			if err := l.cargarV3(p, lim); err != nil {
				return err
			}
			continue
		}
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

func (l *L0) cargarV3(p string, lim chispa3.Limites) error {
	f, err := chispa3.AbrirCon(p, lim)
	if err != nil {
		if errors.Is(err, chispa3.ErrTamano) {
			return fmt.Errorf("modelos: %s: %w (tope aplicado: %d bytes; suba \"max_fichero\" en la config si es legítimo)", p, err, lim.MaxFichero)
		}
		return fmt.Errorf("modelos: %s: %w", p, err)
	}
	defer f.Close()
	var pesadas []string
	for _, t := range []chispa3.Tipo{chispa3.L1, chispa3.L2, chispa3.TORR} {
		if f.Tiene(t) {
			pesadas = append(pesadas, t.String())
		}
	}
	if len(pesadas) > 0 {
		return fmt.Errorf("modelos: %s: \"modelos\" es solo para L0; ese fichero lleva %s; úselo como -modelo", p, strings.Join(pesadas, ", "))
	}
	if !f.Tiene(chispa3.L0TF) && !f.Tiene(chispa3.L0) {
		return fmt.Errorf("modelos: %s: el .chispa v3 no trae L0 ni L0TF", p)
	}
	usada := chispa3.L0
	if f.Tiene(chispa3.L0TF) { // como ArmarDesde: L0TF manda sobre L0
		usada = chispa3.L0TF
	}
	if usada == chispa3.L0TF {
		m, err := f.L0TF()
		if err != nil {
			return fmt.Errorf("modelos: %s: sección L0TF: %w", p, err)
		}
		if err := l.AnadirTF(p, m); err != nil {
			return err
		}
	} else {
		m, err := f.L0Modelo()
		if err != nil {
			return fmt.Errorf("modelos: %s: sección L0: %w", p, err)
		}
		if err := l.Anadir(p, m); err != nil {
			return err
		}
	}
	var ign []string
	for _, t := range f.Tipos() {
		if t != usada && t != chispa3.META {
			ign = append(ign, t.String())
		}
	}
	if len(ign) > 0 {
		sort.Strings(ign)
		aviso := fmt.Sprintf("modelos: %s: se usa solo su %s; se ignoran %s", filepath.Base(p), usada, strings.Join(ign, ", "))
		if slices.Contains(ign, "CALIB") {
			aviso += ": la calibración es la del -modelo"
		}
		l.Avisos = append(l.Avisos, aviso)
		log.Print("AVISO: " + aviso)
	}
	return nil
}

// esV3 dice si el fichero empieza con la cabecera de un .chispa v3 (misma magia que v1/v2, versión 3 en el byte 8).
func esV3(ruta string) bool {
	f, err := os.Open(ruta)
	if err != nil {
		return false
	}
	defer f.Close()
	var cab [10]byte
	if _, err := io.ReadFull(f, cab[:]); err != nil {
		return false
	}
	return bytes.Equal(cab[:8], []byte{0x89, 'C', 'H', 'I', '\r', '\n', 0x1a, '\n'}) &&
		binary.LittleEndian.Uint16(cab[8:]) == chispa3.Version
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
	if p.Kind == KindMulti {
		return Respuesta{}, nil // el L0 entrenado es multiclase (probs que suman 1): no da una p por opción, no opina en multi
	}
	if !scoreValido(p) {
		return Respuesta{}, nil // score con ids que no son 1..K: no opina
	}
	m := l.buscar(p)
	if m == nil {
		return Respuesta{}, nil
	}
	if m.tf != nil {
		return ordinal(p, respuestaTF(m.tf, p.Estado)), nil
	}
	pred := m.m.PredictFull(chispa.Input{Text: p.Estado}, 0)
	probs := make(map[string]float64, len(pred.Probs))
	for _, cp := range pred.Probs {
		probs[cp.Label] = cp.Prob
	}
	return ordinal(p, Respuesta{Answer: pred.Label, Probs: probs, Conf: pred.Prob}), nil
}

// ordinal: en score la respuesta es la mediana de la distribución (como L1, L2 y L3), no el argmax de un clasificador multiclase.
func ordinal(p Pregunta, r Respuesta) Respuesta {
	if p.Kind != KindScore || r.Conf == 0 {
		return r
	}
	var acc float64
	niveles, _ := opcionesNiveles(p.Opciones) // Decidir ya comprobó 1..K
	for _, o := range niveles {
		if acc += r.Probs[o.ID]; acc >= 0.5 {
			r.Answer, r.Conf = o.ID, r.Probs[o.ID]
			break
		}
	}
	return r
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
