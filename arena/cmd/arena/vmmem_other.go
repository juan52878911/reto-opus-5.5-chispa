//go:build !linux

package main

import "context"

// measureVMMem solo funciona en Linux (smaps_rollup); aquí devuelve nil.
func measureVMMem(ctx context.Context) (map[string]int64, error) { return nil, nil }

// measureVMMemDetail idem: nil fuera de Linux.
func measureVMMemDetail(ctx context.Context) (map[string]VMMem, error) { return nil, nil }
