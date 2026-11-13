import http.client
import json
import threading
import urllib.error
import urllib.request

import pytest

from opsdesk import server


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    srv = server.servir(str(tmp_path_factory.mktemp("db") / "t.db"), porta=0)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def req(base, metodo, caminho, corpo=None):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    r = urllib.request.Request(base + caminho, data=dados, method=metodo, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_lista_com_dados_de_demonstracao(base):
    s, tickets = req(base, "GET", "/api/tickets")
    assert s == 200 and len(tickets) >= 50
    abertos = [t for t in tickets if t["status"] != "resolvido"]
    assert abertos == sorted(abertos, key=lambda t: t["sla_remaining_s"])


def test_fluxo_pela_api(base):
    s, t = req(base, "POST", "/api/tickets", {"title": "Teste", "requester": "Loja 1", "category": "ERP", "priority": "alta"})
    assert s == 201
    tid = t["id"]
    assert req(base, "POST", f"/api/tickets/{tid}/escalate", {"note": ""})[0] == 400
    s, e = req(base, "POST", f"/api/tickets/{tid}/escalate", {"note": "logs anexados"})
    assert s == 200 and e["level"] == "N2"
    s, r = req(base, "POST", f"/api/tickets/{tid}/transition", {"to": "resolvido", "note": "ok"})
    assert s == 200 and r["status"] == "resolvido"
    assert req(base, "POST", f"/api/tickets/{tid}/transition", {"to": "novo"})[0] == 400


def test_erros(base):
    assert req(base, "GET", "/api/tickets/1")[0] == 404
    assert req(base, "GET", "/api/rota-que-nao-existe")[0] == 404
    assert req(base, "POST", "/api/tickets", {"title": ""})[0] == 400


def test_metricas(base):
    s, m = req(base, "GET", "/api/metrics")
    assert s == 200 and {"abertos", "sla_em_risco", "escalados_n2"} <= set(m)


def test_nao_serve_arquivos_fora_da_pasta_web(base):
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(base + "/..%2fopsdesk%2fservice.py")
    assert e.value.code == 404


def test_corpo_que_nao_e_objeto_json_retorna_400(base):
    assert req(base, "POST", "/api/tickets", [1, 2])[0] == 400


def test_campo_com_tipo_errado_retorna_400(base):
    corpo = {"title": 123, "requester": "Loja 1", "category": "ERP", "priority": "alta"}
    assert req(base, "POST", "/api/tickets", corpo)[0] == 400


def test_destino_de_transicao_que_nao_e_texto_retorna_400(base):
    s, t = req(base, "POST", "/api/tickets", {"title": "Teste", "requester": "Loja 1", "category": "ERP", "priority": "baixa"})
    assert s == 201
    assert req(base, "POST", f"/api/tickets/{t['id']}/transition", {"to": ["resolvido"]})[0] == 400


def test_corpo_grande_demais_retorna_413(base):
    host, porta = base.removeprefix("http://").split(":")
    conn = http.client.HTTPConnection(host, int(porta), timeout=5)
    conn.putrequest("POST", "/api/tickets")
    conn.putheader("Content-Type", "application/json")
    conn.putheader("Content-Length", str(server.MAX_CORPO + 1))
    conn.endheaders()  # só os cabeçalhos: o servidor deve recusar sem esperar o corpo
    assert conn.getresponse().status == 413
    conn.close()
