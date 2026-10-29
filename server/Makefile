.PHONY: test bench carga carga-arnes
export GOFLAGS = -mod=mod
export GOPROXY = off

test:
	go vet ./... && go test -race ./...

bench:
	go test ./decide -run '^$$' -bench . -benchtime 2s -cpu 1,4

# Mide con chispa-server en marcha (make -C server serve) y los núcleos que se quiera: GOMAXPROCS=1 o 4.
serve:
	go run ./cmd/chispa-server -config testdata/config.json

carga:
	go run ./cmd/carga -c 8 -d 10s

# Arnés reproducible (ver carga/README.md): make -C server carga-arnes ARGS="-d 10s -n 1"
carga-arnes:
	carga/correr.sh $(ARGS)
