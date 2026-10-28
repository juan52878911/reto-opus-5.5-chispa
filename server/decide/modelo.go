package decide

import (
	"fmt"

	"chispa/format/chispa3"
	"chispa/runtime/l1"
)

// Montaje es lo que sale de armar la cascada desde un .chispa v3 (o v2 envuelto).
type Montaje struct {
	L1, L2 Decisor
	Avisos []string // capas que se quedan como stub y por qué
}

// ArmarDesde añade a l0 el modelo de la sección L0TF, o el de L0 si no hay, y monta L1 y L2 con las secciones presentes;
// las que faltan quedan como stub. Con tauDeCalib, el τ de L1 y L2 pasa a ser el tau_escalate
// de CALIB (cfg se modifica); si L2 es L2c y CALIB trae tau_l2c, ese es el τ de L2. tok es el tokenizador de e5 que necesita L2 (puede ser nil).
// f debe seguir abierto mientras se use la cascada.
func ArmarDesde(f *chispa3.Fichero, l0 *L0, cfg *Config, tauDeCalib bool, tok Tokenizador) (Montaje, error) {
	mt := Montaje{L1: NuevoL1(), L2: NuevoL2()}
	if f.Tiene(chispa3.L0TF) {
		// El L0 tfidf es el que entrenó la cabeza conjunta: manda sobre el Chispa de kindling del mismo fichero.
		m, err := f.L0TF()
		if err != nil {
			return mt, fmt.Errorf("sección L0TF: %w", err)
		}
		if err := l0.AnadirTF("sección L0TF", m); err != nil {
			return mt, err
		}
	} else if f.Tiene(chispa3.L0) {
		m, err := f.L0Modelo()
		if err != nil {
			return mt, fmt.Errorf("sección L0: %w", err)
		}
		if err := l0.Anadir("sección L0", m); err != nil {
			return mt, err
		}
	}
	var calib chispa3.Calib
	if f.Tiene(chispa3.CALIB) {
		var err error
		if calib, err = f.Calib(); err != nil {
			return mt, fmt.Errorf("sección CALIB: %w", err)
		}
		if tauDeCalib {
			for i := range cfg.Capas {
				if n := cfg.Capas[i].Nombre; n == "L1" || n == "L2" {
					cfg.Capas[i].Tau = calib.TauEscalate
				}
			}
		}
	}
	if f.Tiene(chispa3.L1) {
		b, err := f.L1()
		if err != nil {
			return mt, fmt.Errorf("sección L1: %w", err)
		}
		m, err := l1.Desde(b)
		if err != nil {
			return mt, fmt.Errorf("sección L1: %w", err)
		}
		mt.L1 = NuevoL1Modelo(m, calib, cfg.CacheEsquemas)
	}
	if f.Tiene(chispa3.L2) && f.Tiene(chispa3.ESQUEMAS) {
		onnx, err := f.L2()
		if err != nil {
			return mt, fmt.Errorf("sección L2: %w", err)
		}
		esq, err := f.Esquemas()
		if err != nil {
			return mt, fmt.Errorf("sección ESQUEMAS: %w", err)
		}
		var conj *chispa3.Conj
		if f.Tiene(chispa3.CONJ) {
			if conj, err = f.Conj(); err != nil {
				return mt, fmt.Errorf("sección CONJ: %w", err)
			}
		}
		d, err := montarL2(onnx, esq, calib, tok, conj)
		if err != nil {
			mt.Avisos = append(mt.Avisos, "L2 queda como stub: "+err.Error())
		} else {
			mt.L2 = d
			aplicarTauL2c(cfg, calib, conj != nil, tauDeCalib)
		}
	}
	return mt, nil
}

// montarL2 monta L2c si hay CONJ y L2 si no.
func montarL2(onnx []byte, esq *chispa3.Esquemas, calib chispa3.Calib, tok Tokenizador, conj *chispa3.Conj) (Decisor, error) {
	if conj == nil {
		return NuevoL2ORT(onnx, esq, calib, tok)
	}
	if tok == nil {
		return nil, ErrSinTokenizador
	}
	ses, err := NuevaSesionORT(onnx)
	if err != nil {
		return nil, err
	}
	base := NuevoL2Con(ses, esq, calib, tok)
	return NuevoL2cCon(base, base, conj), nil
}

// aplicarTauL2c fija el τ de L2 al de la cabeza conjunta si CALIB lo trae. El tau_escalate se calibró para L2 solo.
func aplicarTauL2c(cfg *Config, calib chispa3.Calib, esL2c, tauDeCalib bool) {
	if !tauDeCalib || !esL2c || calib.TauL2c == nil {
		return
	}
	for i := range cfg.Capas {
		if cfg.Capas[i].Nombre == "L2" {
			cfg.Capas[i].Tau = *calib.TauL2c
		}
	}
}
