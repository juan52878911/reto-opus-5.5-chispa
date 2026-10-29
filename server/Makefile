.PHONY: test bench carga carga-arnes
export GOFLAGS = -mod=mod
export GOPROXY = off

# Los tests con el tokenizador real usan CHISPA_TOK (o $$TMPDIR/e5.chispa-tok); sin él se saltan, y aquí se cuenta cuántos.
test:
	go vet ./... && go test -race -v ./... 2>&1 | tee .test.log | grep -E '^(--- FAIL|FAIL|panic)' ; \
	  r=$$(grep -cE '^(--- FAIL|FAIL|panic)' .test.log); \
	  echo "ok=$$(grep -cE '^--- PASS' .test.log) saltados=$$(grep -cE '^--- SKIP' .test.log) fallos=$$r"; \
	  grep -E '^--- SKIP' .test.log; rm -f .test.log; [ "$$r" = 0 ]

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
