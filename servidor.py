#!/usr/bin/env python3
"""Versão web do contador de votos: página + API em cima dos arquivos do TSE.

    python3 servidor.py                  # http://127.0.0.1:8000
    python3 servidor.py --porta 9000

O servidor consulta o TSE e guarda a resposta em cache. Todos os visitantes
compartilham a mesma consulta, então o acesso ao TSE não cresce com o número
de pessoas na página (o TSE bloqueia o IP que passar do limite).
"""
import argparse
import json
import signal
import threading
import time
from collections import OrderedDict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import contador

PAGINA = Path(__file__).with_name("index.html")

# Segundos entre consultas ao TSE por seleção. O CDN renova a cópia a cada ~12 s, mas
# manda max-age de 17 a 54 s; seguir esse max-age atrasaria o placar sem necessidade.
# As consultas usam ETag (resposta 304 quando nada mudou), então são leves.
INTERVALO_TSE = 10
ESPERA_404 = 60  # evita repetir 404 (o TSE bloqueia o IP após muitos)
ESPERA_FALHA = 30
LIMITE_404_POR_MINUTO = 10
# Cada cidade é uma URL a mais no cache e uma consulta a mais ao TSE. Sem teto, quem
# varresse as ~5,7 mil cidades derrubaria o limite de 100 req/s do TSE (bloqueio de
# 10 minutos para o IP todo) e encheria a memória.
LIMITE_BUSCAS_POR_SEGUNDO = 20
MAX_ENTRADAS = 400
TTL_MUNICIPIOS = 6 * 3600  # a lista de cidades não muda durante a apuração
TOP_PADRAO, TOP_MAXIMO = 15, 100


class Entrada:
    def __init__(self):
        self.trava = threading.Lock()
        self.dados = None
        self.etag = None
        self.status = 0
        self.valido_ate = 0.0
        self.verificado_em = 0.0  # último contato bem-sucedido com o TSE (200 ou 304)


class Cache:
    def __init__(self):
        self._entradas = OrderedDict()  # do menos para o mais recentemente usado
        self._trava = threading.Lock()
        self._erros_404 = deque()  # quando ocorreram os 404 recentes
        self._buscas = deque()  # quando ocorreram as consultas recentes ao TSE

    def obter(self, url, ttl=INTERVALO_TSE):
        with self._trava:
            entrada = self._entradas.get(url)
            if entrada is None:
                entrada = self._entradas[url] = Entrada()
                while len(self._entradas) > MAX_ENTRADAS:
                    self._entradas.popitem(last=False)
            self._entradas.move_to_end(url)
        with entrada.trava:  # um visitante consulta o TSE, os outros esperam e reaproveitam
            agora = time.time()
            if agora >= entrada.valido_ate:
                self._atualizar(url, entrada, agora, ttl)
            return entrada.dados, entrada.status, entrada.verificado_em

    def _limite_404(self, agora):
        while self._erros_404 and agora - self._erros_404[0] > 60:
            self._erros_404.popleft()
        return len(self._erros_404) >= LIMITE_404_POR_MINUTO

    def _limite_buscas(self, agora):
        with self._trava:
            while self._buscas and agora - self._buscas[0] > 1:
                self._buscas.popleft()
            if len(self._buscas) >= LIMITE_BUSCAS_POR_SEGUNDO:
                return True
            self._buscas.append(agora)
            return False

    def _atualizar(self, url, entrada, agora, ttl):
        if entrada.dados is None and self._limite_404(agora):
            # muitos 404 seguidos bloqueiam o IP no TSE: não tenta mais uma URL nova por um tempo
            entrada.status, entrada.valido_ate = 429, agora + ESPERA_404
            return
        if self._limite_buscas(agora):
            entrada.status, entrada.valido_ate = 429, agora + 1
            return
        resposta = contador.buscar(url, entrada.etag)
        entrada.status = resposta.status
        if resposta.status in (200, 304):
            if resposta.status == 200:
                entrada.dados, entrada.etag = resposta.dados, resposta.etag
            entrada.verificado_em = agora
            entrada.valido_ate = agora + ttl
        elif resposta.status == 404:
            self._erros_404.append(agora)
            entrada.valido_ate = agora + ESPERA_404
        elif resposta.status in (403, 429):
            entrada.valido_ate = agora + contador.ESPERA_BLOQUEIO
        else:
            entrada.valido_ate = agora + ESPERA_FALHA


CACHE = Cache()


def decimal(texto):
    return float((texto or "0").replace(",", "."))


def resumir(dados, top):
    secoes, eleitores, votos = dados["s"], dados["e"], dados["v"]
    todos = contador.candidatos(dados)
    return {
        "final": dados.get("tf") == "s",
        "ultima_totalizacao": f"{dados.get('dt', '')} {dados.get('ht', '')}".strip(),
        "gerado": f"{dados['dg']} {dados['hg']}",
        "secoes": {
            "total": contador.inteiro(secoes["ts"]),
            "apuradas": contador.inteiro(secoes["st"]),
            "percentual": decimal(secoes["pst"]),
        },
        "eleitores": {
            "aptos": contador.inteiro(eleitores["te"]),
            "comparecimento": contador.inteiro(eleitores["c"]),
            "pct_comparecimento": decimal(eleitores["pc"]),
            "abstencao": contador.inteiro(eleitores["a"]),
            "pct_abstencao": decimal(eleitores["pa"]),
        },
        "votos": {
            "total": contador.inteiro(votos["tv"]),
            "brancos": contador.inteiro(votos["vb"]),
            "pct_brancos": decimal(votos["pvb"]),
            "nulos": contador.inteiro(votos["tvn"]),
            "pct_nulos": decimal(votos["ptvn"]),
        },
        "total_candidatos": len(todos),
        "candidatos": [
            {
                "posicao": posicao,
                "numero": cand["n"],
                "nome": cand.get("nmu") or cand["nm"],
                "partido": cand["partido"],
                "votos": contador.inteiro(cand["vap"]),
                "percentual": decimal(cand["pvap"]),
                "eleito": cand.get("st", "").lower().startswith("eleito"),
                "situacao": contador.situacao(cand),
            }
            for posicao, cand in enumerate(todos[:top], start=1)
        ],
    }


def validar(consulta):
    """Só valores conhecidos chegam à URL do TSE; qualquer outra coisa vira erro 400."""
    pegar = lambda nome, padrao="": consulta.get(nome, [padrao])[0]
    cargo = pegar("cargo", "presidente")
    uf = pegar("uf", "br" if cargo == "presidente" else "").lower()
    ambiente = pegar("ambiente", "oficial")
    turno, top = pegar("turno", "1"), pegar("top", str(TOP_PADRAO))
    if cargo not in contador.CARGOS:
        raise ValueError("cargo inválido")
    if not contador.uf_valida(cargo, uf):
        raise ValueError("uf inválida para este cargo")
    if ambiente not in contador.AMBIENTES:
        raise ValueError("ambiente inválido")
    if turno not in ("1", "2") or not top.isdigit():
        raise ValueError("turno ou top inválido")
    if turno == "2" and cargo not in ("presidente", "governador"):
        raise ValueError("só presidente e governador têm 2º turno")
    return cargo, uf, ambiente, int(turno), max(1, min(int(top), TOP_MAXIMO))


def validar_municipio(consulta, uf):
    """Código TSE da cidade (5 dígitos) ou '' para a UF inteira. Se existe na UF, quem diz é o TSE."""
    codigo = consulta.get("municipio", [""])[0]
    if not codigo:
        return ""
    if uf == "br" or not (codigo.isascii() and codigo.isdigit() and len(codigo) == 5):
        raise ValueError("município inválido")
    return codigo


def erro_do_tse(status, mensagem_404):
    """(status HTTP, corpo) para quando o TSE não deu dados."""
    if status == 404:
        return 404, {"erro": mensagem_404}
    if status in (403, 429):
        return 503, {"erro": "Muitas consultas seguidas ao TSE. Aguarde alguns minutos e tente de novo."}
    return 503, {"erro": f"Não foi possível ler o TSE agora (HTTP {status or 'sem resposta'}). Tentando de novo em instantes."}


def cidades_da_uf(ambiente, cargo, turno, uf):
    """(lista de cidades, None) ou (None, (status HTTP, corpo)) se o TSE não respondeu."""
    url = contador.url_municipios(ambiente, cargo, turno)
    dados, status, _ = CACHE.obter(url, ttl=TTL_MUNICIPIOS)
    if dados is None:
        return None, erro_do_tse(status, "O TSE não publicou a lista de cidades desta eleição.")
    return contador.municipios(dados, uf), None


def municipios_da_uf(consulta):
    """Devolve (status HTTP, corpo JSON) com as cidades da UF, para a página montar o seletor."""
    try:
        cargo, uf, ambiente, turno, _ = validar(consulta)
        if uf == "br":
            raise ValueError("escolha uma UF para listar as cidades")
    except ValueError as erro:
        return 400, {"erro": str(erro)}
    lista, falha = cidades_da_uf(ambiente, cargo, turno, uf)
    if falha:
        return falha
    return 200, {"uf": uf, "municipios": lista}


def resultado(consulta):
    """Devolve (status HTTP, corpo JSON)."""
    try:
        cargo, uf, ambiente, turno, top = validar(consulta)
        municipio = validar_municipio(consulta, uf)
    except ValueError as erro:
        return 400, {"erro": str(erro)}
    cidade = None
    if municipio:
        # Só código que o TSE lista para esta UF vira URL: evita 404 em série (bloqueio do IP).
        lista, falha = cidades_da_uf(ambiente, cargo, turno, uf)
        if falha:
            return falha
        cidade = next((m for m in lista if m["codigo"] == municipio), None)
        if cidade is None:
            return 400, {"erro": "município inválido para esta UF"}
    url = contador.montar_url(ambiente, cargo, uf, turno, municipio=municipio or None)
    dados, status, verificado_em = CACHE.obter(url)
    if dados is None:
        return erro_do_tse(status, "O TSE ainda não publicou o resultado desta seleção (ou o cargo não é disputado nesta UF).")
    corpo = resumir(dados, top)
    corpo["ambiente"] = ambiente
    corpo["municipio"] = {"codigo": cidade["codigo"], "nome": cidade["nome"]} if cidade else None
    corpo["idade_s"] = round(time.time() - verificado_em)
    if status not in (200, 304):
        corpo["aviso"] = "O TSE não respondeu na última tentativa; mostrando o último placar recebido."
    return 200, corpo


class Handler(BaseHTTPRequestHandler):
    def _enviar(self, status, tipo, corpo):
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/":
            self._enviar(200, "text/html; charset=utf-8", PAGINA.read_bytes())
        elif url.path in ("/api/resultado", "/api/municipios"):
            funcao = resultado if url.path == "/api/resultado" else municipios_da_uf
            status, corpo = funcao(parse_qs(url.query))
            self._enviar(status, "application/json; charset=utf-8", json.dumps(corpo, ensure_ascii=False).encode())
        elif url.path == "/saude":
            self._enviar(200, "text/plain; charset=utf-8", b"ok")
        else:
            self._enviar(404, "text/plain; charset=utf-8", b"nao encontrado")

    def log_request(self, code="-", size="-"):  # sem log das consultas normais (a página consulta a cada 15s)
        if str(code).isdigit() and int(code) >= 400:
            super().log_request(code, size)


def main():
    parser = argparse.ArgumentParser(description="Contador de votos em tempo real: versão web.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--porta", type=int, default=8000)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, signal.default_int_handler)  # docker stop encerra na hora
    servidor = ThreadingHTTPServer((args.host, args.porta), Handler)
    print(f"Contador no ar em http://{args.host}:{args.porta}", flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()
