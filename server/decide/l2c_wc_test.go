package decide

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

type decisorRespaldoWC struct {
	conf             float64
	respaldo, nuevo  bool
	tauResp, tauCabe float64
}

func (decisorRespaldoWC) Nombre() string { return "L2" }
func (d decisorRespaldoWC) Decidir(ctx context.Context, p Pregunta) (Respuesta, error) {
	r, _, err := d.DecidirConOrigen(ctx, p, nil)
	return r, err
}
func (d decisorRespaldoWC) DecidirCon(ctx context.Context, p Pregunta, pr Previas) (Respuesta, error) {
	r, _, err := d.DecidirConOrigen(ctx, p, pr)
	return r, err
}
func (d decisorRespaldoWC) DecidirConOrigen(context.Context, Pregunta, Previas) (Respuesta, bool, error) {
	return Respuesta{Answer: "a", Probs: map[string]float64{"a": d.conf}, Conf: d.conf, EsquemaNuevo: d.nuevo}, d.respaldo, nil
}
func (d decisorRespaldoWC) TauRespaldo() (float64, float64, bool) { return d.tauResp, d.tauCabe, true }

// Dorado común: respaldo de L2c de esquema nuevo sin τ de esquema nuevo se corta con tau_escalate_l2 (como Kotlin/Swift).
func TestL2cRespaldoEsquemaNuevoSinTauNuevoWC(t *testing.T) {
	raw, err := os.ReadFile(filepath.Join(dirDorados, "tau_respaldo_nuevo.json"))
	if err != nil {
		t.Fatal(err)
	}
	var g struct {
		TauL2c float64 `json:"tau_l2c"`
		TauEsc float64 `json:"tau_escalate_l2"`
		Casos  []struct {
			Nombre   string   `json:"nombre"`
			Respaldo bool     `json:"respaldo"`
			Nuevo    bool     `json:"esquema_nuevo"`
			TauNuevo *float64 `json:"tau_esquema_nuevo"`
			Conf     float64  `json:"conf"`
			Escala   bool     `json:"escala"`
		} `json:"casos"`
	}
	if err := json.Unmarshal(raw, &g); err != nil {
		t.Fatal(err)
	}
	for _, c := range g.Casos {
		d := decisorRespaldoWC{conf: c.Conf, respaldo: c.Respaldo, nuevo: c.Nuevo, tauResp: g.TauEsc, tauCabe: g.TauL2c}
		cas, err := NuevaCascadaConTauNuevo([]Capa{{"L2", g.TauL2c}}, []Decisor{d}, NuevasMetricas(), c.TauNuevo)
		if err != nil {
			t.Fatal(err)
		}
		if r := cas.Decidir(context.Background(), Pregunta{ID: "q", Kind: KindChoice}); r.Escalate != c.Escala {
			t.Errorf("%s: escalate=%v, quiero %v", c.Nombre, r.Escalate, c.Escala)
		}
	}
}
