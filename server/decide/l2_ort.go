//go:build ort

package decide

import (
	"context"
	"errors"
	"fmt"

	ort "github.com/yalue/onnxruntime_go"

	"chispa/format/chispa3"
	"github.com/juan52878911/chispa/server/torre"
)

// RutaORT es la biblioteca compartida de ONNX Runtime (libonnxruntime.so); vacía = la del sistema.
var RutaORT string

// sesionORT serializa Run: la sesión dinámica de onnxruntime_go no promete ser reentrante con el mismo objeto.
// El turno es un semáforo de capacidad 1 (no un mutex) para poder esperarlo con select sobre ctx.Done(): una petición
// cuyo plazo vence en la cola se va sin ejecutar ORT.
type sesionORT struct {
	sem chan struct{}
	s   *ort.DynamicAdvancedSession
}

// turno espera el semáforo o el ctx, lo que pase antes; tras ganar el semáforo comprueba otra vez el ctx (select elige al azar si ambos están listos).
func (o *sesionORT) turno(ctx context.Context) error {
	if err := ctx.Err(); err != nil {
		return err
	}
	select {
	case o.sem <- struct{}{}:
		if err := ctx.Err(); err != nil {
			<-o.sem
			return err
		}
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

// Close destruye la sesión de ORT; idempotente y seguro frente a un Run en curso (espera a que termine).
func (o *sesionORT) Close() error {
	o.sem <- struct{}{} // sin ctx: Close espera a que termine el Run en curso
	defer func() { <-o.sem }()
	if o.s == nil {
		return nil
	}
	err := o.s.Destroy()
	o.s = nil
	return err
}

func (o *sesionORT) Ranuras(ids []int64) ([][]float32, error) {
	return o.RanurasCtx(context.Background(), ids)
}

// RanurasCtx es Ranuras que deja de esperar el turno de ORT cuando el ctx vence (SesionSCtx).
func (o *sesionORT) RanurasCtx(ctx context.Context, ids []int64) ([][]float32, error) {
	n := int64(len(ids))
	if n == 0 {
		return nil, errors.New("L2: mensaje sin tokens")
	}
	mask := make([]int64, n)
	for i := range mask {
		mask[i] = 1
	}
	tid, err := ort.NewTensor(ort.NewShape(1, n), ids)
	if err != nil {
		return nil, err
	}
	defer tid.Destroy()
	tm, err := ort.NewTensor(ort.NewShape(1, n), mask)
	if err != nil {
		return nil, err
	}
	defer tm.Destroy()
	salida := []ort.Value{nil}
	if err := o.turno(ctx); err != nil {
		return nil, err
	}
	if o.s == nil {
		<-o.sem
		return nil, errors.New("L2: sesión cerrada")
	}
	err = o.s.Run([]ort.Value{tid, tm}, salida)
	<-o.sem
	if err != nil {
		return nil, err
	}
	defer salida[0].Destroy()
	t, ok := salida[0].(*ort.Tensor[float32])
	if !ok {
		return nil, fmt.Errorf("L2: salida S de tipo %T", salida[0])
	}
	sh := t.GetShape() // (1, K, d)
	if len(sh) != 3 || sh[0] != 1 {
		return nil, fmt.Errorf("L2: forma de S %v", sh)
	}
	K, d := int(sh[1]), int(sh[2])
	datos := append([]float32(nil), t.GetData()...)
	S := make([][]float32, K)
	for k := range S {
		S[k] = datos[k*d : (k+1)*d]
	}
	return S, nil
}

// NuevaSesionORT abre el ONNX de la sección L2 con ONNX Runtime.
func NuevaSesionORT(onnx []byte) (SesionS, error) {
	// El entorno de ORT se inicializa una vez por proceso y lo comparte la torre (server/torre).
	if err := torre.IniciarORT(RutaORT); err != nil {
		return nil, err
	}
	s, err := ort.NewDynamicAdvancedSessionWithONNXData(onnx, []string{"input_ids", "attention_mask"}, []string{"S"}, nil)
	if err != nil {
		return nil, err
	}
	return &sesionORT{s: s, sem: make(chan struct{}, 1)}, nil
}

// NuevoL2ORT abre el ONNX de la sección L2 con ONNX Runtime y monta el decisor.
func NuevoL2ORT(onnx []byte, esq *chispa3.Esquemas, calib chispa3.Calib, tok Tokenizador) (Decisor, error) {
	if tok == nil {
		return nil, ErrSinTokenizador
	}
	ses, err := NuevaSesionORT(onnx)
	if err != nil {
		return nil, err
	}
	return NuevoL2Con(ses, esq, calib, tok), nil
}
