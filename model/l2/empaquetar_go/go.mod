module chispa/model/l2/empaquetar_go

go 1.27

require (
	chispa/format/chispa3 v0.0.0
	chispa/runtime/l1 v0.0.0
	chispa/runtime/tok v0.0.0
	chispa/runtime/torre v0.0.0
	github.com/juan52878911/chispa/server v0.0.0
	github.com/juan52878911/kindling v0.17.0
)

replace chispa/format/chispa3 => ../../../format/chispa3

replace github.com/juan52878911/chispa/server => ../../../server

replace chispa/runtime/l1 => ../../../runtime/l1

replace chispa/runtime/tok => ../../../runtime/tok

replace chispa/runtime/torre => ../../../runtime/torre
