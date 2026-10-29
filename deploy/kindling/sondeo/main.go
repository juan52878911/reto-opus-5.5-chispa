// sondeo: healthcheck sin shell ni curl. Sale 0 si GET /healthz responde 200 con status ok.
package main

import (
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"
)

func main() {
	puerto := os.Getenv("CHISPA_PUERTO")
	if puerto == "" {
		puerto = "8090"
	}
	c := http.Client{Timeout: 2 * time.Second}
	r, err := c.Get("http://127.0.0.1:" + puerto + "/healthz")
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	defer r.Body.Close()
	b, _ := io.ReadAll(io.LimitReader(r.Body, 1024))
	if r.StatusCode != 200 || !strings.Contains(string(b), `"ok"`) {
		fmt.Fprintf(os.Stderr, "healthz %d %s\n", r.StatusCode, b)
		os.Exit(1)
	}
}
