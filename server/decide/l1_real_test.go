package decide

import (
	"bytes"
	"context"
	"fmt"
	"os"
	"sort"
	"sync"
	"testing"
	"time"

	"chispa/format/chispa3"
)

// l1Real abre el potion exportado (CHISPA_L1, por defecto /tmp/potion.chispa-l1; 155 MB, no va a git)
// dentro de un v3 en memoria. Sin él, el benchmark se salta.
func l1Real(tb testing.TB) *Cascada {
	tb.Helper()
	ruta := os.Getenv("CHISPA_L1")
	if ruta == "" {
		ruta = "/tmp/potion.chispa-l1"
	}
	l1b, err := os.ReadFile(ruta)
	if err != nil {
		tb.Skipf("falta %s (python runtime/l1/exportar.py): este benchmark NO se ha ejecutado", ruta)
	}
	cb, _ := calibTiny().Codificar()
	var buf bytes.Buffer
	if err := chispa3.Escribir(&buf, []chispa3.Seccion{{Tipo: chispa3.L1, Datos: l1b}, {Tipo: chispa3.CALIB, Datos: cb}}); err != nil {
		tb.Fatal(err)
	}
	f, err := chispa3.Desde(buf.Bytes(), chispa3.Limites{})
	if err != nil {
		tb.Fatal(err)
	}
	cfg := ConfigPorDefecto()
	mt, err := ArmarDesde(f, NuevoL0(cfg.CacheEsquemas), &cfg, false, nil)
	if err != nil {
		tb.Fatal(err)
	}
	c, err := NuevaCascada(cfg.Capas, []Decisor{NuevoL0(8), mt.L1, mt.L2, NuevoL3()}, NuevasMetricas())
	if err != nil {
		tb.Fatal(err)
	}
	return c
}

var mensajes = []string{
	"Hola, quiero que me devuelvan el dinero de la última factura porque me cobraron dos veces.",
	"Mi paquete lleva diez días de retraso y nadie me da una respuesta.",
	"No puedo entrar en mi cuenta desde ayer, me dice que la contraseña es incorrecta.",
	"Gracias por la ayuda, todo resuelto.",
	"Necesito cambiar la dirección de entrega del pedido que hice esta mañana.",
	"El producto llegó roto, ¿cómo hago la devolución?",
	"¿A qué hora abren mañana las oficinas?",
	"Quiero cancelar mi suscripción y que no me cobren el mes que viene.",
}

func preguntasLote(n, desde int) []Pregunta {
	esq := [][]Opcion{opsReembolso(),
		{{ID: "alta", Description: "urgente, hay que atender ya"}, {ID: "baja", Description: "puede esperar"}, {ID: "media", Description: "esta semana"}},
		{{ID: "queja", Description: "el cliente se queja"}, {ID: "consulta", Description: "pregunta informativa"}}}
	out := make([]Pregunta, n)
	for i := range out {
		k := (desde + i) % len(esq)
		out[i] = Pregunta{ID: fmt.Sprint(i), Kind: KindChoice, Texto: fmt.Sprintf("Clasifica el mensaje %d", k), Estado: mensajes[(desde+i)%len(mensajes)], Opciones: esq[k]}
	}
	return out
}

// BenchmarkL1Real: lotes de 16 preguntas con el potion de verdad (L0 sin modelo → L1), sin HTTP.
// Informa decisiones/s y el p99 por lote de 16. Va con 1 y 4 goroutines (-cpu 1,4).
func BenchmarkL1Real(b *testing.B) {
	casc := l1Real(b)
	ctx := context.Background()
	for _, p := range preguntasLote(16, 0) { // calienta la caché de esquemas y de páginas
		if r := casc.Decidir(ctx, p); len(r.Probs) == 0 {
			b.Fatalf("L1 no opinó: %+v", r)
		}
	}
	var mu sync.Mutex
	var lat []time.Duration
	b.ResetTimer()
	b.RunParallel(func(pb *testing.PB) {
		var loc []time.Duration
		for i := 0; pb.Next(); i++ {
			t := time.Now()
			for _, p := range preguntasLote(16, i) {
				casc.Decidir(ctx, p)
			}
			loc = append(loc, time.Since(t))
		}
		mu.Lock()
		lat = append(lat, loc...)
		mu.Unlock()
	})
	b.StopTimer()
	sort.Slice(lat, func(i, j int) bool { return lat[i] < lat[j] })
	if len(lat) > 0 {
		b.ReportMetric(float64(lat[len(lat)*99/100].Microseconds())/1000, "p99-lote16-ms")
	}
	b.ReportMetric(16*float64(b.N)/b.Elapsed().Seconds(), "dec/s")
}
