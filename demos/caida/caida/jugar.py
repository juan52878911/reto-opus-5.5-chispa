"""`python3 -m caida.jugar --url … --salida traza.jsonl`: juega y graba la traza (solo biblioteca estándar)."""
from .traza import main

if __name__ == "__main__":
    raise SystemExit(main())
