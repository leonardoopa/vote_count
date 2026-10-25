"""Espaço de publicidade no topo da página: leitura e validação da configuração.

Tudo vem de variáveis de ambiente (veja .env.example) e é lido uma vez, na partida. Sem
ANUNCIO_TEXTO não há faixa. A página mostra o texto como texto puro (nunca como HTML), com o
rótulo "Publicidade" sempre ao lado, e abre o link numa aba nova, marcado como patrocinado. O clique pode abrir uma conversa de WhatsApp: ANUNCIO_WHATSAPP (o número, com o código do país) vira o
link https://wa.me/<número>?text=<mensagem>, com a mensagem de ANUNCIO_WHATSAPP_MENSAGEM ou uma padrão; ANUNCIO_LINK, se
existir, vale mais. A imagem é opcional
(ANUNCIO_IMAGEM, um endereço http ou https): quem visita a página baixa a imagem direto desse endereço, e o texto fica
sempre junto dela, para quem não a vê. O ícone também é opcional (ANUNCIO_ICONE): uma fotinha pequena ao lado do
texto, como o logo do anunciante. Vale um endereço http(s) ou um arquivo de web/anuncios/ (`/anuncios/<nome>.png`,
`.jpg` ou `.webp`), servido por este mesmo servidor.
"""
import re
import os
import sys
from urllib.parse import quote, urlparse

MAX_TEXTO = 160
MAX_ROTULO = 24
MAX_LINK = 300
MAX_MENSAGEM = 200
MENSAGEM_PADRAO = "Olá! Vi o anúncio no Contador de votos e quero saber mais."
ROTULO_PADRAO = "Publicidade"
INATIVO = {"ativo": False}
ICONE_LOCAL = re.compile(r"^/anuncios/[a-z0-9-]+\.(png|jpg|webp)$")  # arquivos de web/anuncios/, os mesmos que estaticos.py serve


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


def link_do_whatsapp(numero, mensagem):
    """https://wa.me/<número>?text=<mensagem>, ou '' se o número não serve.

    O número vai com o código do país (55 no Brasil); pontuação e espaços são aceitos e saem do link. A mensagem é o que
    a pessoa já encontra escrito ao abrir a conversa.
    """
    numero = numero.strip()
    digitos = "".join(c for c in numero if c.isdigit())
    if not numero or any(not (c.isdigit() or c in " +-()") for c in numero) or not 10 <= len(digitos) <= 15:
        return ""
    return f"https://wa.me/{digitos}?text={quote(mensagem)}"


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
    numero = ambiente.get("ANUNCIO_WHATSAPP", "").strip()
    if numero and "link" in anuncio:
        _avisar("ANUNCIO_WHATSAPP ignorado: ANUNCIO_LINK já está definido e vale mais.")
    elif numero:
        mensagem = limpar(ambiente.get("ANUNCIO_WHATSAPP_MENSAGEM", ""), MAX_MENSAGEM) or MENSAGEM_PADRAO
        anuncio_whatsapp = link_do_whatsapp(numero, mensagem)
        if anuncio_whatsapp:
            anuncio["link"] = anuncio_whatsapp
        else:
            _avisar("ANUNCIO_WHATSAPP ignorado: use o número com o código do país, de 10 a 15 dígitos (ex.: 5581999999999).")
    imagem = ambiente.get("ANUNCIO_IMAGEM", "").strip()
    if imagem:
        if link_valido(imagem):
            anuncio["imagem"] = imagem
        else:
            _avisar("ANUNCIO_IMAGEM ignorado: use um endereço http:// ou https://. O anúncio sai sem imagem.")
    icone = ambiente.get("ANUNCIO_ICONE", "").strip()
    if icone:
        if link_valido(icone) or ICONE_LOCAL.match(icone):
            anuncio["icone"] = icone
        else:
            _avisar("ANUNCIO_ICONE ignorado: use um endereço http:// ou https://, ou /anuncios/<nome>.png (.jpg, .webp). O anúncio sai sem ícone.")
    return anuncio


def do_ambiente():
    return ler(os.environ)


def _avisar(mensagem):
    print(f"Anúncio: {mensagem}", file=sys.stderr, flush=True)
