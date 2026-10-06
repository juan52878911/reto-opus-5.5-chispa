// arena: dataset | train | detector | run. Un solo binario para todo el MVP.
package main

import (
	"flag"
	"fmt"
	"log"
	"os"

	"github.com/juan52878911/chispa/internal/dataset"
	"github.com/juan52878911/chispa/internal/detectors"
	"github.com/juan52878911/chispa/internal/detsrv"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: arena dataset|train|detector|golden|run [flags]")
		os.Exit(2)
	}
	cmd, args := os.Args[1], os.Args[2:]
	var err error
	switch cmd {
	case "dataset":
		fs := flag.NewFlagSet("dataset", flag.ExitOnError)
		out := fs.String("out", "data", "output dir")
		seed := fs.Uint64("seed", 1, "seed")
		fs.Parse(args)
		var st dataset.Stats
		if st, err = dataset.Generate(*out, *seed); err == nil {
			for dim, splits := range st.Counts {
				fmt.Printf("%-10s %v\n", dim, splits)
			}
		}
	case "train":
		fs := flag.NewFlagSet("train", flag.ExitOnError)
		data := fs.String("data", "data", "data dir")
		models := fs.String("models", "models", "models dir")
		fs.Parse(args)
		var infos []detectors.Info
		if infos, err = detectors.TrainAll(*data, *models); err == nil {
			fmt.Printf("%-26s %7s %9s %9s\n", "detector", "train", "test_acc", "coverage")
			for _, i := range infos {
				fmt.Printf("%-26s %7d %9.3f %9.3f\n", i.ID, i.TrainN, i.TestAccuracy, i.TestCoverage)
			}
		}
	case "detector":
		fs := flag.NewFlagSet("detector", flag.ExitOnError)
		dim := fs.String("dim", "", "dimension")
		kind := fs.String("kind", "", "kind")
		models := fs.String("models", "models", "models dir")
		addr := fs.String("addr", "127.0.0.1:0", "listen addr")
		fs.String("id", "", "replica id (default <dim>-<kind>)")
		fs.Parse(args)
		id := fs.Lookup("id").Value.String()
		if id == "" {
			id = detectors.ID(*dim, *kind)
		}
		if *dim == "" {
			err = detsrv.Serve(*addr, "", "", nil) // vacío: espera /configure (microVM)
		} else {
			err = detsrv.Serve(*addr, id, *dim, func() (detectors.Detector, error) { return detectors.Load(*models, *dim, *kind) })
		}
	case "golden":
		err = golden(args)
	case "run":
		err = run(args)
	default:
		err = fmt.Errorf("unknown command %q", cmd)
	}
	if err != nil {
		log.Fatal(err)
	}
}
