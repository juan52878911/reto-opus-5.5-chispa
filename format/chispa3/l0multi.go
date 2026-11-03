package chispa3

import (
	"encoding/binary"
	"fmt"
	"slices"
	"sort"
	"strings"
	"unicode/utf8"

	"github.com/juan52878911/kindling/pkg/chispa"
)

// ---- L0MULTI ----

// Varios L0 en un solo fichero: uno por pregunta few-shot (cada uno con su conjunto de etiquetas). Empaqueta N modelos de los
// que ya existen como sección (un Chispa de kindling, tipo L0, o un TF-IDF, tipo L0TF), cada uno con su propia versión interna.
// La sección L0 / L0TF de siempre sigue valiendo para un solo modelo; L0MULTI se escribe cuando son dos o más.
//
// Disposición (little endian, sin relleno):
//
//	u32 versión (1) · u32 N (1..maxL0Multi) ·
//	N×( u32 tipo (L0 o L0TF) · u16 len · nombre UTF-8 (opcional, para mensajes) · u64 len · datos tal cual de esa sección ).
//
// Cada modelo se decodifica con el decodificador de su tipo. Dos modelos con el mismo conjunto de etiquetas son un error
// (el servidor elige por etiquetas, no habría forma de decidir entre ellos). La calibración y el τ no son por modelo: siguen
// siendo los de CALIB, igual que con «modelos». La versión de cabecera sigue siendo 3: un lector que no conoce L0MULTI falla
// con ErrTipo al abrir el fichero (no lo lee a medias).
const (
	L0MultiVersion = 1
	maxL0Multi     = 1 << 12
	maxNombreL0    = 1 << 10
)

// EntradaL0 es un modelo L0 sin decodificar. Tipo es L0 o L0TF; Datos son los bytes de la sección de ese tipo.
type EntradaL0 struct {
	Nombre string
	Tipo   Tipo
	Datos  []byte
}

// ModeloL0 es una EntradaL0 decodificada: M si Tipo es L0 (kindling), TF si es L0TF.
type ModeloL0 struct {
	Nombre string
	Tipo   Tipo
	M      *chispa.Model
	TF     *L0TFModelo
}

// Etiquetas devuelve las etiquetas del modelo.
func (m ModeloL0) Etiquetas() []string {
	if m.TF != nil {
		return m.TF.Etiquetas
	}
	return m.M.Labels
}

// Decodificar valida y carga los datos según el tipo.
func (e EntradaL0) Decodificar() (ModeloL0, error) {
	switch e.Tipo {
	case L0TF:
		m, err := DecodificarL0TF(e.Datos)
		if err != nil {
			return ModeloL0{}, fmt.Errorf("%s: %w", e.Nombre, err)
		}
		return ModeloL0{Nombre: e.Nombre, Tipo: L0TF, TF: m}, nil
	case L0:
		m, err := chispa.Unmarshal(e.Datos)
		if err != nil {
			return ModeloL0{}, fmt.Errorf("%w: %s: L0: %v", ErrContenido, e.Nombre, err)
		}
		return ModeloL0{Nombre: e.Nombre, Tipo: L0, M: m}, nil
	}
	return ModeloL0{}, fmt.Errorf("%w: %s: tipo %v no es L0 ni L0TF", ErrContenido, e.Nombre, e.Tipo)
}

// FirmaEtiquetas es el conjunto de etiquetas como clave comparable (sin importar el orden).
func FirmaEtiquetas(ids []string) string {
	s := slices.Clone(ids)
	sort.Strings(s)
	return strings.Join(s, "\x00")
}

// CodificarL0Multi serializa la sección. No comprueba etiquetas repetidas (eso lo hace SeccionesL0 / el cargador).
func CodificarL0Multi(es []EntradaL0) ([]byte, error) {
	if len(es) < 1 || len(es) > maxL0Multi {
		return nil, fmt.Errorf("%w: L0MULTI con %d modelos", ErrContenido, len(es))
	}
	b := binary.LittleEndian.AppendUint32(nil, L0MultiVersion)
	b = binary.LittleEndian.AppendUint32(b, uint32(len(es)))
	for i, e := range es {
		if (e.Tipo != L0 && e.Tipo != L0TF) || len(e.Nombre) > maxNombreL0 || !utf8.ValidString(e.Nombre) {
			return nil, fmt.Errorf("%w: L0MULTI modelo %d", ErrContenido, i)
		}
		b = binary.LittleEndian.AppendUint32(b, uint32(e.Tipo))
		b = binary.LittleEndian.AppendUint16(b, uint16(len(e.Nombre)))
		b = append(b, e.Nombre...)
		b = binary.LittleEndian.AppendUint64(b, uint64(len(e.Datos)))
		b = append(b, e.Datos...)
	}
	return b, nil
}

// DecodificarL0Multi lee el marco de la sección (versión, tipos, nombres, longitudes); los datos de cada modelo
// se validan al decodificarlos. Los slices apuntan a b.
func DecodificarL0Multi(b []byte) ([]EntradaL0, error) {
	l := &lector{b: b}
	if v := l.u32(); l.err == nil && v != L0MultiVersion {
		return nil, fmt.Errorf("%w: L0MULTI versión %d", ErrContenido, v)
	}
	n := l.u32()
	if l.err != nil {
		return nil, l.err
	}
	if n < 1 || n > maxL0Multi {
		return nil, fmt.Errorf("%w: L0MULTI con %d modelos", ErrContenido, n)
	}
	es := make([]EntradaL0, 0, min(int(n), len(b)/16))
	for i := uint32(0); i < n; i++ {
		t := Tipo(l.u32())
		ln := l.toma(2)
		if l.err != nil {
			return nil, l.err
		}
		nom := l.toma(uint64(binary.LittleEndian.Uint16(ln)))
		tam := l.toma(8)
		if l.err != nil {
			return nil, l.err
		}
		d := l.toma(binary.LittleEndian.Uint64(tam))
		if l.err != nil {
			return nil, l.err
		}
		if (t != L0 && t != L0TF) || len(nom) > maxNombreL0 || !utf8.Valid(nom) {
			return nil, fmt.Errorf("%w: L0MULTI modelo %d", ErrContenido, i)
		}
		es = append(es, EntradaL0{Nombre: string(nom), Tipo: t, Datos: d})
	}
	if len(l.b) != 0 {
		return nil, fmt.Errorf("%w: L0MULTI con %d bytes sobrantes", ErrContenido, len(l.b))
	}
	return es, nil
}

// L0Multi devuelve los modelos de la sección L0MULTI decodificados y validados; ErrNoHay si el fichero no la tiene.
// Un nombre vacío se rellena con «L0MULTI[i]».
func (f *Fichero) L0Multi() ([]ModeloL0, error) {
	b, err := f.Bytes(L0MULTI)
	if err != nil {
		return nil, err
	}
	es, err := DecodificarL0Multi(b)
	if err != nil {
		return nil, err
	}
	out := make([]ModeloL0, 0, len(es))
	for i, e := range es {
		if e.Nombre == "" {
			e.Nombre = fmt.Sprintf("L0MULTI[%d]", i)
		}
		m, err := e.Decodificar()
		if err != nil {
			return nil, err
		}
		out = append(out, m)
	}
	return out, nil
}

func nombreL0(origen, interno string) string {
	if origen == "" {
		return "sección " + interno
	}
	return origen + " (" + interno + ")"
}

// EntradasL0 son todos los L0 del fichero sin decodificar: el de la sección L0TF (o el de L0 si no hay L0TF, como en
// el servidor) y los de L0MULTI, en ese orden. Los nombres llevan el origen (p. ej. la ruta) o, sin él, «sección …».
func (f *Fichero) EntradasL0(origen string) ([]EntradaL0, error) {
	var es []EntradaL0
	for _, t := range []Tipo{L0TF, L0} {
		if f.Tiene(t) {
			b, err := f.Bytes(t)
			if err != nil {
				return nil, err
			}
			es = append(es, EntradaL0{Nombre: nombreL0(origen, t.String()), Tipo: t, Datos: b})
			break
		}
	}
	if f.Tiene(L0MULTI) {
		b, err := f.Bytes(L0MULTI)
		if err != nil {
			return nil, err
		}
		ms, err := DecodificarL0Multi(b)
		if err != nil {
			return nil, err
		}
		for i, e := range ms {
			if e.Nombre == "" {
				e.Nombre = fmt.Sprintf("L0MULTI[%d]", i)
			}
			e.Nombre = nombreL0(origen, e.Nombre)
			es = append(es, e)
		}
	}
	return es, nil
}

// L0Todos decodifica EntradasL0 (nombres «sección L0TF», «sección L0MULTI[i]»). Las etiquetas repetidas no se comprueban aquí.
func (f *Fichero) L0Todos() ([]ModeloL0, error) {
	es, err := f.EntradasL0("")
	if err != nil {
		return nil, err
	}
	out := make([]ModeloL0, 0, len(es))
	for _, e := range es {
		m, err := e.Decodificar()
		if err != nil {
			return nil, err
		}
		out = append(out, m)
	}
	return out, nil
}

// SeccionesL0 convierte modelos L0 en las secciones que los llevan: ninguna si no hay, L0 o L0TF si es uno (como
// siempre), L0MULTI si son dos o más. Falla, nombrando los dos orígenes, si dos tienen el mismo conjunto de etiquetas.
func SeccionesL0(es []EntradaL0) ([]Seccion, error) {
	vistas := map[string]string{}
	for _, e := range es {
		m, err := e.Decodificar()
		if err != nil {
			return nil, err
		}
		f := FirmaEtiquetas(m.Etiquetas())
		if o, ok := vistas[f]; ok {
			return nil, fmt.Errorf("L0: %s y %s tienen las mismas etiquetas %v", o, e.Nombre, m.Etiquetas())
		}
		vistas[f] = e.Nombre
	}
	switch len(es) {
	case 0:
		return nil, nil
	case 1:
		return []Seccion{{Tipo: es[0].Tipo, Datos: es[0].Datos}}, nil
	}
	b, err := CodificarL0Multi(es)
	if err != nil {
		return nil, err
	}
	return []Seccion{{Tipo: L0MULTI, Datos: b}}, nil
}
