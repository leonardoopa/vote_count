"""A página inicial com a prévia do link, a imagem do placar (/og.png), o manifesto do app e os ícones."""
import json
import os
import threading
import time
from collections import OrderedDict
from urllib.parse import urlencode

from contador.caminhos import WEB
from contador.divulgacao import compartilhar, imagem
from contador.recursos.placar import resumir
from contador.servidor import estado
from contador.servidor.respostas import cidades_da_uf
from contador.servidor.validacao import validar, validar_municipio
from contador.tse import catalogo, leitura

PAGINA = WEB / "index.html"

URL_PUBLICA = os.environ.get("URL_PUBLICA", "")  # ex.: https://votos.exemplo.com.br; sem ela, vale o Host da requisição
MARCA_DO_HEAD = "<!-- bloco: pwa e prévia de compartilhamento (head) -->"
MARCA_DO_HTML = '<html lang="pt-BR">'
TTL_CARTAO = 60
MAX_CARTOES = 64
_CARTOES = OrderedDict()  # chave da seleção + totalização -> (vale até, PNG)
_TRAVA_CARTOES = threading.Lock()
_ICONES = {}
MANIFESTO = {
    "name": compartilhar.NOME_DO_SITE, "short_name": "Votos 2026", "lang": "pt-BR", "start_url": "/", "scope": "/",
    "description": compartilhar.DESCRICAO_PADRAO, "display": "standalone",
    "background_color": "#0d0d0d", "theme_color": "#0d0d0d",
    "icons": [
        {"src": "/icone-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "/icone-512.png", "sizes": "512x512", "type": "image/png"},
        {"src": "/icone-512-mascara.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
    ],
}


def selecao_da_consulta(consulta):
    """(cargo, uf, ambiente, turno, município) de uma query válida, ou None."""
    try:
        cargo, uf, ambiente, turno, _ = validar(consulta)
        return cargo, uf, ambiente, turno, validar_municipio(consulta, uf)
    except ValueError:
        return None


def consulta_canonica(cargo, uf, ambiente, turno, municipio):
    """A query do link, só com valores já validados e sempre na mesma ordem."""
    campos = [("cargo", cargo), ("uf", uf), ("turno", turno)]
    if ambiente != "oficial":
        campos.append(("ambiente", ambiente))
    if municipio:
        campos.append(("municipio", municipio))
    return urlencode(campos)


def nome_da_cidade(ambiente, cargo, turno, uf, municipio):
    """Nome da cidade se a lista do TSE já está no cache (nunca consulta o TSE para isso)."""
    config = estado.CACHE.espiar(catalogo.url_municipios(ambiente, cargo, turno))
    achada = leitura.cidade_por_codigo(leitura.municipios(config, uf), municipio) if config else None
    return achada["nome"] if achada else None


def pagina(consulta, cabecalhos):
    """index.html com as meta tags da seleção do link (WhatsApp, X e outros leem o HTML, não o JavaScript)."""
    base = compartilhar.base_publica(URL_PUBLICA, cabecalhos)
    selecao = selecao_da_consulta(consulta) if "cargo" in consulta or "uf" in consulta else None
    if selecao is None:
        meta = compartilhar.meta_tags(base, "")
    else:
        cargo, uf, ambiente, turno, municipio = selecao
        cidade = nome_da_cidade(ambiente, cargo, turno, uf, municipio) if municipio else None
        dados = estado.CACHE.espiar(catalogo.montar_url(ambiente, cargo, uf, turno, municipio=municipio or None))
        descricao = compartilhar.descricao_do_placar(resumir(dados, 3) if dados else None)
        meta = compartilhar.meta_tags(base, consulta_canonica(*selecao), compartilhar.titulo_da_selecao(cargo, uf, turno, cidade), descricao)
    html = PAGINA.read_text(encoding="utf-8").replace(MARCA_DO_HEAD, meta, 1)
    if consulta.get("embed") == ["1"]:
        # Dentro do iframe de outro site (?embed=1): a página já nasce com o visual enxuto, sem piscar, e fora dos buscadores.
        html = html.replace(MARCA_DO_HTML, '<html lang="pt-BR" class="embed">', 1).replace("<head>", '<head>\n<meta name="robots" content="noindex">', 1)
    return html.encode()


def pagina_inicial(consulta, cabecalhos):
    return 200, "text/html; charset=utf-8", pagina(consulta, cabecalhos), {}


def cartao_do_placar(consulta, cabecalhos=None):
    """(status, tipo, corpo, cabeçalhos extras) da imagem de prévia. Sem dados ainda, a imagem só traz o título."""
    selecao = selecao_da_consulta(consulta)
    if selecao is None:
        return 400, "text/plain; charset=utf-8", b"selecao invalida", {}
    cargo, uf, ambiente, turno, municipio = selecao
    cidade = None
    if municipio:
        # só código que o TSE lista para esta UF vira URL (evita 404 em série, como em `resultado`)
        lista, falha = cidades_da_uf(ambiente, cargo, turno, uf)
        cidade = leitura.cidade_por_codigo(lista or [], municipio)
        if falha or cidade is None:
            return 400, "text/plain; charset=utf-8", b"municipio invalido", {}
    dados, _, _ = estado.CACHE.obter(catalogo.montar_url(ambiente, cargo, uf, turno, municipio=municipio or None))
    resumo = resumir(dados, compartilhar.MAX_CANDIDATOS_NA_IMAGEM) if dados else None
    chave = (selecao, resumo["ultima_totalizacao"] if resumo else "", resumo["secoes"]["apuradas"] if resumo else 0, resumo["final"] if resumo else False)
    with _TRAVA_CARTOES:
        agora = time.time()
        pronto = _CARTOES.get(chave)
        if pronto is None or pronto[0] < agora:
            titulo = compartilhar.titulo_da_selecao(cargo, uf, turno, cidade["nome"] if cidade else None)
            pronto = _CARTOES[chave] = (agora + TTL_CARTAO, compartilhar.cartao(titulo, resumo, ambiente))
            while len(_CARTOES) > MAX_CARTOES:
                _CARTOES.popitem(last=False)
        _CARTOES.move_to_end(chave)
    return 200, "image/png", pronto[1], {"Cache-Control": "public, max-age=60"}


def icone(lado, mascara=False):
    def rota(consulta, cabecalhos=None):
        if (lado, mascara) not in _ICONES:
            _ICONES[(lado, mascara)] = imagem.icone(lado, mascara)
        return 200, "image/png", _ICONES[(lado, mascara)], {"Cache-Control": "public, max-age=86400"}
    return rota


def manifesto(consulta, cabecalhos=None):
    corpo = json.dumps(MANIFESTO, ensure_ascii=False).encode()
    return 200, "application/manifest+json; charset=utf-8", corpo, {"Cache-Control": "public, max-age=3600"}
