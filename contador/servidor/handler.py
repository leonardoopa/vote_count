"""O HTTP: escolhe a rota pelo caminho e envia a resposta."""
import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from contador.servidor import estaticos
from contador.servidor.rotas import ROTAS_API, ROTAS_ARQUIVO


class Handler(BaseHTTPRequestHandler):
    def _enviar(self, status, tipo, corpo, extras=None):
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        extras = extras or {}
        if "Cache-Control" not in extras:
            self.send_header("Cache-Control", "no-store")
        for nome, valor in extras.items():
            self.send_header(nome, valor)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corpo)

    def do_GET(self):
        url = urlparse(self.path)
        consulta = parse_qs(url.query)
        if url.path in ROTAS_API:
            status, corpo = ROTAS_API[url.path](consulta)
            self._enviar(status, "application/json; charset=utf-8", json.dumps(corpo, ensure_ascii=False).encode())
        elif url.path in ROTAS_ARQUIVO:
            status, tipo, corpo, extras = ROTAS_ARQUIVO[url.path](consulta, self.headers)
            self._enviar(status, tipo, corpo, extras)
        elif url.path == "/saude":
            self._enviar(200, "text/plain; charset=utf-8", b"ok")
        elif (arquivo := estaticos.arquivo_da_web(url.path, self.headers)) is not None:
            self._enviar(*arquivo)
        elif (desenho := estaticos.desenho_dos_municipios(url.path, self.headers)) is not None:
            self._enviar(*desenho)
        else:
            self._enviar(404, "text/plain; charset=utf-8", b"nao encontrado")

    do_HEAD = do_GET  # mesmos cabeçalhos, sem corpo (alguns verificadores de link usam HEAD)

    def log_request(self, code="-", size="-"):  # sem log das consultas normais (a página consulta a cada 15s)
        if str(code).isdigit() and int(code) >= 400:
            super().log_request(code, size)
