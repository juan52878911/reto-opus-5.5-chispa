package decide

import (
	"context"
	"errors"
	"reflect"
	"sort"
	"strings"
	"sync"
	"testing"

	"chispa/format/chispa3"
	"chispa/runtime/torre"
)

// codificadorApunta devuelve una torre distinta por texto (hash simple) y apunta los textos calculados; falla desde la llamada falla (1-based; 0 = nunca).
type codificadorApunta struct {
	mu     sync.Mutex
	textos []string
	falla  int
}

func (c *codificadorApunta) Torre(texto string) ([]float32, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.textos = append(c.textos, texto)
	if c.falla > 0 && len(c.textos) >= c.falla {
		return nil, errors.New("codificador roto")
	}
	return []float32{float32(len(texto)), 1}, nil
}

// R20 #1: con v2_sin_id el texto de una opción depende de las demás; la clave de caché y del vuelo sale del texto efectivo.
// Dos peticiones con la misma pregunta, id y descripción de «a» pero otras opciones, en los dos órdenes.
func TestR20ClaveDelTextoEfectivoServidor(t *testing.T) {
	p1 := Pregunta{Texto: "¿q?", Kind: KindChoice, Opciones: []Opcion{{ID: "a", Description: "pago"}, {ID: "b", Description: "cobro"}}}
	p2 := Pregunta{Texto: "¿q?", Kind: KindChoice, Opciones: []Opcion{{ID: "a", Description: "pago"}, {ID: "c", Description: "pago"}}}
	for nombre, orden := range map[string][]Pregunta{"1-2": {p1, p2}, "2-1": {p2, p1}} {
		t.Run(nombre, func(t *testing.T) {
			enc := &codificadorApunta{}
			l := l2Torres(t, enc, 1024).ConTextoTorre(chispa3.TextoTorreV2SinID)
			for _, p := range orden {
				ts, ok, err := l.torresNuevas(context.Background(), p)
				if err != nil || !ok {
					t.Fatalf("%v %v", ok, err)
				}
				// cada torre devuelta es la que está bajo la clave del texto efectivo de su opción
				for i, o := range OpcionesConsulta(p) {
					if got, _ := l.cache.Get(ClaveTorre(chispa3.TextoTorreV2SinID, p, o)); !reflect.DeepEqual(got, ts[i]) {
						t.Fatalf("%s: la torre devuelta no es la de su clave", o.ID)
					}
				}
			}
			got := append([]string(nil), enc.textos...)
			sort.Strings(got)
			want := []string{"passage: ¿q? · a · pago", "passage: ¿q? · c · pago", "passage: ¿q? · cobro", "passage: ¿q? · pago"}
			sort.Strings(want)
			if !reflect.DeepEqual(got, want) {
				t.Fatalf("textos calculados %q, esperaba %q (a con v2 y a con v1 son torres distintas)", got, want)
			}
		})
	}
}

// Con v1 el texto no depende de las demás opciones: la clave de «a» es la misma en las dos preguntas (la caché sigue compartiendo).
func TestR20ClaveV1IndependienteDeLasDemas(t *testing.T) {
	p1 := Pregunta{Texto: "¿q?", Opciones: []Opcion{{ID: "a", Description: "pago"}, {ID: "b", Description: "cobro"}}}
	p2 := Pregunta{Texto: "¿q?", Opciones: []Opcion{{ID: "a", Description: "pago"}, {ID: "c", Description: "pago"}}}
	for _, v := range []string{"", chispa3.TextoTorreV1} {
		if ClaveTorre(v, p1, p1.Opciones[0]) != ClaveTorre(v, p2, p2.Opciones[0]) {
			t.Fatalf("v1 (%q): la clave de «a» no debe depender de las demás opciones", v)
		}
	}
	if ClaveTorre(chispa3.TextoTorreV2SinID, p1, p1.Opciones[0]) == ClaveTorre(chispa3.TextoTorreV2SinID, p2, p2.Opciones[0]) {
		t.Fatal("v2: «a» tiene textos distintos en las dos preguntas y no puede compartir clave")
	}
	if torre.ClaveTexto("x") == torre.ClaveTexto("y") {
		t.Fatal("ClaveTexto no distingue textos")
	}
}

// R20 #5 (camino completo): un error a mitad devuelve a la petición el cupo reservado y no gastado.
func TestR20CupoDevueltoCaminoCompleto(t *testing.T) {
	enc := &codificadorApunta{falla: 3}
	l := l2Torres(t, enc, 1024)
	ctx := conPresupuesto(context.Background())
	if _, _, err := l.torresNuevas(ctx, preguntaConOpciones(6)); err == nil {
		t.Fatal("esperaba el error del codificador")
	}
	// 2 torres bien calculadas; la tercera falló y no se gastó
	if u := presupuestoDe(ctx).usadas.Load(); u != 2 {
		t.Fatalf("usadas=%d, esperaba 2 (las calculadas)", u)
	}
}

// R20 #5 (camino parcial): el cupo que no se llegó a gastar vuelve a pr.usadas.
func TestR20CupoDevueltoCaminoParcial(t *testing.T) {
	enc := &codificadorApunta{falla: 2}
	l := l2Torres(t, enc, 1024).ConMaxTorresNuevas(4)
	ctx := conPresupuesto(context.Background())
	if _, _, err := l.torresNuevas(ctx, preguntaConOpciones(10)); !errors.Is(err, errSinPresupuestoTorres) {
		t.Fatalf("err=%v", err)
	}
	if u := presupuestoDe(ctx).usadas.Load(); u != 1 {
		t.Fatalf("usadas=%d, esperaba 1 (solo la primera se calculó)", u)
	}
	// ctx cancelado antes de empezar: nada gastado
	ctx2, cancel := context.WithCancel(conPresupuesto(context.Background()))
	cancel()
	l2 := l2Torres(t, &codificadorApunta{}, 1024).ConMaxTorresNuevas(4)
	l2.torresNuevas(ctx2, preguntaConOpciones(10))
	if u := presupuestoDe(ctx2).usadas.Load(); u != 0 {
		t.Fatalf("ctx cancelado: usadas=%d", u)
	}
}

// R20 #6 / ZE: Validar acepta cualquier cache_torres >= 0 (el mínimo 16 × max_opciones se aplica al montar el modelo con TORR);
// el aviso de cache_torres < max_torres_nuevas sigue.
func TestR20ConfigCacheTorresMenorQueMax(t *testing.T) {
	cfg := ConfigPorDefecto()
	if err := cfg.Validar(); err != nil {
		t.Fatalf("el defecto debe ser válido: %v", err)
	}
	for _, k := range [][2]int{{128, 256}, {128, 0}, {64, 64}, {384, 256}, {0, 64}} {
		cfg.CacheTorres, cfg.MaxTorresNuevas = k[0], k[1]
		if err := cfg.Validar(); err != nil {
			t.Fatalf("cache=%d max=%d debe ser válida: %v", k[0], k[1], err)
		}
	}
	cfg.CacheTorres, cfg.MaxTorresNuevas = 128, 256
	for _, a := range cfg.Avisos() { // R22-7: ArmarDesde sube la caché al mínimo; Config.Avisos ya no compara con el valor pedido
		if strings.Contains(a, "cache_torres") {
			t.Fatalf("cache_torres < max_torres_nuevas ya no avisa desde la config: %q", a)
		}
	}
	cfg.CacheTorres = -1
	if err := cfg.Validar(); err == nil {
		t.Fatal("cache_torres negativo debe fallar")
	}
}
