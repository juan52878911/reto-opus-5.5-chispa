package main

// VMMem es la memoria de una microVM medida desde el host (bytes).
type VMMem struct {
	Pss int64 // reparto justo: las páginas compartidas CoW se dividen entre mapeadores
	Rss int64
}
