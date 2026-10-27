"""THX-01 (doofz): decisiones tipadas calibradas; checkpoint raíz (el subdirectorio `multilingual` no está en el snapshot)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common, _decision

if __name__ == "__main__":
    common.main("thx01", lambda t, tr, a: _decision.Decision("~/hf/hub/models--doofz--THX-01/snapshots/*", t),
                "ver config del repo (sin README ni LICENSE en el snapshot)")
