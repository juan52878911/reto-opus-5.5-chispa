package decide

import "testing"

func FuzzDecide(f *testing.F) {
	for _, s := range []string{
		`{"state":"x","questions":[{"id":"1","question":"q","kind":"choice","options":[{"id":"a"},{"id":"b"}]}]}`,
		`{"questions":[{"id":"1","question":"q","kind":"noul","nonce":"n"}]}`,
		`{"questions":[{"id":"1","question":"q","kind":"score","options":[{"id":"1"},{"id":"2"}]}]}`,
		`{`, ``, `[]`, `null`, `{"questions":null}`, `{"questions":[{}]}`, "\x00\xff",
	} {
		f.Add(s)
	}
	met := NuevasMetricas()
	d := Stub{"L0"}
	c, err := NuevaCascada([]Capa{{d.Nombre(), 0.8}}, []Decisor{d}, met)
	if err != nil {
		f.Fatal(err)
	}
	h := NuevoServidor(c, met, 16).Handler()
	f.Fuzz(func(t *testing.T, body string) {
		rr := post(h, body)
		if rr.Code >= 500 {
			t.Fatalf("%d: %s", rr.Code, rr.Body.String())
		}
	})
}
