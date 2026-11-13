"""Testes da leitura de chamados: eventos em lote (sem uma consulta por chamado) e validação de tipos."""
import pytest


def abrir(desk, titulo="PDV sem comunicação", pri="alta"):
    return desk.criar(titulo, "Loja 0142", "PDV", pri)


def test_listar_busca_eventos_em_uma_unica_consulta(desk):
    for i in range(5):
        t = abrir(desk, f"Chamado {i}")
        desk.transicao(t["id"], "atendimento")
    consultas = []
    desk.con.set_trace_callback(consultas.append)
    lista = desk.listar()
    desk.con.set_trace_callback(None)
    assert len([c for c in consultas if "FROM events" in c]) == 1
    assert len(lista) == 5 and all(len(t["events"]) == 2 for t in lista)


def test_listar_e_obter_devolvem_os_mesmos_eventos(desk):
    t = abrir(desk)
    desk.transicao(t["id"], "atendimento", "iniciado")
    assert desk.listar()[0]["events"] == desk.obter(t["id"])["events"]


def test_listar_sem_chamados_devolve_lista_vazia(desk):
    assert desk.listar() == []


@pytest.mark.parametrize("campo", ["title", "requester", "description"])
def test_criar_recusa_campo_que_nao_e_texto(desk, campo):
    args = dict(title="Falha", requester="Loja 1", category="PDV", priority="alta")
    args[campo] = 123
    with pytest.raises(ValueError):
        desk.criar(**args)


def test_transicao_recusa_destino_que_nao_e_texto(desk):
    t = abrir(desk)
    with pytest.raises(ValueError):
        desk.transicao(t["id"], ["atendimento"])


def test_escalar_recusa_ator_que_nao_e_texto(desk):
    t = abrir(desk)
    with pytest.raises(ValueError):
        desk.escalar(t["id"], "logs anexados", actor={"nome": "x"})
