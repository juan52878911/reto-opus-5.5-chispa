package decide

import (
	"context"
	"strings"
	"testing"
)

func promptUsuarioL3(t *testing.T, ids ...string) string {
	t.Helper()
	f := &llmFalso{contenido: `{"probs":{"1":0.3,"2":0.4,"3":0.3}}`}
	l, _ := nuevoL3Test(t, f.arranca(t), nil)
	if _, err := l.Decidir(context.Background(), pregL3(KindScore, ids...)); err != nil {
		t.Fatal(err)
	}
	return f.ultima.Load().(peticionL3).Messages[1].Content
}

// H1: el prompt de score lista las opciones por nivel, sea cual sea el orden de la petición.
func TestXAPromptL3ScoreOrden(t *testing.T) {
	a := promptUsuarioL3(t, "1", "2", "3")
	b := promptUsuarioL3(t, "3", "1", "2")
	if a != b {
		t.Fatalf("el prompt depende del orden declarado:\n%s\n%s", a, b)
	}
	if !strings.Contains(a, `"id":"1"`) || strings.Index(a, `"id":"1"`) > strings.Index(a, `"id":"3"`) {
		t.Fatalf("opciones fuera de nivel: %s", a)
	}
}

// H3: «01» no empata con «1»: ids no canónicos van al orden declarado (como los no numéricos).
func TestXAIdsNoCanonicosOrdenDeclarado(t *testing.T) {
	for _, ids := range [][]string{{"2", "01", "1"}, {"2", "+1", "1"}} {
		got := opcionesPorNivel(pregL3(KindScore, ids...).Opciones)
		for i, o := range got {
			if o.ID != ids[i] {
				t.Fatalf("%v reordenado: %v", ids, got)
			}
		}
	}
}

// H4: en score no numérico la clave de la caché de nonce incluye el orden declarado.
func TestXANonceScoreNoNumericoOrden(t *testing.T) {
	s, h, _ := servidorConClaves(t, nil)
	cuerpo := func(ids ...string) string {
		var ops []string
		for _, id := range ids {
			ops = append(ops, `{"id":"`+id+`"}`)
		}
		return `{"state":"s","questions":[{"id":"q","question":"¿?","kind":"score","nonce":"n1","options":[` + strings.Join(ops, ",") + `]}]}`
	}
	respuesta(t, h, cuerpo("bajo", "medio", "alto"))
	respuesta(t, h, cuerpo("alto", "medio", "bajo"))
	if n := s.Met.NonceHits.Load(); n != 0 {
		t.Fatalf("otro orden declarado acertó la caché (aciertos %d)", n)
	}
	respuesta(t, h, cuerpo("alto", "medio", "bajo"))
	if n := s.Met.NonceHits.Load(); n != 1 {
		t.Fatalf("misma petición no acertó la caché (aciertos %d)", n)
	}
	// ids enteros canónicos: el orden no importa, sigue acertando.
	respuesta(t, h, strings.ReplaceAll(cuerpo("1", "2", "3"), "n1", "n2"))
	respuesta(t, h, strings.ReplaceAll(cuerpo("3", "1", "2"), "n1", "n2"))
	if n := s.Met.NonceHits.Load(); n != 2 {
		t.Fatalf("enteros canónicos deben compartir caché (aciertos %d)", n)
	}
}
