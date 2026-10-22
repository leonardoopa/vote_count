"""Espaço de publicidade no topo da página: leitura e validação da configuração.

Tudo vem de variáveis de ambiente (veja .env.example) e é lido uma vez, na partida. Sem
ANUNCIO_TEXTO não há faixa. A página mostra o texto como texto puro (nunca como HTML), com o
rótulo "Publicidade" sempre ao lado, e abre o link numa aba nova, marcado como patrocinado.
"""
import os
import sys
from urllib.parse import urlparse

MAX_TEXTO = 160
MAX_ROTULO = 24
MAX_LINK = 300
ROTULO_PADRAO = "Publicidade"
INATIVO = {"ativo": False}


def limpar(texto, maximo):
    """Uma linha de texto imprimível com até `maximo` caracteres, ou '' se não serve."""
    texto = " ".join((texto or "").split())
    return texto if texto and len(texto) <= maximo and texto.isprintable() else ""


def link_valido(link):
    """Só http(s) com endereço. Nada de javascript:, data: nem espaços escondidos."""
    if not link or len(link) > MAX_LINK or link != link.strip() or any(c.isspace() or not c.isprintable() for c in link):
        return False
    partes = urlparse(link)
    return partes.scheme in ("http", "https") and bool(partes.hostname)


def ler(ambiente):
    """Corpo de /api/anuncio a partir das variáveis de ambiente (um dict como `os.environ`)."""
    bruto = ambiente.get("ANUNCIO_TEXTO", "")
    if not bruto.strip():
        return INATIVO
    texto = limpar(bruto, MAX_TEXTO)
    if not texto:
        _avisar(f"ANUNCIO_TEXTO ignorado: precisa ter de 1 a {MAX_TEXTO} caracteres, numa linha só.")
        return INATIVO
    anuncio = {"ativo": True, "texto": texto, "rotulo": limpar(ambiente.get("ANUNCIO_ROTULO", ""), MAX_ROTULO) or ROTULO_PADRAO}
    link = ambiente.get("ANUNCIO_LINK", "").strip()
    if link:
        if link_valido(link):
            anuncio["link"] = link
        else:
            _avisar("ANUNCIO_LINK ignorado: use um endereço http:// ou https://. O anúncio sai sem link.")
    return anuncio


def do_ambiente():
    return ler(os.environ)


def _avisar(mensagem):
    print(f"Anúncio: {mensagem}", file=sys.stderr, flush=True)
