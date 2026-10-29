//go:build ort

package torre

import (
	"errors"
	"fmt"
	"sync"

	ort "github.com/yalue/onnxruntime_go"
)

// RutaORT es la biblioteca compartida de ONNX Runtime (libonnxruntime.so); vacía = la del sistema.
var RutaORT string

var (
	iniciarORT sync.Once
	errIniciar error
)

// IniciarORT inicializa el entorno de ONNX Runtime una sola vez por proceso. Lo comparten L2 (decide.NuevaSesionORT)
// y la torre: onnxruntime_go falla si se inicializa dos veces, y los dos ONNX conviven en el mismo proceso.
// ruta, si no está vacía, fija la biblioteca antes de la primera inicialización.
func IniciarORT(ruta string) error {
	iniciarORT.Do(func() {
		if ruta == "" {
			ruta = RutaORT
		}
		if ruta != "" {
			ort.SetSharedLibraryPath(ruta)
		}
		errIniciar = ort.InitializeEnvironment()
	})
	return errIniciar
}

// sesionORT serializa Run: la sesión dinámica de onnxruntime_go no promete ser reentrante con el mismo objeto.
type sesionORT struct {
	mu sync.Mutex
	s  *ort.DynamicAdvancedSession
}

func (o *sesionORT) Embeber(ids, mascara []int64) ([]float32, error) {
	n := int64(len(ids))
	if n == 0 || int64(len(mascara)) != n {
		return nil, errors.New("torre: ids y máscara vacíos o de distinta longitud")
	}
	tid, err := ort.NewTensor(ort.NewShape(1, n), ids)
	if err != nil {
		return nil, err
	}
	defer tid.Destroy()
	tm, err := ort.NewTensor(ort.NewShape(1, n), mascara)
	if err != nil {
		return nil, err
	}
	defer tm.Destroy()
	salida := []ort.Value{nil}
	o.mu.Lock()
	err = o.s.Run([]ort.Value{tid, tm}, salida)
	o.mu.Unlock()
	if err != nil {
		return nil, err
	}
	defer salida[0].Destroy()
	t, ok := salida[0].(*ort.Tensor[float32])
	if !ok {
		return nil, fmt.Errorf("torre: salida h de tipo %T", salida[0])
	}
	if sh := t.GetShape(); len(sh) != 2 || sh[0] != 1 { // (1, dim)
		return nil, fmt.Errorf("torre: forma de h %v", sh)
	}
	return append([]float32(nil), t.GetData()...), nil
}

func abrirSesion(onnx []byte) (Sesion, error) {
	if err := IniciarORT(""); err != nil {
		return nil, err
	}
	s, err := ort.NewDynamicAdvancedSessionWithONNXData(onnx, []string{"input_ids", "attention_mask"}, []string{"h"}, nil)
	if err != nil {
		return nil, err
	}
	return &sesionORT{s: s}, nil
}
