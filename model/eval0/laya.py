"""Laya multilingual (convaiinnovations): mismo formato que THX-01 (rl_agent_config.json); se carga con el runtime thx01."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common, _decision

if __name__ == "__main__":
    common.main("laya", lambda t, tr, a: _decision.Decision("~/hf/hub/models--convaiinnovations--laya-multilingual/snapshots/*", t),
                "no consta (el snapshot no trae README ni LICENSE)")
