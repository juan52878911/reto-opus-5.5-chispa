.PHONY: build dataset train arena smoke test clean

build dataset train arena smoke test clean:
	$(MAKE) -C arena $@
