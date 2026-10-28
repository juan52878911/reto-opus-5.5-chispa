package main

import "math"

func sigmoid(z float64) float64 { return 1 / (1 + math.Exp(-z)) }

func argmax(v []float64) int {
	k := 0
	for i, x := range v {
		if x > v[k] {
			k = i
		}
	}
	return k
}
