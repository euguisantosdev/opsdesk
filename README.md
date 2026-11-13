# OpsDesk

Service desk de demonstração com **SLA em tempo real**, **escalonamento N1 → N2** e quadro de chamados.
Projeto pessoal, com **dados fictícios** — não representa sistema de nenhuma empresa.

[![tests](https://github.com/euguisantosdev/opsdesk/actions/workflows/tests.yml/badge.svg)](https://github.com/euguisantosdev/opsdesk/actions/workflows/tests.yml)

![Painel](docs/painel.png)

| Quadro de chamados | Detalhe com histórico e SLA |
|---|---|
| ![Quadro](docs/quadro.png) | ![Detalhe](docs/detalhe.png) |

## O que o sistema faz

- **Ciclo do chamado:** Novo → Em atendimento → Aguardando usuário → Resolvido, com histórico (quem fez o quê e quando).
- **Motor de SLA por prioridade:** Crítica 1h · Alta 4h · Média 8h · Baixa 24h. O relógio **pausa** enquanto o chamado aguarda o usuário e **para** ao resolver. Abaixo de 25% do prazo o chamado entra em **risco**; passou do prazo, **estourado**.
- **Escalonamento N1 → N2** só com evidências registradas; **resolver** exige a descrição da solução.
- **Quadro com arrastar e soltar** (transições inválidas são recusadas) e painel com indicadores.
- **API JSON** (`/api/tickets`, `/api/tickets/{id}/transition`, `/api/tickets/{id}/escalate`, `/api/metrics`).

## Arquitetura

```
web/ (HTML + CSS + JS puro)  ──fetch──►  opsdesk/server.py (API JSON, http.server)
                                              │
                                  opsdesk/service.py  (regras: ciclo, escalonamento, métricas)
                                  opsdesk/sla.py      (cálculo de SLA, funções puras)
                                              │
                                          SQLite (data/opsdesk.db, criado e populado na 1ª execução)
```

Sem dependências externas: apenas a biblioteca padrão do Python. Sem a API, a página roda em **modo demonstração** com `web/demo-data.json`.

## Como rodar

```bash
python -m opsdesk.server        # abre em http://127.0.0.1:8000
```

Testes (44 testes: SLA, ciclo do chamado, consultas e API):

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Requer Python 3.10 ou superior. O CI do GitHub roda com Python 3.12.

Gerar de novo os dados da demonstração: `python export_demo.py`.

## API

| Método e rota | O que faz |
|---|---|
| `GET /api/tickets` | Lista os chamados (filtros opcionais: `status`, `priority`, `level`, `q`) |
| `GET /api/tickets/{id}` | Abre um chamado, com histórico e estado do SLA |
| `POST /api/tickets` | Cria um chamado (`title`, `requester`, `category`, `priority`) |
| `POST /api/tickets/{id}/transition` | Muda o estado (`to`, `note`); resolver exige `note` com a solução |
| `POST /api/tickets/{id}/escalate` | Escala de N1 para N2 (`note` com as evidências) |
| `GET /api/metrics` | Indicadores do painel |

Erros de validação retornam `400`; chamado inexistente, `404`; corpo acima de 64 KiB, `413`.

## Decisões de projeto

- **Regras de negócio em Python puro e testadas**, separadas da interface; o front só exibe e chama a API.
- **SQL direto (sqlite3)** para ficar explícito o modelo de dados (`tickets` e `events`).
- **Transições de estado declaradas em uma tabela** (`TRANSICOES`), em vez de condicionais espalhadas.
- **Relógio injetável**: os testes controlam o tempo e verificam a pausa do SLA sem esperar.
- **Segurança básica:** consultas parametrizadas, escape de HTML no front, bloqueio de caminhos fora de `web/`, limite de tamanho do corpo da requisição e recusa de campos que não sejam texto.
- **Leitura em lote:** os eventos de todos os chamados são buscados em uma consulta por lote, e não uma consulta por chamado (há um teste que garante isso).

## Limitações conhecidas

Este é um projeto de demonstração, não um sistema de produção.

- **Sem autenticação:** o campo `actor` das ações vem da requisição e não é verificado.
- **Sem migrações de banco** (o esquema é criado na primeira execução) e **sem paginação** nas listagens.
- As métricas carregam todos os chamados e seus eventos.
- Um bloqueio global serializa as requisições; o servidor da biblioteca padrão não é indicado para carga real.
- Datas em UTC, sem fuso horário explícito.

## Próximos passos

Base de conhecimento ligada aos chamados, log de auditoria detalhado, integração com o [SRE Auto-Heal](https://github.com/euguisantosdev/sre-autoheal) e uma versão do backend em **Java e Spring Boot** com PostgreSQL (planejada; ainda não iniciada).
