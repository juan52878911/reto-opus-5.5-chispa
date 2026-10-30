package decide

import (
	"strings"
	"unicode"
)

// NormalizarMayusculas aplica el contrato de normalización de mayúsculas (docs/contrato-normalizacion.md): si el texto
// tiene al menos 8 letras y más del 70 % están en mayúscula, devuelve el texto en minúsculas; si no, lo deja igual.
// Solo se aplica al mensaje que entra a L2, antes de «query: », de tokenizar y de ventanear.
func NormalizarMayusculas(texto string) string {
	letras, mayus := 0, 0
	for _, c := range texto {
		if unicode.IsLetter(c) {
			letras++
			if unicode.IsUpper(c) {
				mayus++
			}
		}
	}
	if letras >= 8 && mayus*10 > 7*letras {
		return strings.ToLower(texto)
	}
	return texto
}
