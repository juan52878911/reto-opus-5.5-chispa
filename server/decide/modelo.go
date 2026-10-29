package decide

import (
	"encoding/binary"
	"fmt"

	"chispa/format/chispa3"
	"chispa/runtime/l1"
	"github.com/juan52878911/chispa/server/torre"
)

// TokenizadorPasaje es el tokenizador de e5 con «passage: » (runtime/tok.TokenizarPasaje) que necesita la torre al vuelo.
// El Tokenizador que se pasa a ArmarDesde lo puede implementar además de IDs; sin él no se monta la torre.
type TokenizadorPasaje = torre.Tokenizador

// OpcionArmado ajusta ArmarDesde; sirve para sustituir ORT por piezas falsas en las pruebas.
type OpcionArmado func(*opcionesArmado)

type opcionesArmado struct {
	ses    SesionS
	torres CodificadorTorre
}

// ConSesionS monta L2 sobre esta sesión en lugar de abrir el ONNX de la sección L2 con ORT.
func ConSesionS(s SesionS) OpcionArmado { return func(o *opcionesArmado) { o.ses = s } }

// ConCodificadorTorre usa este codificador de torres en lugar de abrir el ONNX de la sección TORR con ORT.
func ConCodificadorTorre(c CodificadorTorre) OpcionArmado {
	return func(o *opcionesArmado) { o.torres = c }
}

// Montaje es lo que sale de armar la cascada desde un .chispa v3 (o v2 envuelto).
type Montaje struct {
	L1, L2 Decisor
	Avisos []string // capas que se quedan como stub y por qué
}

// ArmarDesde añade a l0 el modelo de la sección L0TF, o el de L0 si no hay, y monta L1 y L2 con las secciones presentes;
// las que faltan quedan como stub. Con tauDeCalib, el τ de L1 y L2 pasa a ser el tau_escalate
// de CALIB (cfg se modifica); si L2 es L2c y CALIB trae tau_l2c, ese es el τ de L2. tok es el tokenizador de e5 que necesita L2 (puede ser nil).
// Si el .chispa trae la sección TORR, L2 calcula al vuelo las torres de los esquemas que ESQUEMAS no trae (L2.ConTorres,
// caché de cfg.CacheTorres torres, tope de cfg.MaxTorresNuevas por petición); sin ella, un esquema nuevo queda sin opinión de L2 como antes. Hace falta que tok
// implemente TokenizadorPasaje: si no, la torre no se monta y se avisa.
// f debe seguir abierto mientras se use la cascada.
func ArmarDesde(f *chispa3.Fichero, l0 *L0, cfg *Config, tauDeCalib bool, tok Tokenizador, opts ...OpcionArmado) (Montaje, error) {
	var op opcionesArmado
	for _, o := range opts {
		o(&op)
	}
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
	var sopl *chispa3.Sopl1
	if f.Tiene(chispa3.SOPL1) {
		var err error
		if sopl, err = f.Sopl1(); err != nil {
			return mt, fmt.Errorf("sección SOPL1: %w", err)
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
		mt.L1 = NuevoL1Modelo(m, calib, cfg.CacheEsquemas).ConSoporte(sopl, cfg.L1ShrinkageLambda)
		if sopl != nil && sopl.Dim() != m.Dim() {
			mt.Avisos = append(mt.Avisos, fmt.Sprintf("SOPL1 de dimensión %d y L1 de %d: L1 no mezcla el soporte", sopl.Dim(), m.Dim()))
		}
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
		base, err := montarL2(onnx, esq, calib, tok, op.ses)
		if err != nil {
			mt.Avisos = append(mt.Avisos, "L2 queda como stub: "+err.Error())
		} else {
			if f.Tiene(chispa3.TORR) {
				if err := montarTorres(f, base, tok, op.torres, cfg.CacheTorres, cfg.MaxTorresNuevas); err != nil {
					mt.Avisos = append(mt.Avisos, "sin torres al vuelo: "+err.Error())
				}
			}
			mt.L2 = Decisor(base)
			if conj != nil {
				mt.L2 = NuevoL2cCon(base, base, conj).ConSoporte(sopl, cfg.L2ShrinkageLambda)
			}
			aplicarTauL2c(cfg, calib, conj != nil, tauDeCalib)
		}
	}
	return mt, nil
}

// montarL2 monta el L2 base sobre ses, o sobre el ONNX de la sección L2 si ses es nil.
func montarL2(onnx []byte, esq *chispa3.Esquemas, calib chispa3.Calib, tok Tokenizador, ses SesionS) (*L2, error) {
	if tok == nil {
		return nil, ErrSinTokenizador
	}
	if ses == nil {
		var err error
		if ses, err = NuevaSesionORT(onnx); err != nil {
			return nil, err
		}
	}
	return NuevoL2Con(ses, esq, calib, tok), nil
}

// montarTorres lee la sección TORR y activa las torres al vuelo en l2; enc, si no es nil, sustituye al ONNX.
func montarTorres(f *chispa3.Fichero, l2 *L2, tok Tokenizador, enc CodificadorTorre, cache, maxNuevas int) error {
	t, err := f.Torre()
	if err != nil {
		return fmt.Errorf("sección TORR: %w", err)
	}
	if t.Dim != l2.esq.Dim() {
		return fmt.Errorf("sección TORR: dimensión %d, pero las ranuras de L2 son de %d", t.Dim, l2.esq.Dim())
	}
	b, err := f.Bytes(chispa3.TORR)
	if err != nil {
		return err
	}
	if err := torre.ValidarPrefijo(binary.LittleEndian.Uint32(b), t.Prefijo); err != nil {
		return err
	}
	if enc == nil {
		tp, ok := tok.(TokenizadorPasaje)
		if !ok {
			return fmt.Errorf("el tokenizador no ofrece el modo passage")
		}
		if enc, err = torre.Abrir(t, tp); err != nil {
			return err
		}
	}
	if cache <= 0 {
		cache = CacheTorresPorDefecto
	}
	l2.ConTorres(enc, cache).ConMaxTorresNuevas(maxNuevas)
	return nil
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
