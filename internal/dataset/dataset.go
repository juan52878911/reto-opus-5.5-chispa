// Package dataset genera un dataset sintético, determinista y por plantillas,
// de mensajes tipo WhatsApp en español colombiano.
package dataset

import (
	"bufio"
	"encoding/json"
	"fmt"
	"math/rand/v2"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"github.com/juan52878911/chispa/contracts"
)

// Stats: dim -> split -> label -> n.
type Stats struct {
	Counts map[string]map[string]map[string]int
}

const perTemplate = 18

var urlRe = regexp.MustCompile(`(?i)(https?://|www\.|\b[a-z0-9-]+\.(com|co|net|org|ly|xyz|top|info)\b)`)

// Fields calcula los campos derivados del texto.
func Fields(text string) map[string]any {
	n := 0
	for _, r := range text {
		if isEmoji(r) {
			n++
		}
	}
	return map[string]any{
		"has_url":  urlRe.MatchString(text),
		"n_emojis": n,
		"len":      len([]rune(text)),
	}
}

func isEmoji(r rune) bool {
	return (r >= 0x1F300 && r <= 0x1FAFF) || (r >= 0x2600 && r <= 0x27BF) || r == 0x2B50 || r == 0x2764
}

var slots = map[string][]string{
	"nombre":   {"Juan", "Camila", "Andrés", "Valentina", "Sebas", "Laura", "Santi", "Daniela", "Carlos", "Paola", "Mateo", "Luisa", "Felipe", "Juli"},
	"monto":    {"$50.000", "$120.000", "2 millones", "500 lucas", "$1.500.000", "30 luca", "$85.000", "$300.000", "10 millones", "$20.000"},
	"url":      {"bit.ly/x7Kq2", "http://premio-gratis.xyz/cobra", "www.ganadinero.top", "tinyurl.com/a9Zp", "https://bancol0mbia-seguro.com/login", "http://ofertas-ya.info/r", "wa-premios.net/claim", "cutt.ly/Vv3k"},
	"producto": {"iPhone 15", "Rolex", "tennis Nike", "licuadora", "moto Yamaha", "PlayStation 5", "portátil", "bono Éxito", "TV de 55", "bicicleta"},
	"hora":     {"las 3", "las 5pm", "las 8", "mediodía", "las 10 de la noche", "las 7am", "las 4:30", "la 1pm"},
	"lugar":    {"la casa", "el centro", "la oficina", "el parque", "Unicentro", "el Éxito", "la universidad", "el apartamento", "la finca", "Chapinero"},
	"emoji":    {"😂", "🔥", "💰", "🙏", "😅", "👍", "🎉", "😍", "🚨", "😬", "🤑"},
	"banco":    {"Bancolombia", "Davivienda", "Nequi", "Daviplata", "BBVA", "Banco de Bogotá"},
	"dia":      {"lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo", "mañana", "hoy"},
	"tema":     {"matemáticas", "el contrato", "la presentación", "el informe", "la tarea", "el proyecto", "la factura"},
	"num":      {"3", "5", "7", "10", "15", "20"},
}

var (
	slotRe  = regexp.MustCompile(`\{[a-z]+\}`)
	abbrevs = []struct{ from, to string }{
		{"por favor", "porfa"}, {"porque", "xq"}, {"que", "q"}, {"qué", "q"}, {"te quiero mucho", "tqm"},
		{"para", "pa"}, {"también", "tmb"}, {"mensaje", "msj"}, {"con", "c/"}, {"quiero", "kiero"},
		{"que", "k"}, {"gracias", "grax"}, {"hola", "ola"}, {"ahora", "ahorita"},
	}
	accentRepl = strings.NewReplacer("á", "a", "é", "e", "í", "i", "ó", "o", "ú", "u", "ñ", "n", "¿", "", "¡", "", "Á", "A", "É", "E", "Í", "I", "Ó", "O", "Ú", "U")
	tailEmoji  = []string{" 😂", " 🙏", " 😅", " 👍", " 🔥", " 😬", " 🙌"}
)

func fill(t string, r *rand.Rand) string {
	chosen := map[string]string{}
	return slotRe.ReplaceAllStringFunc(t, func(m string) string {
		k := m[1 : len(m)-1]
		if v, ok := chosen[k]; ok {
			return v
		}
		l := slots[k]
		if len(l) == 0 {
			return m
		}
		v := l[r.IntN(len(l))]
		chosen[k] = v
		return v
	})
}

func noise(s string, r *rand.Rand) string {
	if r.IntN(100) < 35 {
		s = strings.ToLower(s)
	}
	if r.IntN(100) < 30 {
		for _, a := range abbrevs {
			if r.IntN(2) == 0 {
				s = strings.Replace(s, " "+a.from+" ", " "+a.to+" ", 1)
			}
		}
	}
	if r.IntN(100) < 15 {
		w := strings.Fields(s)
		if len(w) > 0 {
			i := r.IntN(len(w))
			rs := []rune(w[i])
			if len(rs) > 3 && !urlRe.MatchString(w[i]) {
				j := 1 + r.IntN(len(rs)-2)
				rs[j], rs[j+1] = rs[j+1], rs[j]
				w[i] = string(rs)
				s = strings.Join(w, " ")
			}
		}
	}
	if r.IntN(100) < 30 {
		s = accentRepl.Replace(s)
	}
	if r.IntN(100) < 20 {
		s += tailEmoji[r.IntN(len(tailEmoji))]
	}
	return s
}

// splitOf asigna cada plantilla a un split de forma determinista.
func splitAssign(n int, r *rand.Rand) []string {
	perm := r.Perm(n)
	nt := max(2, (n+5)/10)
	nv := max(2, (n+5)/10)
	out := make([]string, n)
	for k, idx := range perm {
		switch {
		case k < nt:
			out[idx] = "test"
		case k < nt+nv:
			out[idx] = "valid"
		default:
			out[idx] = "train"
		}
	}
	return out
}

// Generate escribe el dataset en outDir.
func Generate(outDir string, seed uint64) (Stats, error) {
	r := rand.New(rand.NewPCG(seed, seed^0x9e37))
	st := Stats{Counts: map[string]map[string]map[string]int{}}
	for _, dim := range contracts.DimensionOrder {
		st.Counts[dim] = map[string]map[string]int{}
		bySplit := map[string][]contracts.Example{}
		for _, label := range contracts.Dimensions[dim] {
			tpls := templates[dim+"/"+label]
			if len(tpls) == 0 {
				return st, fmt.Errorf("sin plantillas para %s/%s", dim, label)
			}
			assign := splitAssign(len(tpls), r)
			for ti, t := range tpls {
				sp := assign[ti]
				seen := map[string]bool{}
				for k := 0; k < perTemplate; k++ {
					var txt string
					for try := 0; try < 8; try++ {
						txt = noise(fill(t, r), r)
						if !seen[txt] {
							break
						}
					}
					seen[txt] = true
					bySplit[sp] = append(bySplit[sp], contracts.Example{
						ID:       fmt.Sprintf("%s-%s-%d-%d", dim, label, ti, k),
						Text:     txt,
						Label:    label,
						Fields:   Fields(txt),
						Template: fmt.Sprintf("%s/%s/%d", dim, label, ti),
					})
					if st.Counts[dim][sp] == nil {
						st.Counts[dim][sp] = map[string]int{}
					}
					st.Counts[dim][sp][label]++
				}
			}
		}
		for _, sp := range []string{"train", "valid", "test"} {
			ex := bySplit[sp]
			r.Shuffle(len(ex), func(i, j int) { ex[i], ex[j] = ex[j], ex[i] })
			if err := writeJSONL(filepath.Join(outDir, dim, sp+".jsonl"), ex); err != nil {
				return st, err
			}
		}
	}
	err := os.WriteFile(filepath.Join(outDir, "benign.txt"), []byte(strings.Join(BenignPool(), "\n")+"\n"), 0o644)
	return st, err
}

func writeJSONL(path string, ex []contracts.Example) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	w := bufio.NewWriter(f)
	enc := json.NewEncoder(w)
	for _, e := range ex {
		if err := enc.Encode(e); err != nil {
			f.Close()
			return err
		}
	}
	if err := w.Flush(); err != nil {
		f.Close()
		return err
	}
	return f.Close()
}

var benignBase = []string{
	"jaja sí, mañana nos vemos en la casa de mi tía", "¿ya almorzaste?", "toca madrugar mañana pa la vuelta", "qué más parce, ¿cómo vas?",
	"de una, nos vemos en el parque", "bacano el partido de anoche", "me prestas el cargador porfa", "ya llegué a la casa, todo bien",
	"mi mamá hizo ajiaco hoy", "jajaja no puedo con ese video", "¿vamos a tomar tinto más tarde?", "el bus se demoró una eternidad",
	"estoy viendo la novela con mi abuela", "mañana hay pico y placa, ojo", "llave, me pasas la tarea de sociales?", "nos vemos el sábado en la finca",
	"qué pereza el trancón en la 80", "ya compré las empanadas para la reunión", "acabo de salir del gimnasio", "el perro se comió mi tarea, literal",
	"feliz cumpleaños, que la pases bacano", "¿viste el gol de Colombia?", "voy para la panadería, ¿quieres algo?", "hoy llovió toda la tarde",
	"tqm, gracias por acompañarme ayer", "estoy en el centro comercial con mi hermana", "me dio hambre, pedimos pizza?", "toca estudiar pa el parcial del lunes",
	"jaja sí, mi primo ya viene en camino", "dejé las llaves en la oficina, qué embarrada", "¿a qué hora es la misa mañana?", "hace un calor horrible hoy",
	"me voy a dormir temprano hoy", "pasé por el mercado y compré aguacate", "el domingo hay almuerzo donde la abuela", "ya casi termino de lavar la ropa",
	"qué buena la película que vimos", "mañana te cuento con calma", "estoy escuchando vallenato, qué rico", "me prestas tu paraguas, porfa?",
	"el niño ya se quedó dormido", "vamos a caminar por la ciclovía el domingo", "jaja eso fue épico", "acabo de ver a Sebas en la calle",
	"¿me guardas puesto en la clase?", "compré arepas y queso pa la comida", "hoy me tocó caminar mucho", "ya pagué el recibo del agua, todo en orden",
	"la reunión de padres es el jueves", "gracias por la ayuda con la mudanza", "voy a hacer jugo de lulo", "¿qué hay de cena hoy?",
	"mi tía llega el viernes en flota", "el profe dejó taller pa la próxima semana", "ya cambié el turno con Camila", "uf, qué sueño tengo",
	"jajaja tú siempre con tus cosas", "me voy en Transmilenio, nos vemos allá", "¿alguien tiene la foto del grupo?", "oye, ¿cómo salió el examen?",
	"mañana madrugo a hacer deporte", "acabo de probar el café nuevo, está delicioso", "mi hermano me regaló un libro", "estoy cocinando sancocho hoy",
	"le dije a mi jefe que llego tarde, hay trancón", "este fin de semana toca limpiar la casa", "¿ya viste la serie nueva?", "jaja, qué risa lo de ayer",
	"los niños están jugando en el parque", "pasa por mí a las 6, porfa", "me encantó el regalo, gracias", "ya es viernes, por fin",
	"estoy en la fila del banco, qué pereza", "el domingo vamos a piscina", "me duele un poco la cabeza, voy a descansar", "te mando la foto en un rato",
	"qué lindo el atardecer hoy", "mi papá arregló la bicicleta", "en la tarde paso por tu casa", "jaja, ni me digas, yo también me quedé dormido",
	"tengo cita con el odontólogo el martes", "me quedé sin datos, estoy con wifi", "la abuela está cocinando buñuelos", "bueno parce, hablamos luego",
	"ya terminé el informe, lo reviso mañana", "estoy en la biblioteca estudiando", "vamos por helado después de clase", "hoy es el cumpleaños de mi prima",
	"toca comprar leche y pan", "el partido empieza a las 8", "buenos días, ¿cómo amaneciste?", "buenas noches, que descanses",
	"mañana llevo el postre", "jaja ese man es un crack", "pasé a saludar a los vecinos", "estamos organizando el paseo para diciembre",
	"me encanta esta canción", "ya limpié la cocina", "voy a sacar al perro a pasear", "estoy esperando el domicilio",
	"la clase de inglés estuvo buena", "hoy hay reunión de equipo a la 1", "recuerda traer el cuaderno", "bacano, gracias por avisarme",
}

// BenignPool devuelve ~200 fragmentos inocentes para rellenar mensajes.
func BenignPool() []string {
	out := make([]string, 0, len(benignBase)*2)
	out = append(out, benignBase...)
	pre := []string{"jaja ", "oye, ", "ah, ", "mira, ", "pues ", "bueno, "}
	for i, b := range benignBase {
		if i%2 == 0 {
			p := pre[i/2%len(pre)]
			out = append(out, p+strings.ToLower(b[:1])+b[1:])
		}
	}
	return out
}
