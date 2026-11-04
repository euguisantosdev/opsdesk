from datetime import datetime

import pytest

from opsdesk import sla

T0 = datetime(2026, 11, 4, 12, 0, 0)


def chamado(prioridade="alta", **kw):
    t = {"priority": prioridade, "status": "atendimento", "created_at": T0.isoformat(),
         "paused_s": 0, "paused_at": None, "resolved_at": None}
    t.update(kw)
    return t


@pytest.mark.parametrize("pri,horas", [("critica", 1), ("alta", 4), ("media", 8), ("baixa", 24)])
def test_prazo_total_por_prioridade(pri, horas):
    assert sla.total_s(pri) == horas * 3600


def test_prioridade_invalida():
    with pytest.raises(ValueError):
        sla.total_s("urgentissima")


def test_restante_diminui_com_o_tempo():
    t = chamado("alta")
    assert sla.restante_s(t, datetime(2026, 11, 4, 13, 0, 0)) == 3 * 3600


def test_estados_ok_risco_estourado():
    t = chamado("alta")  # 4h; risco abaixo de 1h restante
    assert sla.estado(t, datetime(2026, 11, 4, 13, 0, 0)) == "ok"
    assert sla.estado(t, datetime(2026, 11, 4, 15, 30, 0)) == "risco"
    assert sla.estado(t, datetime(2026, 11, 4, 16, 1, 0)) == "estourado"


def test_pausa_nao_consome_sla():
    t = chamado("alta", status="aguardando", paused_at=datetime(2026, 11, 4, 13, 0, 0).isoformat())
    # 3h depois, mas pausado desde 13h: só 1h consumida
    assert sla.decorrido_s(t, datetime(2026, 11, 4, 15, 0, 0)) == 3600


def test_pausas_anteriores_sao_descontadas():
    t = chamado("alta", paused_s=1800)
    assert sla.decorrido_s(t, datetime(2026, 11, 4, 13, 0, 0)) == 1800


def test_resolvido_congela_o_relogio():
    t = chamado("critica", status="resolvido", resolved_at=datetime(2026, 11, 4, 12, 40, 0).isoformat())
    assert sla.decorrido_s(t, datetime(2026, 11, 5, 12, 0, 0)) == 40 * 60
    assert sla.estado(t, datetime(2026, 11, 5, 12, 0, 0)) == "ok"
    t["resolved_at"] = datetime(2026, 11, 4, 13, 30, 0).isoformat()
    assert sla.estado(t, datetime(2026, 11, 5, 12, 0, 0)) == "estourado"


def test_relogio_so_corre_em_novo_e_atendimento():
    assert sla.correndo(chamado(status="novo"))
    assert sla.correndo(chamado(status="atendimento"))
    assert not sla.correndo(chamado(status="aguardando"))
    assert not sla.correndo(chamado(status="resolvido"))
