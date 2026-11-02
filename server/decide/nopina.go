package decide

// Causas de «sin opinión» de una capa (etiqueta «causa» de chispa_capa_no_opina_total).
const (
	CausaSinTorre        = "sin_torre"            // esquema ausente de ESQUEMAS y el .chispa no trae TORR (o falta -tok/ORT): L2 no puede calcular torres
	CausaTipoNoSoportado = "tipo_no_soportado"    // la capa no decide ese tipo (p. ej. multi sin cabeza calibrada)
	CausaScoreIds        = "score_ids_no_validos" // score con ids que no son 1..K
	CausaSinModelo       = "sin_modelo"           // la capa no tiene modelo cargado
	CausaEsquemaNoVisto  = "esquema_no_entrenado" // L0 sin modelo para ese esquema
	CausaSinOpinion      = "sin_opinion"          // otra causa
)

// ExplicaNoOpina lo implementan las capas que saben decir por qué no opinaron.
type ExplicaNoOpina interface {
	CausaNoOpina(p Pregunta) string
}

func causaNoOpina(d Decisor, p Pregunta) string {
	if !scoreValido(p) {
		return CausaScoreIds
	}
	if e, ok := d.(ExplicaNoOpina); ok {
		return e.CausaNoOpina(p)
	}
	return CausaSinOpinion
}

// CausaNoOpina: L2 sin sesión ONNX, multi sin cabeza, o esquema nuevo sin torres al vuelo.
func (l *L2) CausaNoOpina(p Pregunta) string {
	switch {
	case l == nil || l.ses == nil:
		return CausaSinModelo
	case p.Kind == KindMulti:
		if _, opina := l.multi.opinaMultiL2(p, l.calib, nil); !opina {
			return CausaTipoNoSoportado
		}
	}
	if l.torres == nil && l.esquemaNuevo(p) {
		return CausaSinTorre
	}
	return CausaSinOpinion
}

// TorreAlVuelo dice si L2 puede calcular la torre de un esquema nuevo.
func (l *L2) TorreAlVuelo() bool { return l != nil && l.torres != nil }

// Activa dice si L2 tiene modelo cargado.
func (l *L2) Activa() bool { return l != nil && l.ses != nil }

func (l *L1) CausaNoOpina(p Pregunta) string {
	if l == nil || l.m == nil {
		return CausaSinModelo
	}
	return CausaSinOpinion
}

// Activa dice si L1 tiene modelo cargado.
func (l *L1) Activa() bool { return l != nil && l.m != nil }

func (l *L0) CausaNoOpina(p Pregunta) string {
	if p.Kind == KindMulti {
		return CausaTipoNoSoportado
	}
	if l.buscar(p) == nil {
		return CausaEsquemaNoVisto
	}
	return CausaSinOpinion
}

// Activa dice si L0 tiene algún modelo entrenado.
func (l *L0) Activa() bool { return l != nil && len(l.modelos) > 0 }

// Capacidades es lo que el servidor puede decir de su modelo: qué capas tienen modelo (las Stub no) y si L2 calcula torres al vuelo.
type Capacidades struct {
	Capas        map[string]bool `json:"capas"`
	TorreAlVuelo bool            `json:"torre_al_vuelo"`
}

func activaCapa(d Decisor) bool {
	if a, ok := d.(interface{ Activa() bool }); ok {
		return a.Activa()
	}
	_, stub := d.(Stub)
	return !stub
}

// Capacidades de la cascada armada; /healthz las publica.
func (c *Cascada) Capacidades() Capacidades {
	cp := Capacidades{Capas: map[string]bool{}}
	for _, k := range c.capas {
		cp.Capas[k.d.Nombre()] = activaCapa(k.d)
		if t, ok := k.d.(interface{ TorreAlVuelo() bool }); ok && t.TorreAlVuelo() {
			cp.TorreAlVuelo = true
		}
	}
	return cp
}
