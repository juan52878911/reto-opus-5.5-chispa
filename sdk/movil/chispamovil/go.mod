module chispa/sdk/movil/chispamovil

go 1.27

require (
	chispa/format/chispa3 v0.0.0
	chispa/runtime/l1 v0.0.0
	chispa/runtime/tok v0.0.0
	github.com/juan52878911/chispa/server v0.0.0
	github.com/juan52878911/kindling v0.17.0
)

require github.com/yalue/onnxruntime_go v1.38.0 // indirect

replace (
	chispa/format/chispa3 => ../../../format/chispa3
	chispa/runtime/l1 => ../../../runtime/l1
	chispa/runtime/tok => ../../../runtime/tok
	github.com/juan52878911/chispa/server => ../../../server
)
