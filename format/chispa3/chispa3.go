// Paquete chispa3 es el contenedor .chispa v3: una cabecera con versión, una tabla de secciones
// (tipo, offset, longitud, sha256) y las secciones (META, L0, L1, L2, ESQUEMAS, CALIB, CONJ, L0TF). El cargador
// valida toda la estructura al abrir y el sha256 de cada sección antes de entregar sus bytes.
package chispa3

import (
	"bytes"
	"crypto/sha256"
	"encoding/binary"
	"errors"
	"fmt"
	"hash/crc32"
	"io"
	"math"
	"os"
	"sort"
	"sync"
)

// Tipo identifica una sección.
type Tipo uint32

const (
	META Tipo = 1 + iota
	L0
	L1
	L2
	ESQUEMAS
	CALIB
	CONJ
	L0TF
	numTipos = iota + 1
)

func (t Tipo) String() string {
	switch t {
	case META:
		return "META"
	case L0:
		return "L0"
	case L1:
		return "L1"
	case L2:
		return "L2"
	case ESQUEMAS:
		return "ESQUEMAS"
	case CALIB:
		return "CALIB"
	case CONJ:
		return "CONJ"
	case L0TF:
		return "L0TF"
	}
	return fmt.Sprintf("tipo(%d)", uint32(t))
}

const (
	Version     = 3
	tamCabecera = 32
	tamEntrada  = 56
	alineacion  = 16
)

var magia = [8]byte{0x89, 'C', 'H', 'I', '\r', '\n', 0x1a, '\n'} // la misma que v1/v2

// Errores de validación; se devuelven envueltos con detalle (errors.Is).
var (
	ErrMagia     = errors.New("chispa3: magia incorrecta")
	ErrVersion   = errors.New("chispa3: versión no soportada")
	ErrTruncado  = errors.New("chispa3: fichero truncado")
	ErrCabecera  = errors.New("chispa3: cabecera inválida")
	ErrCRC       = errors.New("chispa3: crc de cabecera/tabla incorrecto")
	ErrTabla     = errors.New("chispa3: tabla de secciones inválida")
	ErrTipo      = errors.New("chispa3: tipo de sección desconocido")
	ErrDuplicado = errors.New("chispa3: tipo de sección repetido")
	ErrSolape    = errors.New("chispa3: secciones solapadas")
	ErrHueco     = errors.New("chispa3: hueco o desalineación entre secciones")
	ErrFuera     = errors.New("chispa3: sección fuera del fichero")
	ErrDesborde  = errors.New("chispa3: desborde de enteros en la tabla")
	ErrTamano    = errors.New("chispa3: supera un tamaño máximo")
	ErrHash      = errors.New("chispa3: sha256 de sección incorrecto")
	ErrNoHay     = errors.New("chispa3: la sección no existe")
	ErrRelleno   = errors.New("chispa3: relleno distinto de cero")
	ErrContenido = errors.New("chispa3: contenido de sección inválido")
	ErrCerrado   = errors.New("chispa3: fichero cerrado")
)

// Limites acota lo que el cargador acepta; el cero de cada campo significa «por defecto».
type Limites struct {
	MaxFichero   int64          // 1 GiB
	MaxSecciones int            // numTipos-1
	MaxSeccion   int64          // 512 MiB, para los tipos sin entrada propia
	PorTipo      map[Tipo]int64 // máximo por tipo
}

const (
	defMaxFichero = 1 << 30
	defMaxSeccion = 512 << 20
)

func (l Limites) maxFichero() int64 {
	if l.MaxFichero > 0 {
		return l.MaxFichero
	}
	return defMaxFichero
}

func (l Limites) maxSecciones() int {
	if l.MaxSecciones > 0 {
		return l.MaxSecciones
	}
	return numTipos - 1
}

func (l Limites) maxDe(t Tipo) int64 {
	if m, ok := l.PorTipo[t]; ok {
		return m
	}
	if l.MaxSeccion > 0 {
		return l.MaxSeccion
	}
	return defMaxSeccion
}

// Seccion es una sección a escribir.
type Seccion struct {
	Tipo  Tipo
	Datos []byte
}

type entrada struct {
	tipo   Tipo
	off    uint64 // relativo al inicio del área de datos
	len    uint64
	sha    [32]byte
	datos  []byte
	una    sync.Once
	errSHA error
}

// Fichero es un .chispa v3 abierto. Es de solo lectura y seguro para uso concurrente.
// Los []byte entregados dejan de ser válidos tras Close.
type Fichero struct {
	data   []byte
	cerrar func() error
	mu     sync.RWMutex
	cerr   bool
	sec    map[Tipo]*entrada
	orden  []Tipo
	compat bool
}

func alinear(n uint64) uint64 { return (n + alineacion - 1) &^ (alineacion - 1) }

// Escribir serializa las secciones en orden de tipo, alineadas a 16 bytes y con relleno cero.
func Escribir(w io.Writer, secs []Seccion) error {
	if len(secs) == 0 {
		return fmt.Errorf("%w: sin secciones", ErrTabla)
	}
	s := append([]Seccion(nil), secs...)
	sort.Slice(s, func(i, j int) bool { return s[i].Tipo < s[j].Tipo })
	for i, x := range s {
		if x.Tipo == 0 || x.Tipo >= numTipos {
			return fmt.Errorf("%w: %v", ErrTipo, x.Tipo)
		}
		if i > 0 && s[i-1].Tipo == x.Tipo {
			return fmt.Errorf("%w: %v", ErrDuplicado, x.Tipo)
		}
	}
	tabla := make([]byte, tamEntrada*len(s))
	var off uint64
	for i, x := range s {
		off = alinear(off)
		e := tabla[i*tamEntrada:]
		binary.LittleEndian.PutUint32(e[0:], uint32(x.Tipo))
		binary.LittleEndian.PutUint64(e[8:], off)
		binary.LittleEndian.PutUint64(e[16:], uint64(len(x.Datos)))
		sum := sha256.Sum256(x.Datos)
		copy(e[24:], sum[:])
		off += uint64(len(x.Datos))
	}
	cab := make([]byte, tamCabecera)
	copy(cab, magia[:])
	binary.LittleEndian.PutUint16(cab[8:], Version)
	binary.LittleEndian.PutUint32(cab[12:], uint32(len(s)))
	binary.LittleEndian.PutUint64(cab[16:], uint64(tamCabecera+len(tabla))+off)
	c := crc32.Update(crc32.Checksum(cab, crcTabla), crcTabla, tabla)
	binary.LittleEndian.PutUint32(cab[24:], c)
	if _, err := w.Write(cab); err != nil {
		return err
	}
	if _, err := w.Write(tabla); err != nil {
		return err
	}
	var pos uint64
	var cero [alineacion]byte
	for _, x := range s {
		if p := alinear(pos) - pos; p > 0 {
			if _, err := w.Write(cero[:p]); err != nil {
				return err
			}
			pos += p
		}
		if _, err := w.Write(x.Datos); err != nil {
			return err
		}
		pos += uint64(len(x.Datos))
	}
	return nil
}

var crcTabla = crc32.MakeTable(crc32.Castagnoli)

// Abrir mapea ruta en memoria y la valida con los límites por defecto. Acepta también un .chispa
// v1/v2, que envuelve en un Fichero con solo la sección L0.
func Abrir(ruta string) (*Fichero, error) { return AbrirCon(ruta, Limites{}) }

// AbrirCon es Abrir con límites propios.
func AbrirCon(ruta string, lim Limites) (*Fichero, error) {
	f, err := os.Open(ruta)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	st, err := f.Stat()
	if err != nil {
		return nil, err
	}
	if !st.Mode().IsRegular() {
		return nil, fmt.Errorf("chispa3: %s no es un fichero regular", ruta)
	}
	if st.Size() > lim.maxFichero() {
		return nil, fmt.Errorf("%w: fichero de %d bytes", ErrTamano, st.Size())
	}
	if st.Size() < tamCabecera {
		return nil, fmt.Errorf("%w: %d bytes", ErrTruncado, st.Size())
	}
	data, cerrar, err := mapear(f, st.Size())
	if err != nil {
		return nil, err
	}
	fi, err := Desde(data, lim)
	if err != nil {
		cerrar()
		return nil, err
	}
	fi.cerrar = cerrar
	return fi, nil
}

// Desde valida data como un .chispa v3 (o v1/v2). data debe seguir vivo y sin cambios mientras se use.
func Desde(data []byte, lim Limites) (*Fichero, error) {
	if int64(len(data)) > lim.maxFichero() {
		return nil, fmt.Errorf("%w: %d bytes", ErrTamano, len(data))
	}
	if len(data) < len(magia) || !bytes.Equal(data[:len(magia)], magia[:]) {
		return nil, ErrMagia
	}
	if len(data) < tamCabecera {
		return nil, fmt.Errorf("%w: cabecera de %d bytes", ErrTruncado, len(data))
	}
	ver := binary.LittleEndian.Uint16(data[8:])
	switch ver {
	case legadoVersion:
		return desdeLegado(data, lim)
	case Version:
	default:
		return nil, fmt.Errorf("%w: %d", ErrVersion, ver)
	}
	if binary.LittleEndian.Uint16(data[10:]) != 0 {
		return nil, fmt.Errorf("%w: banderas", ErrCabecera)
	}
	if !todoCero(data[28:tamCabecera]) {
		return nil, fmt.Errorf("%w: reservado", ErrCabecera)
	}
	n := uint64(binary.LittleEndian.Uint32(data[12:]))
	if n == 0 || n > uint64(lim.maxSecciones()) {
		return nil, fmt.Errorf("%w: %d secciones", ErrTabla, n)
	}
	total := binary.LittleEndian.Uint64(data[16:])
	if total != uint64(len(data)) {
		if total > uint64(len(data)) {
			return nil, fmt.Errorf("%w: la cabecera declara %d bytes y hay %d", ErrTruncado, total, len(data))
		}
		return nil, fmt.Errorf("%w: la cabecera declara %d bytes y hay %d (bytes sobrantes)", ErrCabecera, total, len(data))
	}
	inicio := uint64(tamCabecera) + n*tamEntrada // n ≤ 2^32: no desborda
	if inicio > total {
		return nil, fmt.Errorf("%w: la tabla no cabe", ErrTruncado)
	}
	tabla := data[tamCabecera:inicio]
	var cab [tamCabecera]byte
	copy(cab[:], data)
	crcDecl := binary.LittleEndian.Uint32(cab[24:])
	binary.LittleEndian.PutUint32(cab[24:], 0)
	if crc32.Update(crc32.Checksum(cab[:], crcTabla), crcTabla, tabla) != crcDecl {
		return nil, ErrCRC
	}
	datos := data[inicio:]
	tam := uint64(len(datos))
	fi := &Fichero{data: data, sec: make(map[Tipo]*entrada, n)}
	var fin uint64 // fin de la sección anterior
	for i := uint64(0); i < n; i++ {
		e := tabla[i*tamEntrada : (i+1)*tamEntrada]
		t := Tipo(binary.LittleEndian.Uint32(e[0:]))
		if t == 0 || t >= numTipos {
			return nil, fmt.Errorf("%w: %d", ErrTipo, uint32(t))
		}
		if _, ok := fi.sec[t]; ok {
			return nil, fmt.Errorf("%w: %v", ErrDuplicado, t)
		}
		if binary.LittleEndian.Uint32(e[4:]) != 0 {
			return nil, fmt.Errorf("%w: reservado en la entrada %d", ErrTabla, i)
		}
		off := binary.LittleEndian.Uint64(e[8:])
		ln := binary.LittleEndian.Uint64(e[16:])
		if off > math.MaxInt64 || ln > math.MaxInt64 || ln > math.MaxUint64-off {
			return nil, fmt.Errorf("%w: %v", ErrDesborde, t)
		}
		if off > tam || ln > tam-off {
			return nil, fmt.Errorf("%w: %v off=%d len=%d de %d", ErrFuera, t, off, ln, tam)
		}
		if ln > uint64(lim.maxDe(t)) {
			return nil, fmt.Errorf("%w: %v de %d bytes", ErrTamano, t, ln)
		}
		if off < fin {
			return nil, fmt.Errorf("%w: %v empieza en %d y la anterior acaba en %d", ErrSolape, t, off, fin)
		}
		if off != alinear(fin) {
			return nil, fmt.Errorf("%w: %v empieza en %d, se esperaba %d", ErrHueco, t, off, alinear(fin))
		}
		if !todoCero(datos[fin:off]) {
			return nil, ErrRelleno
		}
		x := &entrada{tipo: t, off: off, len: ln, datos: datos[off : off+ln : off+ln]}
		copy(x.sha[:], e[24:56])
		fi.sec[t] = x
		fi.orden = append(fi.orden, t)
		fin = off + ln
	}
	if fin != tam {
		return nil, fmt.Errorf("%w: %d bytes tras la última sección", ErrCabecera, tam-fin)
	}
	return fi, nil
}

func todoCero(b []byte) bool {
	for _, c := range b {
		if c != 0 {
			return false
		}
	}
	return true
}

// Tipos devuelve los tipos presentes, en el orden del fichero.
func (f *Fichero) Tipos() []Tipo { return append([]Tipo(nil), f.orden...) }

// Tiene dice si existe la sección.
func (f *Fichero) Tiene(t Tipo) bool { _, ok := f.sec[t]; return ok }

// Compat dice si el fichero era un .chispa v1/v2 envuelto.
func (f *Fichero) Compat() bool { return f.compat }

// Bytes devuelve el contenido de la sección tras comprobar (una vez) su sha256.
// El slice apunta al mapa de memoria: no se debe modificar ni usar tras Close.
func (f *Fichero) Bytes(t Tipo) ([]byte, error) {
	f.mu.RLock()
	defer f.mu.RUnlock()
	if f.cerr {
		return nil, ErrCerrado
	}
	x, ok := f.sec[t]
	if !ok {
		return nil, fmt.Errorf("%w: %v", ErrNoHay, t)
	}
	x.una.Do(func() {
		if sha256.Sum256(x.datos) != x.sha {
			x.errSHA = fmt.Errorf("%w: %v", ErrHash, t)
		}
	})
	if x.errSHA != nil {
		return nil, x.errSHA
	}
	return x.datos, nil
}

// Verificar comprueba el sha256 de todas las secciones.
func (f *Fichero) Verificar() error {
	for _, t := range f.orden {
		if _, err := f.Bytes(t); err != nil {
			return err
		}
	}
	return nil
}

// Close libera el mapa de memoria. Es idempotente.
func (f *Fichero) Close() error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.cerr {
		return nil
	}
	f.cerr = true
	if f.cerrar != nil {
		return f.cerrar()
	}
	return nil
}
