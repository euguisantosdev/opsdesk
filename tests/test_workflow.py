import pytest

from opsdesk.service import NaoEncontrado


def abrir(desk, pri="alta"):
    return desk.criar("PDV sem comunicação", "Loja 0142", "PDV", pri)


def test_criar_chamado(desk):
    t = abrir(desk)
    assert t["id"] == 4701 and t["status"] == "novo" and t["level"] == "N1"
    assert t["sla_remaining_s"] == 4 * 3600
    assert t["events"][0]["kind"] == "aberto"


@pytest.mark.parametrize("campo,valor", [("title", " "), ("requester", ""), ("category", "Outra"), ("priority", "x")])
def test_criar_valida_campos(desk, campo, valor):
    args = dict(title="Falha", requester="Loja 1", category="PDV", priority="alta")
    args[campo] = valor
    with pytest.raises(ValueError):
        desk.criar(**args)


def test_ciclo_completo(desk, relogio):
    t = abrir(desk)
    assert desk.transicao(t["id"], "atendimento")["status"] == "atendimento"
    relogio.avancar(minutes=30)
    assert desk.transicao(t["id"], "aguardando", "Aguardando o usuário")["sla_running"] is False
    relogio.avancar(hours=2)  # pausado: não consome
    t2 = desk.transicao(t["id"], "atendimento")
    assert t2["sla_remaining_s"] == 4 * 3600 - 30 * 60
    r = desk.transicao(t["id"], "resolvido", "Serviço reiniciado")
    assert r["status"] == "resolvido" and r["resolved_at"] and r["sla_state"] == "ok"
    assert [e["kind"] for e in r["events"]] == ["aberto", "atendimento", "aguardando", "atendimento", "resolvido"]


@pytest.mark.parametrize("de,para", [("novo", "resolvido"), ("novo", "aguardando"), ("aguardando", "resolvido")])
def test_transicoes_invalidas(desk, de, para):
    t = abrir(desk)
    if de == "aguardando":
        desk.transicao(t["id"], "atendimento")
        desk.transicao(t["id"], "aguardando")
    with pytest.raises(ValueError):
        desk.transicao(t["id"], para, "x")


def test_resolver_exige_solucao(desk):
    t = abrir(desk)
    desk.transicao(t["id"], "atendimento")
    with pytest.raises(ValueError):
        desk.transicao(t["id"], "resolvido", "  ")


def test_resolvido_nao_reabre(desk):
    t = abrir(desk)
    desk.transicao(t["id"], "atendimento")
    desk.transicao(t["id"], "resolvido", "ok")
    with pytest.raises(ValueError):
        desk.transicao(t["id"], "atendimento")


def test_escalonamento_exige_evidencias(desk):
    t = abrir(desk)
    with pytest.raises(ValueError):
        desk.escalar(t["id"], "")
    e = desk.escalar(t["id"], "Logs com timeout; cabo conferido")
    assert e["level"] == "N2" and e["status"] == "atendimento" and e["assignee"] == "Plantão N2"
    assert e["events"][-1]["kind"] == "escalado"


def test_nao_escala_duas_vezes_nem_resolvido(desk):
    t = abrir(desk)
    desk.escalar(t["id"], "evidências")
    with pytest.raises(ValueError):
        desk.escalar(t["id"], "evidências")
    outro = abrir(desk)
    desk.transicao(outro["id"], "atendimento")
    desk.transicao(outro["id"], "resolvido", "ok")
    with pytest.raises(ValueError):
        desk.escalar(outro["id"], "evidências")


def test_inexistente(desk):
    with pytest.raises(NaoEncontrado):
        desk.obter(1)


def test_listar_ordena_por_sla_e_filtra(desk):
    baixa = abrir(desk, "baixa")
    critica = abrir(desk, "critica")
    assert [t["id"] for t in desk.listar()] == [critica["id"], baixa["id"]]
    assert [t["id"] for t in desk.listar(prioridade="baixa")] == [baixa["id"]]
    assert [t["id"] for t in desk.listar(q="4702")] == [critica["id"]]


def test_metricas(desk, relogio):
    a = abrir(desk, "critica")
    b = abrir(desk, "alta")
    desk.transicao(b["id"], "atendimento")
    relogio.avancar(minutes=50)  # crítica: restam 10 min (<25%) -> risco
    desk.transicao(b["id"], "resolvido", "ok")
    m = desk.metricas()
    assert m["abertos"] == 1 and m["sla_em_risco"] == 1 and m["sla_estourado"] == 0
    assert m["tempo_medio_resolucao_s"] == 50 * 60
    assert m["sla_cumprido_por_nivel"] == {"N1": 100, "N2": None}
    desk.escalar(a["id"], "evidências")
    assert desk.metricas()["escalados_n2"] == 1
