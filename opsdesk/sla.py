"""Regras de SLA do OpsDesk.

O relógio do SLA corre desde a abertura, pausa enquanto o chamado aguarda o
usuário e para quando o chamado é resolvido.
"""
from datetime import datetime

# Prazo total (em horas) por prioridade.
SLA_HORAS = {"critica": 1, "alta": 4, "media": 8, "baixa": 24}
# Abaixo desta fração do prazo restante, o chamado entra em "risco".
FRACAO_RISCO = 0.25


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def total_s(prioridade: str) -> int:
    if prioridade not in SLA_HORAS:
        raise ValueError(f"Prioridade inválida: {prioridade}")
    return SLA_HORAS[prioridade] * 3600


def decorrido_s(t: dict, agora: datetime) -> float:
    """Segundos de SLA consumidos (descontando as pausas)."""
    fim = parse(t["resolved_at"]) if t.get("resolved_at") else agora
    bruto = (fim - parse(t["created_at"])).total_seconds()
    pausado = float(t.get("paused_s") or 0)
    if t.get("paused_at") and not t.get("resolved_at"):
        pausado += (agora - parse(t["paused_at"])).total_seconds()
    return max(0.0, bruto - pausado)


def restante_s(t: dict, agora: datetime) -> float:
    return total_s(t["priority"]) - decorrido_s(t, agora)


def estado(t: dict, agora: datetime) -> str:
    """'ok', 'risco' ou 'estourado' (para resolvidos: 'ok' se cumpriu o prazo)."""
    rest = restante_s(t, agora)
    if rest < 0:
        return "estourado"
    if t["status"] != "resolvido" and rest < FRACAO_RISCO * total_s(t["priority"]):
        return "risco"
    return "ok"


def correndo(t: dict) -> bool:
    return t["status"] in ("novo", "atendimento")
