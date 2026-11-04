/* OpsDesk — front-end sem dependências.
   Fala com a API Python quando ela existe; sem servidor, usa demo-data.json (dados fictícios). */
(() => {
  'use strict';

  const $ = (s, r = document) => r.querySelector(s);
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const PRI = { critica: 'Crítica', alta: 'Alta', media: 'Média', baixa: 'Baixa' };
  const PCLS = { critica: 'crit', alta: 'alta', media: 'med', baixa: 'low' };
  const COLS = [['novo', 'Novos'], ['atendimento', 'Em atendimento'], ['aguardando', 'Aguardando usuário'], ['resolvido', 'Resolvidos']];
  const TRANS = { novo: ['atendimento'], atendimento: ['aguardando', 'resolvido'], aguardando: ['atendimento'], resolvido: [] };
  const CATS = ['PDV', 'ERP', 'Active Directory', 'Rede', 'Impressora', 'Acesso', 'Integração/API'];
  const EV_LBL = { aberto: 'Chamado aberto', atendimento: 'Em atendimento', aguardando: 'Aguardando usuário', escalado: 'Escalado para N2', resolvido: 'Resolvido' };
  const AVC = ['a1', 'a2', 'a3', 'a4'];
  const ICON = {
    painel: '<path d="M3 3h7v9H3zM14 3h7v5h-7zM14 12h7v9h-7zM3 16h7v5H3z"/>',
    chamados: '<path d="M3 9a2 2 0 0 0 0 6v3h18v-3a2 2 0 0 1 0-6V6H3z"/><path d="M13 6v12" stroke-dasharray="2 3"/>',
    sla: '<circle cx="12" cy="13" r="8"/><path d="M12 9v4l2.5 2M9 2h6"/>',
    kb: '<path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v17H6.5A2.5 2.5 0 0 0 4 21.5z"/><path d="M4 21.5V4.5"/>',
    auto: '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2"/>',
  };

  const S = { tickets: [], mode: 'api', baseNow: Date.now(), view: 'painel', filtro: 'todos', q: '', sel: null, sig: '' };

  /* ---------- tempo ---------- */
  const nowMs = () => S.baseNow + (Date.now() - S.t0);
  const parse = (ts) => Date.parse(ts + 'Z');
  const hhmm = (ts) => new Date(parse(ts)).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  const dia = (ts) => new Date(parse(ts)).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
  const isoNow = () => new Date(nowMs()).toISOString().slice(0, 19);
  const rem = (t) => (t.sla_running ? t.sla_remaining_s - (Date.now() - t._at) / 1000 : t.sla_remaining_s);
  function estado(t) {
    const r = rem(t);
    if (r < 0) return 'estourado';
    if (t.status !== 'resolvido' && r < 0.25 * t.sla_total_s) return 'risco';
    return 'ok';
  }
  function fmt(sec) {
    const neg = sec < 0, s = Math.floor(Math.abs(sec));
    const p = (n) => String(n).padStart(2, '0');
    return (neg ? '−' : '') + p(Math.floor(s / 3600)) + ':' + p(Math.floor((s % 3600) / 60)) + ':' + p(s % 60);
  }
  function fmtDur(sec) {
    if (sec == null) return '—';
    const h = Math.floor(sec / 3600), m = Math.round((sec % 3600) / 60);
    return h ? `${h}h ${String(m).padStart(2, '0')}m` : `${m}m`;
  }
  const slaCell = (t) => {
    if (t.status === 'resolvido') return `<span class="sla ${t.sla_state === 'ok' ? 's-ok' : 's-estourado'}">${t.sla_state === 'ok' ? '✓ no prazo' : '✕ estourado'}</span>`;
    if (!t.sla_running) return `<span class="sla s-pausa" title="SLA pausado">⏸ ${fmt(rem(t))}</span>`;
    return `<span class="sla s-${estado(t)}" data-sla="${t.id}">${fmt(rem(t))}</span>`;
  };
  const avCls = (t) => AVC[t.id % AVC.length];

  /* ---------- dados ---------- */
  async function carregar() {
    try {
      const r = await fetch('/api/tickets', { cache: 'no-store' });
      if (!r.ok) throw new Error('sem api');
      S.tickets = await r.json();
      S.mode = 'api';
      S.baseNow = Date.now();
    } catch {
      const r = await fetch('demo-data.json', { cache: 'no-store' });
      const d = await r.json();
      S.tickets = d.tickets;
      S.mode = 'demo';
      S.baseNow = parse(d.generated_at);
    }
    S.t0 = Date.now();
    S.tickets.forEach((t) => (t._at = S.t0));
  }

  async function chamar(path, body) {
    const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const j = await r.json();
    if (!r.ok) throw new Error(j.erro || 'Erro');
    return j;
  }
  const upsert = (t) => {
    t._at = Date.now();
    const i = S.tickets.findIndex((x) => x.id === t.id);
    if (i >= 0) S.tickets[i] = t; else S.tickets.push(t);
    return t;
  };
  const congelar = (t) => { t.sla_remaining_s = rem(t); t._at = Date.now(); };

  async function transicao(t, para, nota) {
    nota = (nota || '').trim();
    if (S.mode === 'api') return upsert(await chamar(`/api/tickets/${t.id}/transition`, { to: para, note: nota }));
    if (!TRANS[t.status].includes(para)) throw new Error(`Transição inválida: ${t.status} → ${para}`);
    if (para === 'resolvido' && !nota) throw new Error('Descreva a solução para resolver o chamado');
    congelar(t);
    t.status = para;
    t.sla_running = para === 'novo' || para === 'atendimento';
    if (!t.assignee) t.assignee = 'Analista';
    if (para === 'resolvido') { t.resolved_at = isoNow(); t.sla_state = t.sla_remaining_s >= 0 ? 'ok' : 'estourado'; }
    t.events.push({ at: isoNow(), actor: t.assignee, kind: para, note: nota });
    return t;
  }
  async function escalar(t, nota) {
    nota = (nota || '').trim();
    if (S.mode === 'api') return upsert(await chamar(`/api/tickets/${t.id}/escalate`, { note: nota }));
    if (t.status === 'resolvido') throw new Error('Chamado resolvido não pode ser escalado');
    if (t.level !== 'N1') throw new Error('Chamado já está no N2');
    if (!nota) throw new Error('Informe as evidências para escalar ao N2');
    congelar(t);
    if (t.status === 'novo') { t.status = 'atendimento'; t.sla_running = true; }
    t.level = 'N2'; t.assignee = 'Plantão N2';
    t.events.push({ at: isoNow(), actor: 'Analista N1', kind: 'escalado', note: nota });
    return t;
  }
  async function criar(d) {
    if (S.mode === 'api') return upsert(await chamar('/api/tickets', d));
    const total = { critica: 1, alta: 4, media: 8, baixa: 24 }[d.priority] * 3600;
    const id = Math.max(4700, ...S.tickets.map((x) => x.id)) + 1;
    return upsert({ id, title: d.title.trim(), description: '', requester: d.requester.trim(), category: d.category, priority: d.priority,
      level: 'N1', status: 'novo', assignee: '', created_at: isoNow(), resolved_at: null, sla_total_s: total, sla_remaining_s: total,
      sla_state: 'ok', sla_running: true, events: [{ at: isoNow(), actor: 'Sistema', kind: 'aberto', note: `Chamado aberto por ${d.requester.trim()}` }] });
  }

  /* ---------- derivados ---------- */
  const abertos = () => S.tickets.filter((t) => t.status !== 'resolvido');
  const porSla = (a, b) => rem(a) - rem(b);
  function filtrados() {
    const q = S.q.trim().toLowerCase();
    return S.tickets.filter((t) => {
      if (q && !(`${t.id} ${t.title} ${t.requester} ${t.category}`.toLowerCase().includes(q))) return false;
      if (S.filtro === 'criticos') return t.priority === 'critica';
      if (S.filtro === 'risco') return t.status !== 'resolvido' && estado(t) !== 'ok';
      if (S.filtro === 'n2') return t.level === 'N2';
      return true;
    });
  }
  function metricas() {
    const ab = abertos(), res = S.tickets.filter((t) => t.status === 'resolvido');
    const dur = res.map((t) => (parse(t.resolved_at) - parse(t.created_at)) / 1000);
    const cumpr = (rs) => (rs.length ? Math.round((100 * rs.filter((t) => t.sla_state === 'ok').length) / rs.length) : null);
    return {
      abertos: ab.length,
      novas24: S.tickets.filter((t) => nowMs() - parse(t.created_at) < 864e5).length,
      risco: ab.filter((t) => estado(t) === 'risco').length,
      estourados: ab.filter((t) => estado(t) === 'estourado').length,
      n2: ab.filter((t) => t.level === 'N2').length,
      medio: dur.length ? dur.reduce((a, b) => a + b, 0) / dur.length : null,
      resolvidos: res.length,
      cumpr: { N1: cumpr(res.filter((t) => t.level === 'N1')), N2: cumpr(res.filter((t) => t.level === 'N2')), Geral: cumpr(res) },
    };
  }
  const assinatura = () => abertos().map((t) => t.id + estado(t)).join(',');

  /* ---------- views ---------- */
  function pri(t) { return `<span class="p ${PCLS[t.priority]}">${PRI[t.priority]}</span>`; }

  function chartVolume() {
    const W = 440, H = 150, base = nowMs(), N = 24, v = new Array(N).fill(0);
    S.tickets.forEach((t) => { const h = Math.floor((base - parse(t.created_at)) / 36e5); if (h >= 0 && h < N) v[N - 1 - h]++; });
    const max = Math.max(4, ...v), x = (i) => (i / (N - 1)) * W, y = (n) => H - 14 - (n / max) * (H - 36);
    let d = `M${x(0)} ${y(v[0])}`;
    for (let i = 1; i < N; i++) { const cx = (x(i - 1) + x(i)) / 2; d += ` C${cx} ${y(v[i - 1])} ${cx} ${y(v[i])} ${x(i)} ${y(v[i])}`; }
    const pk = v.indexOf(Math.max(...v));
    return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Chamados abertos por hora nas últimas 24 horas">
      <defs><linearGradient id="g" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#6d8cff" stop-opacity=".45"/><stop offset="1" stop-color="#6d8cff" stop-opacity="0"/></linearGradient></defs>
      <g stroke="#1e2433">${[0, 1, 2].map((i) => `<path d="M0 ${24 + i * 40}H${W}"/>`).join('')}</g>
      <path d="${d} V${H} H0Z" fill="url(#g)"/><path d="${d}" fill="none" stroke="#8aa4ff" stroke-width="2.5"/>
      <circle cx="${x(pk)}" cy="${y(v[pk])}" r="5" fill="#8aa4ff"/>
      <text x="${Math.min(Math.max(x(pk), 20), W - 20)}" y="${Math.max(y(v[pk]) - 10, 12)}" text-anchor="middle" fill="#b6bfd6" font-size="11">${v[pk]}</text></svg>`;
  }

  function viewPainel() {
    const m = metricas();
    const fila = abertos().sort(porSla).slice(0, 7);
    const bar = (nome, p, cor) => `<div class="row-sb"><span>${nome}</span><span class="${p == null ? 's-pausa' : p >= 85 ? 's-ok' : 's-risco'}">${p == null ? '—' : p + '%'}</span></div>
      <div class="bar"><i style="width:${p || 0}%;background:${cor}"></i></div>`;
    return `
    <div class="kpis">
      <div class="card kpi"><div class="l">Chamados abertos</div><div class="v">${m.abertos}</div><div class="d">${m.novas24} criados nas últimas 24h</div></div>
      <div class="card kpi"><div class="l">SLA em risco</div><div class="v" style="color:${m.risco ? 'var(--warn)' : 'inherit'}">${m.risco}</div><div class="d">${m.estourados} estourado${m.estourados === 1 ? '' : 's'}</div></div>
      <div class="card kpi"><div class="l">Tempo médio de resolução</div><div class="v">${fmtDur(m.medio)}</div><div class="d">${m.resolvidos} resolvidos</div></div>
      <div class="card kpi"><div class="l">Escalados para N2</div><div class="v">${m.n2}</div><div class="d">${m.abertos ? Math.round((100 * m.n2) / m.abertos) : 0}% da fila aberta</div></div>
    </div>
    <div class="grid">
      <div class="card"><h3>Fila prioritária <span>ordenada por SLA restante</span></h3>
        ${fila.length ? `<div style="overflow-x:auto"><table class="tbl"><thead><tr><th>ID</th><th>Assunto</th><th>Prioridade</th><th class="hide-s">Nível</th><th>SLA restante</th></tr></thead><tbody>
        ${fila.map((t) => `<tr data-open="${t.id}" tabindex="0"><td class="id">#${t.id}</td><td class="ti">${esc(t.title)}</td><td>${pri(t)}</td><td class="hide-s">${t.level}</td><td>${slaCell(t)}</td></tr>`).join('')}
        </tbody></table></div>` : '<p class="empty">Nenhum chamado aberto.</p>'}</div>
      <div class="stack">
        <div class="card"><h3>Volume por hora <span>últimas 24h</span></h3>${chartVolume()}</div>
        <div class="card"><h3>SLA cumprido <span>chamados resolvidos</span></h3>
          ${bar('N1 · Atendimento', m.cumpr.N1, 'linear-gradient(90deg,#34d399,#38bdf8)')}
          ${bar('N2 · Sustentação', m.cumpr.N2, 'linear-gradient(90deg,#6d8cff,#a78bfa)')}
          ${bar('Geral', m.cumpr.Geral, 'linear-gradient(90deg,#fbbf24,#fb923c)')}</div>
      </div>
    </div>`;
  }

  function cardT(t) {
    return `<div class="t" draggable="true" data-open="${t.id}" data-id="${t.id}" tabindex="0">
      <div class="id">#${t.id} · ${esc(t.requester)}</div><div class="ti">${esc(t.title)}</div>
      <div class="row">${pri(t)}<span class="lvl ${t.level === 'N2' ? 'n2' : ''}">${t.level}</span>${slaCell(t)}<span class="av ${t.assignee ? avCls(t) : ''}" title="${esc(t.assignee || 'Sem responsável')}"></span></div></div>`;
  }
  function viewChamados() {
    const f = filtrados();
    const chip = (k, l) => `<button class="chip ${S.filtro === k ? 'on' : ''}" data-f="${k}">${l}</button>`;
    const cols = COLS.map(([k, nome]) => {
      let ts = f.filter((t) => t.status === k).sort(k === 'resolvido' ? (a, b) => parse(b.resolved_at) - parse(a.resolved_at) : porSla);
      const total = ts.length;
      if (k === 'resolvido') ts = ts.slice(0, 8);
      return `<section class="col" data-col="${k}" aria-label="${nome}"><h4>${nome} <b>${total}</b></h4>${ts.map(cardT).join('') || '<p class="empty">Vazio</p>'}${total > ts.length ? `<p class="empty">+ ${total - ts.length} resolvidos</p>` : ''}</section>`;
    }).join('');
    return `<div class="tools">${chip('todos', 'Todos')}${chip('criticos', 'Críticos')}${chip('risco', 'SLA em risco')}${chip('n2', 'Escalados N2')}</div><div class="board">${cols}</div>`;
  }

  function renderNav() {
    const item = (k, l, ic, extra = '') => `<${k === 'painel' || k === 'chamados' ? 'button' : 'div'} class="nav ${S.view === k ? 'on' : ''} ${k === 'painel' || k === 'chamados' ? '' : 'off'}" data-nav="${k}"><svg viewBox="0 0 24 24">${ICON[ic]}</svg><span>${l}</span>${extra}</${k === 'painel' || k === 'chamados' ? 'button' : 'div'}>`;
    $('#nav').innerHTML = item('painel', 'Painel', 'painel') + item('chamados', 'Chamados', 'chamados', `<b>${abertos().length}</b>`) +
      item('sla', 'SLA', 'sla', '<small>em breve</small>') + item('kb', 'Conhecimento', 'kb', '<small>em breve</small>') + item('auto', 'Automações', 'auto', '<small>em breve</small>');
  }
  function render() {
    renderNav();
    const dt = new Date(nowMs()).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' });
    $('#h1').textContent = S.view === 'painel' ? 'Visão geral da operação' : 'Chamados';
    $('#sub').textContent = `${dt} · ${S.mode === 'demo' ? 'modo demonstração (sem servidor)' : 'conectado à API'}`;
    $('#view').innerHTML = S.view === 'painel' ? viewPainel() : viewChamados();
    S.sig = assinatura();
    if (S.sel != null) drawer(S.sel, true);
  }

  /* ---------- drawer ---------- */
  function drawer(id, soAtualizar) {
    const t = S.tickets.find((x) => x.id === id);
    if (!t) return;
    S.sel = id;
    const r = rem(t), frac = Math.max(0, Math.min(1, r / t.sla_total_s)), st = estado(t);
    const cor = t.status === 'resolvido' ? (t.sla_state === 'ok' ? '#34d399' : '#f87171') : { ok: '#34d399', risco: '#fbbf24', estourado: '#f87171' }[st];
    const acoes = [];
    if (t.status === 'novo') acoes.push(['atendimento', 'Assumir', 'pr']);
    if (t.status === 'atendimento') acoes.push(['aguardando', 'Aguardar usuário', ''], ['resolvido', 'Resolver', 'pr']);
    if (t.status === 'aguardando') acoes.push(['atendimento', 'Retomar', 'pr']);
    const esc2 = t.status !== 'resolvido' && t.level === 'N1' ? '<button class="btn bad" data-act="escalar">Escalar para N2</button>' : '';
    $('#drawer').innerHTML = `
      <div class="dh"><span class="id">#${t.id}</span>${pri(t)}<span class="lvl ${t.level === 'N2' ? 'n2' : ''}">${t.level}</span><button class="x" data-close aria-label="Fechar">✕</button></div>
      <h2>${esc(t.title)}</h2>
      <div class="ring"><svg width="58" height="58" viewBox="0 0 58 58" aria-hidden="true"><circle cx="29" cy="29" r="24" fill="none" stroke="#1b2132" stroke-width="6"/>
        <circle id="ring-c" cx="29" cy="29" r="24" fill="none" stroke="${cor}" stroke-width="6" stroke-linecap="round" stroke-dasharray="151" stroke-dashoffset="${151 * (1 - frac)}" transform="rotate(-90 29 29)"/></svg>
        <div><small>${t.status === 'resolvido' ? 'Resolvido' : t.sla_running ? 'SLA restante' : 'SLA pausado'}</small>
        <div class="big sla s-${t.status === 'resolvido' ? (t.sla_state === 'ok' ? 'ok' : 'estourado') : t.sla_running ? st : 'pausa'}" ${t.sla_running ? `data-sla="${t.id}"` : ''}>${t.status === 'resolvido' ? (t.sla_state === 'ok' ? 'No prazo' : 'Estourado') : fmt(r)}</div></div>
        <div style="margin-left:auto;text-align:right;color:var(--mut);font-size:12px">Prazo total<br><b style="color:#fff">${t.sla_total_s / 3600}h</b></div></div>
      <div class="meta"><div class="m"><small>Solicitante</small><div>${esc(t.requester)}</div></div>
        <div class="m"><small>Responsável</small><div>${t.assignee ? `<span class="av ${avCls(t)}" style="vertical-align:middle;margin-right:6px"></span>${esc(t.assignee)}` : '—'}</div></div>
        <div class="m"><small>Categoria</small><div>${esc(t.category)}</div></div>
        <div class="m"><small>Status</small><div>${(COLS.find((c) => c[0] === t.status) || [])[1]}</div></div></div>
      ${t.description ? `<p class="desc">${esc(t.description)}</p>` : ''}
      <div><h3>Histórico</h3><ul class="tl">${t.events.map((e) => `<li class="k-${e.kind}"><b>${EV_LBL[e.kind] || e.kind}</b>${e.note ? ` — ${esc(e.note)}` : ''}<small>${dia(e.at)} ${hhmm(e.at)} · ${esc(e.actor)}</small></li>`).join('')}</ul></div>
      <div class="acts">${esc2}${acoes.map(([k, l, c]) => `<button class="btn ${c}" data-act="${k}">${l}</button>`).join('')}</div>`;
    $('#drawer').classList.add('on'); $('#drawer').setAttribute('aria-hidden', 'false'); $('#scrim').classList.add('on');
    if (!soAtualizar) $('#drawer .x').focus();
  }
  function fechar() { S.sel = null; $('#drawer').classList.remove('on'); $('#drawer').setAttribute('aria-hidden', 'true'); $('#scrim').classList.remove('on'); }

  /* ---------- diálogos / toast ---------- */
  let toastT;
  function toast(msg, bad) { const e = $('#toast'); e.textContent = msg; e.className = 'toast on' + (bad ? ' bad' : ''); clearTimeout(toastT); toastT = setTimeout(() => (e.className = 'toast'), 3200); }

  function pedirNota({ titulo, desc, rotulo, obrigatoria }) {
    return new Promise((res) => {
      const d = $('#dlg-nota'), ta = $('#nota-v');
      $('#nota-t').textContent = titulo; $('#nota-d').textContent = desc; $('#nota-ok').textContent = rotulo; ta.value = ''; $('#nota-e').textContent = '';
      const fim = () => { d.removeEventListener('close', onClose); $('#nota-ok').removeEventListener('click', onOk); };
      const onOk = (e) => { if (obrigatoria && !ta.value.trim()) { e.preventDefault(); $('#nota-e').textContent = 'Este campo é obrigatório.'; ta.focus(); } };
      const onClose = () => { fim(); res(d.returnValue === 'ok' ? ta.value : null); };
      $('#nota-ok').addEventListener('click', onOk); d.addEventListener('close', onClose);
      d.returnValue = ''; d.showModal(); ta.focus();
    });
  }

  async function executar(t, acao) {
    try {
      if (acao === 'escalar') {
        const n = await pedirNota({ titulo: `Escalar #${t.id} para o N2`, desc: 'Registre as evidências coletadas (testes feitos, logs, horário).', rotulo: 'Escalar', obrigatoria: true });
        if (n == null) return; await escalar(t, n); toast(`#${t.id} escalado para o N2`);
      } else if (acao === 'resolvido') {
        const n = await pedirNota({ titulo: `Resolver #${t.id}`, desc: 'Descreva a solução aplicada. Ela fica no histórico do chamado.', rotulo: 'Resolver', obrigatoria: true });
        if (n == null) return; await transicao(t, 'resolvido', n); toast(`#${t.id} resolvido`);
      } else if (acao === 'aguardando') {
        const n = await pedirNota({ titulo: `Aguardar usuário (#${t.id})`, desc: 'O relógio do SLA fica pausado enquanto o chamado aguarda retorno.', rotulo: 'Pausar SLA', obrigatoria: false });
        if (n == null) return; await transicao(t, 'aguardando', n); toast('SLA pausado');
      } else { await transicao(t, acao, ''); toast(acao === 'atendimento' ? 'Chamado em atendimento' : 'Atualizado'); }
      render();
    } catch (e) { toast(e.message, true); }
  }

  /* ---------- eventos ---------- */
  document.addEventListener('click', (e) => {
    const el = e.target.closest('[data-open],[data-nav],[data-f],[data-act],[data-close],#scrim,#novo');
    if (!el) return;
    if (el.dataset.nav) { if (el.dataset.nav === 'painel' || el.dataset.nav === 'chamados') { S.view = el.dataset.nav; fechar(); render(); } return; }
    if (el.dataset.f) { S.filtro = el.dataset.f; render(); return; }
    if (el.dataset.act) { const t = S.tickets.find((x) => x.id === S.sel); if (t) executar(t, el.dataset.act); return; }
    if (el.id === 'novo') { $('#novo-e').textContent = ''; $('#f-novo').reset(); $('#dlg-novo').showModal(); return; }
    if (el.dataset.open) { drawer(Number(el.dataset.open)); return; }
    fechar();
  });
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); $('#q').focus(); }
    else if (e.key === 'Escape' && S.sel != null && !document.querySelector('dialog[open]')) fechar();
    else if (e.key === 'Enter' && e.target.matches('[data-open]')) drawer(Number(e.target.dataset.open));
  });
  $('#q').addEventListener('input', (e) => { S.q = e.target.value; if (S.q && S.view !== 'chamados') S.view = 'chamados'; render(); });

  // arrastar e soltar no quadro
  let arrastando = null;
  document.addEventListener('dragstart', (e) => { const c = e.target.closest('.t'); if (!c) return; arrastando = Number(c.dataset.id); c.classList.add('drag'); e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', String(arrastando)); });
  document.addEventListener('dragend', () => { arrastando = null; document.querySelectorAll('.drag,.over').forEach((x) => x.classList.remove('drag', 'over')); });
  document.addEventListener('dragover', (e) => { const c = e.target.closest('.col'); if (c && arrastando != null) { e.preventDefault(); document.querySelectorAll('.over').forEach((x) => x.classList.remove('over')); c.classList.add('over'); } });
  document.addEventListener('drop', (e) => {
    const c = e.target.closest('.col'); if (!c || arrastando == null) return; e.preventDefault();
    const t = S.tickets.find((x) => x.id === arrastando), para = c.dataset.col;
    if (!t || t.status === para) return;
    if (!TRANS[t.status].includes(para)) return toast(`Não é possível mover de “${t.status}” para “${para}”`, true);
    executar(t, para);
  });

  $('#f-novo').addEventListener('submit', async (e) => {
    if (e.submitter && e.submitter.value !== 'ok') return;
    const f = new FormData(e.target);
    try { const t = await criar(Object.fromEntries(f)); toast(`Chamado #${t.id} aberto`); S.view = 'chamados'; S.q = ''; $('#q').value = ''; render(); drawer(t.id); }
    catch (err) { e.preventDefault(); $('#novo-e').textContent = err.message; $('#dlg-novo').showModal(); }
  });
  $('#dlg-novo [name=category]').innerHTML = CATS.map((c) => `<option>${c}</option>`).join('');
  $('#dlg-novo [name=priority]').innerHTML = Object.entries(PRI).map(([k, v]) => `<option value="${k}" ${k === 'media' ? 'selected' : ''}>${v}</option>`).join('');

  /* ---------- relógio ---------- */
  setInterval(() => {
    document.querySelectorAll('[data-sla]').forEach((el) => {
      const t = S.tickets.find((x) => x.id === Number(el.dataset.sla)); if (!t) return;
      el.textContent = fmt(rem(t)); el.classList.remove('s-ok', 's-risco', 's-estourado'); el.classList.add('s-' + estado(t));
    });
    if (S.sel != null) {
      const t = S.tickets.find((x) => x.id === S.sel), c = $('#ring-c');
      if (t && c && t.sla_running) c.setAttribute('stroke-dashoffset', 151 * (1 - Math.max(0, Math.min(1, rem(t) / t.sla_total_s))));
    }
    if (assinatura() !== S.sig && !document.querySelector('dialog[open]')) render(); // mudou de ok→risco→estourado
  }, 1000);

  carregar().then(() => { S.view = location.hash === '#chamados' ? 'chamados' : 'painel'; render(); })
    .catch(() => { $('#view').innerHTML = '<p class="empty">Não foi possível carregar os dados.</p>'; });
})();
