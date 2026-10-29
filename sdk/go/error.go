package chispa

import (
	"fmt"
	"time"
)

// Códigos propios de ErrorChispa, además de los error.code del servidor (invalid_kind, field_too_long, timeout…).
const (
	CodRed          = "network_error" // no hubo respuesta HTTP
	CodTimeout      = "timeout"       // con Status 0: el timeout propio del cliente; con Status 503: el del servidor
	CodRespuesta    = "bad_response"  // cuerpo ilegible o fuera del contrato
	CodCancelado    = "canceled"      // el ctx del llamador se canceló o venció
	CodHTTPGenerico = "http_error"    // error HTTP sin cuerpo tipado
)

// ErrorChispa es el único tipo de error del cliente (usa errors.As). Codigo es el error.code del servidor o uno de los Cod*.
// Status es el HTTP, o 0 si no hubo respuesta o falló la validación local (que usa los mismos códigos que el servidor).
type ErrorChispa struct {
	Codigo     string
	Mensaje    string
	IDPregunta string
	Status     int
	// RetryAfter es el Retry-After de la respuesta (segundos, con tope de 30 s); 0 si no vino o no era numérico.
	RetryAfter time.Duration
	Causa      error
}

func (e *ErrorChispa) Error() string {
	s := "chispa: "
	if e.Status != 0 {
		s += fmt.Sprintf("HTTP %d: ", e.Status)
	}
	if e.Codigo != "" {
		s += "[" + e.Codigo + "] "
	}
	return s + e.Mensaje
}

func (e *ErrorChispa) Unwrap() error { return e.Causa }

func falla(codigo, mensaje, idPregunta string) *ErrorChispa {
	return &ErrorChispa{Codigo: codigo, Mensaje: mensaje, IDPregunta: idPregunta}
}
