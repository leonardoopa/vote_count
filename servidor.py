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

import anuncio
import contador
import historico
import mapa

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
DISPUTAS_MAXIMO = 27  # todas as UFs; a página mostra as mais apertadas primeiro


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
    HISTORICO.registrar((ambiente, cargo, uf, turno, municipio), dados)  # só memória e disco: o histórico nunca consulta o TSE
    corpo = resumir(dados, top)
    corpo["ambiente"] = ambiente
    corpo["municipio"] = {"codigo": cidade["codigo"], "nome": cidade["nome"]} if cidade else None
    corpo["idade_s"] = round(time.time() - verificado_em)
    if status not in (200, 304):
        corpo["aviso"] = "O TSE não respondeu na última tentativa; mostrando o último placar recebido."
    return 200, corpo


# Rotas JSON da API: caminho -> função(consulta) que devolve (status HTTP, corpo). Cada recurso novo
# escreve a sua função na seção abaixo e registra a rota aqui, sem mexer no Handler.
ROTAS_API = {
    "/api/resultado": resultado,
    "/api/municipios": municipios_da_uf,
}

# ---- histórico e atualizações ----

# Um ponto do placar a cada totalização nova, por seleção. `resultado()` registra o que já tem no
# cache; as rotas abaixo só leem o que foi guardado, então nunca consultam o TSE.
HISTORICO = historico.do_ambiente()


def chave_do_historico(consulta):
    """(chave da série, None) ou (None, (status HTTP, corpo)) quando a seleção não pode ter histórico."""
    try:
        cargo, uf, ambiente, turno, _ = validar(consulta)
        municipio = validar_municipio(consulta, uf)
    except ValueError as erro:
        return None, (400, {"erro": str(erro)})
    if cargo not in historico.CARGOS:
        return None, (400, {"erro": "o histórico só existe para presidente, governador e senador"})
    return (ambiente, cargo, uf, turno, municipio), None


def historico_da_selecao(consulta):
    chave, erro = chave_do_historico(consulta)
    return erro or (200, HISTORICO.consultar(chave))


def atualizacoes_da_selecao(consulta):
    chave, erro = chave_do_historico(consulta)
    return erro or (200, HISTORICO.atualizacoes(chave))


ROTAS_API.update({
    "/api/historico": historico_da_selecao,
    "/api/atualizacoes": atualizacoes_da_selecao,
})


# ---- mapa, regiões e anúncio ----

# Faixa de publicidade do topo: configurada por variáveis de ambiente e lida só na partida.
ANUNCIO = anuncio.do_ambiente()

# Uma resposta pronta por seleção: vários visitantes dividem o mesmo mapa em vez de cada um abrir
# a sua rodada de consultas (são 29 arquivos por rodada). Poucas chaves: ambiente x cargo x turno.
TTL_RESPOSTA_MAPA = 5
_PRONTAS, _TRAVAS_PRONTAS, _TRAVA_GERAL = {}, {}, threading.Lock()


def lembrar(chave, construir, ttl=TTL_RESPOSTA_MAPA):
    """(status, corpo) de `construir()`, refeito no máximo a cada `ttl` segundos por chave."""
    with _TRAVA_GERAL:
        trava = _TRAVAS_PRONTAS.setdefault(chave, threading.Lock())
    with trava:  # quem chega com a resposta vencida refaz; os outros esperam e reaproveitam
        pronta = _PRONTAS.get(chave)
        if pronta is None or time.time() >= pronta[0]:
            status, corpo = construir()
            pronta = _PRONTAS[chave] = (time.time() + ttl, status, corpo)
        return pronta[1], pronta[2]


def validar_mapa(consulta, cargos=("presidente", "governador")):
    """(cargo, ambiente, turno) do mapa: a validação é a de `validar`, que pede uma UF; o mapa usa todas."""
    cargo = consulta.get("cargo", ["presidente"])[0]
    if cargo not in cargos:
        raise ValueError("este recurso só existe para " + " e ".join(cargos))
    _, _, ambiente, turno, _ = validar({**consulta, "uf": ["br" if cargo == "presidente" else "sp"]})
    return cargo, ambiente, turno


def resumo_do_cargo(cargo, ambiente, turno):
    """(status, corpo) do resumo por UF: uma rodada de consultas que mapa, regiões e disputas dividem."""
    def construir():
        corpo, falha = mapa.resumo_por_uf(CACHE.obter, ambiente, cargo, turno)
        return erro_do_tse(*falha) if falha else (200, corpo)

    return lembrar(("mapa", ambiente, cargo, turno), construir)


def mapa_por_uf(consulta):
    """Devolve (status HTTP, corpo JSON) com o líder de cada UF, para o mapa do Brasil."""
    try:
        cargo, ambiente, turno = validar_mapa(consulta)
    except ValueError as erro:
        return 400, {"erro": str(erro)}
    return resumo_do_cargo(cargo, ambiente, turno)


def derivado(consulta, cargos, funcao):
    """Corpo de uma rota que só reorganiza o resumo por UF (regiões, disputas): sem consulta nova ao TSE."""
    try:
        cargo, ambiente, turno = validar_mapa(consulta, cargos)
    except ValueError as erro:
        return 400, {"erro": str(erro)}
    status, corpo = resumo_do_cargo(cargo, ambiente, turno)
    return (status, funcao(corpo)) if status == 200 else (status, corpo)


def regioes_do_pais(consulta):
    return derivado({**consulta, "cargo": ["presidente"]}, ("presidente",), mapa.regioes)


def disputas_apertadas(consulta):
    return derivado(consulta, ("governador", "senador"), lambda corpo: mapa.disputas(corpo, limite=DISPUTAS_MAXIMO))


ROTAS_API.update({
    "/api/anuncio": lambda consulta: (200, ANUNCIO),
    "/api/mapa": mapa_por_uf,
    "/api/regioes": regioes_do_pais,
    "/api/disputas": disputas_apertadas,
})


# ---- busca rápida ----

MAX_BUSCA = 40        # caracteres do termo
MAX_RESULTADOS = 10   # cidades devolvidas
_INDICE = (None, [])  # (arquivo de cidades do TSE, [(uf, código, nome, nome sem acento, capital)])


def indice_de_cidades(config):
    """Cidades de todas as UFs já sem acento, guardadas enquanto o arquivo do TSE no cache for o mesmo."""
    global _INDICE
    if _INDICE[0] is not config:
        lista = [
            (abr["cd"], m["cd"], contador.nome_proprio(m["nm"]), contador.sem_acento(m["nm"]), m.get("c") == "s")
            for abr in config.get("abr", []) if abr.get("cd") in contador.UFS
            for m in abr.get("mu", [])
        ]
        _INDICE = (config, lista)
    return _INDICE[1]


def buscar_cidades(config, cargo, termo, limite=MAX_RESULTADOS):
    """Cidades cujo nome contém o termo (sem diferenciar acento nem caixa). Quem começa com o termo vem primeiro."""
    alvo = contador.sem_acento(termo)
    if len(alvo) < 2:
        return []
    achadas = []
    for uf, codigo, nome, normal, capital in indice_de_cidades(config):
        posicao = normal.find(alvo)
        if posicao < 0 or not contador.uf_valida(cargo, uf):
            continue
        rank = 0 if posicao == 0 else 1 if normal[posicao - 1] == " " else 2
        achadas.append(((rank, not capital, len(normal), normal, uf), {"uf": uf, "codigo": codigo, "nome": nome, "capital": capital}))
    achadas.sort(key=lambda par: par[0])
    return [cidade for _, cidade in achadas[:limite]]


def busca_rapida(consulta):
    """Devolve (status HTTP, corpo JSON) com as cidades que combinam com `q`. A lista vem do cache: sem consulta nova."""
    cargo = consulta.get("cargo", ["presidente"])[0]
    uf = "br" if cargo == "presidente" else "df" if cargo == "deputado-distrital" else "sp"
    try:
        cargo, _, ambiente, _, _ = validar({**consulta, "uf": [uf], "turno": ["1"]})
    except ValueError as erro:
        return 400, {"erro": str(erro)}
    termo = consulta.get("q", [""])[0]
    if len(termo) > MAX_BUSCA:
        return 400, {"erro": "termo de busca longo demais"}
    if len(contador.sem_acento(termo)) < 2:
        return 200, {"cidades": []}
    # a lista de cidades é a mesma em qualquer turno: o 1º turno sempre existe
    config, status, _ = CACHE.obter(contador.url_municipios(ambiente, cargo, 1), ttl=TTL_MUNICIPIOS)
    if config is None:
        return erro_do_tse(status, "O TSE não publicou a lista de cidades desta eleição.")
    return 200, {"cidades": buscar_cidades(config, cargo, termo)}


ROTAS_API["/api/busca"] = busca_rapida


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
        elif url.path in ROTAS_API:
            status, corpo = ROTAS_API[url.path](parse_qs(url.query))
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
