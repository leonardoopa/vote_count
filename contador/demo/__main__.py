"""Demonstração: o servidor de sempre em cima de um TSE falso, com a apuração avançando sozinha.

    python3 -m contador.demo                  # http://127.0.0.1:8000/?ambiente=simulado
    python3 -m contador.demo --duracao 600 --passo 15 --porta 8010
"""
import argparse
import time

from contador.demo import tse_falso
from contador.servidor import app, estado
from contador.tse import cliente


def main():
    parser = argparse.ArgumentParser(prog="python3 -m contador.demo", description="Demonstração com TSE falso (nada sai da máquina).")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--porta", type=int, default=8000)
    parser.add_argument("--duracao", type=int, default=300, help="segundos da apuração, de 0 a 100%%")
    parser.add_argument("--passo", type=int, default=10, help="segundos entre totalizações novas")
    args = parser.parse_args()
    tse_falso.RELOGIO.update(inicio=time.time(), passo=max(1, args.passo), duracao=max(args.passo, args.duracao))
    cliente.buscar = tse_falso.buscar_falso
    estado.VARREDOR.por_segundo = max(estado.VARREDOR.por_segundo, 50)  # sem TSE de verdade, o mapa por município enche logo
    print(f"TSE FALSO: dados inventados. Abra http://{args.host}:{args.porta}/?ambiente=simulado", flush=True)
    app.main(["--host", args.host, "--porta", str(args.porta)])


if __name__ == "__main__":
    main()
