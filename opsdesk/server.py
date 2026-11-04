"""Servidor HTTP do OpsDesk: API JSON + arquivos estáticos (sem dependências externas)."""
import json
import mimetypes
import os
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import seed
from .service import Desk, NaoEncontrado, conectar, agora

WEB = Path(__file__).resolve().parent.parent / "web"
LOCK = threading.Lock()


def criar_desk(db: str, popular: bool = True) -> Desk:
    con = conectar(db)
    desk = Desk(con)
    if popular and con.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 0:
        seed.popular(con, agora())
    return desk


def fabricar_handler(desk: Desk):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, codigo, corpo):
            dados = json.dumps(corpo, ensure_ascii=False).encode()
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)

        def _corpo(self):
            n = int(self.headers.get("Content-Length") or 0)
            try:
                return json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError:
                raise ValueError("JSON inválido")

        def _estatico(self, caminho):
            alvo = "index.html" if caminho in ("", "/") else caminho.lstrip("/")
            arq = (WEB / alvo).resolve()
            if WEB.resolve() not in arq.parents or not arq.is_file():
                return self._json(404, {"erro": "Não encontrado"})
            dados = arq.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", (mimetypes.guess_type(str(arq))[0] or "application/octet-stream")
                             + ("; charset=utf-8" if arq.suffix in (".html", ".js", ".css", ".json") else ""))
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)

        def _tratar(self, fn):
            try:
                with LOCK:
                    codigo, corpo = fn()
                self._json(codigo, corpo)
            except NaoEncontrado as e:
                self._json(404, {"erro": str(e)})
            except ValueError as e:
                self._json(400, {"erro": str(e)})

        def do_GET(self):
            u = urlparse(self.path)
            if not u.path.startswith("/api/"):
                return self._estatico(u.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            if u.path == "/api/tickets":
                return self._tratar(lambda: (200, desk.listar(q.get("status"), q.get("priority"), q.get("level"), q.get("q"))))
            if u.path == "/api/metrics":
                return self._tratar(lambda: (200, desk.metricas()))
            m = re.fullmatch(r"/api/tickets/(\d+)", u.path)
            if m:
                return self._tratar(lambda: (200, desk.obter(int(m[1]))))
            self._json(404, {"erro": "Rota não encontrada"})

        def do_POST(self):
            u = urlparse(self.path)
            try:
                b = self._corpo()
            except ValueError as e:
                return self._json(400, {"erro": str(e)})
            if u.path == "/api/tickets":
                return self._tratar(lambda: (201, desk.criar(b.get("title"), b.get("requester"), b.get("category"),
                                                              b.get("priority"), b.get("description", ""))))
            m = re.fullmatch(r"/api/tickets/(\d+)/(transition|escalate)", u.path)
            if m:
                tid = int(m[1])
                if m[2] == "transition":
                    return self._tratar(lambda: (200, desk.transicao(tid, b.get("to"), b.get("note", ""), b.get("actor", "Analista"))))
                return self._tratar(lambda: (200, desk.escalar(tid, b.get("note", ""), b.get("actor", "Analista N1"))))
            self._json(404, {"erro": "Rota não encontrada"})

    return H


def servir(db: str, porta: int = 8000, popular: bool = True) -> ThreadingHTTPServer:
    desk = criar_desk(db, popular)
    return ThreadingHTTPServer(("127.0.0.1", porta), fabricar_handler(desk))


if __name__ == "__main__":
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    db = os.environ.get("OPSDESK_DB", str(Path(__file__).resolve().parent.parent / "data" / "opsdesk.db"))
    srv = servir(db, porta)
    print(f"OpsDesk rodando em http://127.0.0.1:{porta}  (Ctrl+C para sair)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrado.")
