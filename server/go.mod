module github.com/juan52878911/chispa/server

go 1.27

require github.com/juan52878911/kindling v0.17.0

require (
	chispa/format/chispa3 v0.0.0
	chispa/runtime/l1 v0.0.0
	chispa/runtime/tok v0.0.0
)

replace (
	chispa/format/chispa3 => ../format/chispa3
	chispa/runtime/l1 => ../runtime/l1
	chispa/runtime/tok => ../runtime/tok
)
