"""Gera web/demo-data.json (snapshot fictício) para a demonstração sem servidor."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from opsdesk import seed
from opsdesk.service import Desk, conectar

AGORA = datetime(2026, 11, 4, 15, 30, 0)
con = conectar(":memory:")
seed.popular(con, AGORA)
desk = Desk(con, relogio=lambda: AGORA)
dados = {"generated_at": AGORA.isoformat(), "tickets": desk.listar()}
Path("web/demo-data.json").write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
print("tickets:", len(dados["tickets"]))
