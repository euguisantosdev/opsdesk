"""Dados FICTÍCIOS para demonstração. Nenhum dado real de empresa ou pessoa."""
import random
from datetime import datetime, timedelta

from . import sla
from .service import CATEGORIAS

LOJAS = [f"Loja {n:04d}" for n in (142, 87, 233, 18, 310, 64, 205, 12)]
SETORES = ["Financeiro", "RH", "Suporte", "Comercial", "Operações"]

MODELOS = [  # (título, categoria, prioridade)
    ("PDV sem comunicação com o servidor", "PDV", "critica"),
    ("Timeout na integração de pedidos (API)", "Integração/API", "critica"),
    ("Relatório do ERP com valores divergentes", "ERP", "alta"),
    ("Conta bloqueada no Active Directory", "Active Directory", "alta"),
    ("Falha de login no ERP", "ERP", "alta"),
    ("Impressora fiscal não responde", "Impressora", "media"),
    ("Acesso a pasta compartilhada", "Acesso", "media"),
    ("Lentidão no sistema de caixa", "PDV", "media"),
    ("Solicitação de acesso à VPN", "Acesso", "media"),
    ("Monitor sem sinal no caixa", "PDV", "baixa"),
    ("Pinpad não conecta", "PDV", "alta"),
    ("Troca de senha de rede", "Active Directory", "baixa"),
    ("Switch com porta intermitente", "Rede", "media"),
    ("Consulta SQL lenta no relatório diário", "ERP", "alta"),
    ("Instalar certificado digital", "Acesso", "baixa"),
]
SOLUCOES = [
    "Reinício do serviço de comunicação; conferido o log sem novos erros.",
    "Cadastro corrigido via SQL após validar duplicidade; usuário confirmou.",
    "Cabo substituído e porta do switch reconfigurada.",
    "Senha redefinida e conta desbloqueada no AD; orientado o usuário.",
    "Driver reinstalado e teste de impressão aprovado.",
    "Permissão ajustada no grupo correto; acesso validado.",
]
EVIDENCIAS = [
    "Ping falha e há timeout nos logs do serviço; cabo e energia já conferidos.",
    "Erro 504 na chamada externa; sem falha local. Anexados logs e horário do incidente.",
    "Consulta SQL retorna registros duplicados; N1 não tem acesso para corrigir a base.",
]


def popular(con, agora: datetime, semente: int = 42, n: int = 56) -> None:
    rnd = random.Random(semente)
    prox = 4700

    def inserir(t, eventos):
        con.execute("INSERT INTO tickets(id,title,description,requester,category,priority,level,status,"
                    "assignee,created_at,paused_at,paused_s,resolved_at) VALUES "
                    "(:id,:title,:description,:requester,:category,:priority,:level,:status,:assignee,"
                    ":created_at,:paused_at,:paused_s,:resolved_at)", t)
        for at, actor, kind, nota in eventos:
            con.execute("INSERT INTO events(ticket_id,at,actor,kind,note) VALUES (?,?,?,?,?)",
                        (t["id"], at.isoformat(), actor, kind, nota))

    def base(titulo, cat, pri, criado, **kw):
        nonlocal prox
        prox += 1
        t = dict(id=prox, title=titulo, description="", requester=rnd.choice(LOJAS), category=cat,
                 priority=pri, level="N1", status="novo", assignee="", created_at=criado.isoformat(),
                 paused_at=None, paused_s=0.0, resolved_at=None)
        t.update(kw)
        return t

    # Cenários fixos: dois críticos perto de estourar, um em risco, etc.
    fixos = [
        ("PDV sem comunicação com o servidor", "PDV", "critica", 14 * 60, "atendimento", "N2"),
        ("Timeout na integração de pedidos (API)", "Integração/API", "critica", 41 * 60, "atendimento", "N2"),
        ("Relatório do ERP com valores divergentes", "ERP", "alta", 115 * 60, "atendimento", "N2"),
        ("Conta bloqueada no Active Directory", "Active Directory", "alta", 150 * 60, "aguardando", "N1"),
    ]
    for titulo, cat, pri, resta, status, nivel in fixos:
        criado = agora - timedelta(seconds=sla.total_s(pri) - resta)
        t = base(titulo, cat, pri, criado, status=status, level=nivel,
                 assignee="Plantão N2" if nivel == "N2" else "Ana Souza")
        ev = [(criado, "Sistema", "aberto", f"Chamado aberto por {t['requester']}"),
              (criado + timedelta(minutes=8), "Ana Souza", "atendimento", "Triagem N1 iniciada")]
        if nivel == "N2":
            ev.append((criado + timedelta(minutes=14), "Ana Souza", "escalado", rnd.choice(EVIDENCIAS)))
        if status == "aguardando":
            t["paused_at"] = (agora - timedelta(minutes=20)).isoformat()
            ev.append((agora - timedelta(minutes=20), "Ana Souza", "aguardando", "Aguardando retorno do usuário"))
        inserir(t, ev)

    # Demais chamados, espalhados nas últimas 36h.
    while prox - 4700 < n:
        titulo, cat, pri = rnd.choice(MODELOS)
        criado = agora - timedelta(minutes=rnd.randint(5, 36 * 60))
        sorte = rnd.random()
        total = sla.total_s(pri)
        t = base(titulo, cat, pri, criado, description=f"Aberto por {rnd.choice(SETORES)}.")
        ev = [(criado, "Sistema", "aberto", f"Chamado aberto por {t['requester']}")]
        if sorte < 0.62:  # resolvido
            fim = criado + timedelta(seconds=total * rnd.choice([0.3, 0.5, 0.7, 0.9, 1.15]))
            if fim > agora:
                fim = agora - timedelta(minutes=2)
            t.update(status="resolvido", resolved_at=fim.isoformat(), assignee=rnd.choice(["Ana Souza", "Caio Lima"]))
            ev.append((criado + timedelta(minutes=6), t["assignee"], "atendimento", "Triagem N1 iniciada"))
            if rnd.random() < 0.3:
                t["level"] = "N2"
                ev.append((criado + timedelta(minutes=20), t["assignee"], "escalado", rnd.choice(EVIDENCIAS)))
            ev.append((fim, t["assignee"], "resolvido", rnd.choice(SOLUCOES)))
        elif sorte < 0.80:
            t["status"] = "novo"
        else:
            t.update(status="atendimento", assignee=rnd.choice(["Ana Souza", "Caio Lima"]))
            ev.append((criado + timedelta(minutes=6), t["assignee"], "atendimento", "Triagem N1 iniciada"))
        # evita novos já estourados demais: recentes
        if t["status"] != "resolvido" and (agora - criado).total_seconds() > total * 0.9:
            t["created_at"] = (agora - timedelta(seconds=total * rnd.uniform(0.2, 0.7))).isoformat()
            ev[0] = (datetime.fromisoformat(t["created_at"]), *ev[0][1:])
            ev = ev[:1] + [(datetime.fromisoformat(t["created_at"]) + timedelta(minutes=6), *e[1:]) for e in ev[1:]]
        inserir(t, ev)
    con.commit()
