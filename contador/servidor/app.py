"""A linha de comando que sobe o servidor.

    python3 -m contador.servidor                  # http://127.0.0.1:8000
    python3 -m contador.servidor --porta 9000

O servidor consulta o TSE e guarda a resposta em cache. Todos os visitantes
compartilham a mesma consulta, então o acesso ao TSE não cresce com o número
de pessoas na página (o TSE bloqueia o IP que passar do limite).
"""
import argparse
import signal
from http.server import ThreadingHTTPServer

from contador.servidor.handler import Handler


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python3 -m contador.servidor", description="Contador de votos em tempo real: versão web.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--porta", type=int, default=8000)
    args = parser.parse_args(argv)
    signal.signal(signal.SIGTERM, signal.default_int_handler)  # docker stop encerra na hora
    servidor = ThreadingHTTPServer((args.host, args.porta), Handler)
    print(f"Contador no ar em http://{args.host}:{args.porta}", flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()
