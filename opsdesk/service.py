"""Regras de negócio: ciclo do chamado, escalonamento e métricas."""
import sqlite3
from datetime import datetime, timezone

from . import sla

STATUS = ("novo", "atendimento", "aguardando", "resolvido")
PRIORIDADES = tuple(sla.SLA_HORAS)
TRANSICOES = {
    "novo": {"atendimento"},
    "atendimento": {"aguardando", "resolvido"},
    "aguardando": {"atendimento"},
    "resolvido": set(),
}
CATEGORIAS = ("PDV", "ERP", "Active Directory", "Rede", "Impressora", "Acesso", "Integração/API")

SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
  id INTEGER PRIMARY KEY, title TEXT NOT NULL, description TEXT DEFAULT '',
  requester TEXT NOT NULL, category TEXT NOT NULL, priority TEXT NOT NULL,
  level TEXT NOT NULL DEFAULT 'N1', status TEXT NOT NULL DEFAULT 'novo',
  assignee TEXT DEFAULT '', created_at TEXT NOT NULL, paused_at TEXT,
  paused_s REAL NOT NULL DEFAULT 0, resolved_at TEXT);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id INTEGER NOT NULL REFERENCES tickets(id),
  at TEXT NOT NULL, actor TEXT NOT NULL, kind TEXT NOT NULL, note TEXT DEFAULT '');
CREATE INDEX IF NOT EXISTS ix_events_ticket ON events(ticket_id);
"""


class NaoEncontrado(Exception):
    pass


def agora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def conectar(caminho: str) -> sqlite3.Connection:
    con = sqlite3.connect(caminho, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


class Desk:
    def __init__(self, con: sqlite3.Connection, relogio=agora):
        self.con = con
        self.relogio = relogio

    # ---------- leitura ----------
    def _ticket(self, row: sqlite3.Row, now: datetime) -> dict:
        t = dict(row)
        t["events"] = [dict(e) for e in self.con.execute(
            "SELECT at, actor, kind, note FROM events WHERE ticket_id=? ORDER BY id", (t["id"],))]
        t["sla_total_s"] = sla.total_s(t["priority"])
        t["sla_remaining_s"] = round(sla.restante_s(t, now))
        t["sla_state"] = sla.estado(t, now)
        t["sla_running"] = sla.correndo(t)
        return t

    def obter(self, tid: int) -> dict:
        row = self.con.execute("SELECT * FROM tickets WHERE id=?", (tid,)).fetchone()
        if not row:
            raise NaoEncontrado(f"Chamado {tid} não existe")
        return self._ticket(row, self.relogio())

    def listar(self, status=None, prioridade=None, nivel=None, q=None) -> list[dict]:
        sql, args = "SELECT * FROM tickets WHERE 1=1", []
        for col, val in (("status", status), ("priority", prioridade), ("level", nivel)):
            if val:
                sql += f" AND {col}=?"
                args.append(val)
        if q:
            sql += " AND (title LIKE ? OR requester LIKE ? OR CAST(id AS TEXT) LIKE ?)"
            args += [f"%{q}%"] * 3
        now = self.relogio()
        out = [self._ticket(r, now) for r in self.con.execute(sql, args)]
        # abertos primeiro, menor SLA restante primeiro
        out.sort(key=lambda t: (t["status"] == "resolvido", t["sla_remaining_s"]))
        return out

    # ---------- escrita ----------
    def _evento(self, tid, actor, kind, note=""):
        self.con.execute("INSERT INTO events(ticket_id, at, actor, kind, note) VALUES (?,?,?,?,?)",
                         (tid, self.relogio().isoformat(), actor, kind, note))

    def criar(self, title, requester, category, priority, description="", actor="Sistema") -> dict:
        title, requester = (title or "").strip(), (requester or "").strip()
        if not title or not requester:
            raise ValueError("Título e solicitante são obrigatórios")
        if priority not in PRIORIDADES:
            raise ValueError("Prioridade inválida")
        if category not in CATEGORIAS:
            raise ValueError("Categoria inválida")
        prox = (self.con.execute("SELECT COALESCE(MAX(id), 4700) FROM tickets").fetchone()[0]) + 1
        self.con.execute(
            "INSERT INTO tickets(id, title, description, requester, category, priority, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (prox, title, description, requester, category, priority, self.relogio().isoformat()))
        self._evento(prox, actor, "aberto", f"Chamado aberto por {requester}")
        self.con.commit()
        return self.obter(prox)

    def transicao(self, tid: int, para: str, nota: str = "", actor: str = "Analista") -> dict:
        t = self.obter(tid)
        if para not in TRANSICOES.get(t["status"], set()):
            raise ValueError(f"Transição inválida: {t['status']} → {para}")
        nota = (nota or "").strip()
        if para == "resolvido" and not nota:
            raise ValueError("Descreva a solução para resolver o chamado")
        now = self.relogio()
        if para == "aguardando":
            self.con.execute("UPDATE tickets SET paused_at=? WHERE id=?", (now.isoformat(), tid))
        if t["status"] == "aguardando":
            extra = (now - sla.parse(t["paused_at"])).total_seconds()
            self.con.execute("UPDATE tickets SET paused_s=paused_s+?, paused_at=NULL WHERE id=?", (extra, tid))
        if para == "resolvido":
            self.con.execute("UPDATE tickets SET resolved_at=? WHERE id=?", (now.isoformat(), tid))
        assignee = t["assignee"] or actor
        self.con.execute("UPDATE tickets SET status=?, assignee=? WHERE id=?", (para, assignee, tid))
        self._evento(tid, actor, para, nota)
        self.con.commit()
        return self.obter(tid)

    def escalar(self, tid: int, nota: str, actor: str = "Analista N1") -> dict:
        t = self.obter(tid)
        if t["status"] == "resolvido":
            raise ValueError("Chamado resolvido não pode ser escalado")
        if t["level"] != "N1":
            raise ValueError("Chamado já está no N2")
        if not (nota or "").strip():
            raise ValueError("Informe as evidências para escalar ao N2")
        novo_status = "atendimento" if t["status"] == "novo" else t["status"]
        self.con.execute("UPDATE tickets SET level='N2', status=?, assignee='Plantão N2' WHERE id=?",
                         (novo_status, tid))
        self._evento(tid, actor, "escalado", nota.strip())
        self.con.commit()
        return self.obter(tid)

    # ---------- métricas ----------
    def metricas(self) -> dict:
        ts = self.listar()
        abertos = [t for t in ts if t["status"] != "resolvido"]
        resolvidos = [t for t in ts if t["status"] == "resolvido"]
        tempos = [sla.decorrido_s(t, self.relogio()) for t in resolvidos]
        por_nivel = {}
        for nivel in ("N1", "N2"):
            rs = [t for t in resolvidos if t["level"] == nivel]
            cumpridos = [t for t in rs if t["sla_state"] == "ok"]
            por_nivel[nivel] = round(100 * len(cumpridos) / len(rs)) if rs else None
        return {
            "abertos": len(abertos),
            "sla_em_risco": sum(1 for t in abertos if t["sla_state"] == "risco"),
            "sla_estourado": sum(1 for t in abertos if t["sla_state"] == "estourado"),
            "escalados_n2": sum(1 for t in abertos if t["level"] == "N2"),
            "tempo_medio_resolucao_s": round(sum(tempos) / len(tempos)) if tempos else None,
            "sla_cumprido_por_nivel": por_nivel,
        }
