.PHONY: build dataset train arena smoke test clean

build:
	go build -o arena ./cmd/arena

dataset: build
	./arena dataset -out data

train: dataset
	./arena train -data data -models models

arena: train
	@(sleep 2; open http://127.0.0.1:8088 2>/dev/null || true) &
	./arena run

smoke: train
	./arena run -smoke -max-attacks 50 -addr 127.0.0.1:8089 -base-port 9300

test:
	go vet ./... && go test ./...

clean:
	rm -rf arena data models
