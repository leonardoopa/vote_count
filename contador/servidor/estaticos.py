"""Arquivos de web/: estilo, scripts, service worker e os desenhos dos mapas."""
import gzip
import hashlib
import re
import threading
from collections import OrderedDict

from contador.caminhos import WEB
from contador.tse import catalogo

SERVICE_WORKER = WEB / "sw.js"

# os únicos caminhos que saem direto de web/; anuncios/ guarda o ícone do anunciante (ANUNCIO_ICONE)
ARQUIVO_WEB = re.compile(r"^/(estilo\.css|js/[a-z0-9-]+\.js|anuncios/[a-z0-9-]+\.(?:png|jpg|webp))$")
TIPOS_DA_WEB = {".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                ".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}
MAX_GZIP = 64
_GZIP = OrderedDict()  # ETag -> conteúdo comprimido
_TRAVA_GZIP = threading.Lock()


def arquivo_da_pasta_web(arquivo, tipo, cabecalhos=None):
    """(status, tipo, corpo, extras) de um arquivo de web/.

    O navegador revalida com ETag (304 sem corpo quando nada mudou) e recebe gzip se aceitar: os desenhos dos
    municípios passam de 100 KB e o texto comprime bem.
    """
    try:
        conteudo = arquivo.read_bytes()
    except OSError:
        return 404, "text/plain; charset=utf-8", b"nao encontrado", {}
    etag = f'W/"{hashlib.sha1(conteudo).hexdigest()[:20]}"'
    extras = {"ETag": etag, "Cache-Control": "no-cache", "Vary": "Accept-Encoding"}
    cabecalhos = cabecalhos or {}
    if etag[2:] in (cabecalhos.get("If-None-Match") or ""):
        return 304, tipo, b"", extras
    if len(conteudo) > 1024 and "gzip" in (cabecalhos.get("Accept-Encoding") or ""):
        with _TRAVA_GZIP:
            if etag not in _GZIP:
                _GZIP[etag] = gzip.compress(conteudo, 6, mtime=0)
                while len(_GZIP) > MAX_GZIP:
                    _GZIP.popitem(last=False)
            _GZIP.move_to_end(etag)
            conteudo = _GZIP[etag]
        extras["Content-Encoding"] = "gzip"
    return 200, tipo, conteudo, extras


def arquivo_da_web(caminho, cabecalhos=None):
    """(status, tipo, corpo, extras) de /estilo.css, /js/<nome>.js ou /anuncios/<nome>.<png|jpg|webp>, ou None se o caminho não é de um deles."""
    if not ARQUIVO_WEB.match(caminho):
        return None
    arquivo = WEB / caminho[1:]
    return arquivo_da_pasta_web(arquivo, TIPOS_DA_WEB[arquivo.suffix], cabecalhos)


def service_worker(consulta, cabecalhos=None):
    return arquivo_da_pasta_web(SERVICE_WORKER, "text/javascript; charset=utf-8", cabecalhos)


GEO = WEB / "geo"  # desenhos dos municípios, um arquivo por UF, e o do mundo (tools/gerar_mapa.py --municipios e --mundo)
ARQUIVO_GEO = re.compile(r"^/geo/([a-z]{2}|mundo|brasil)\.json$")


def desenho_dos_municipios(caminho, cabecalhos=None):
    """(status, tipo, corpo, extras) do arquivo geo/<uf>.json, ou None se o caminho não é de um desenho."""
    achado = ARQUIVO_GEO.match(caminho)
    if not achado or (achado[1] not in ("mundo", "brasil") and achado[1] not in catalogo.UFS):
        return None
    arquivo = GEO / f"{achado[1]}.json"
    if not arquivo.is_file():
        return 404, "text/plain; charset=utf-8", b"desenho indisponivel", {}
    return arquivo_da_pasta_web(arquivo, "application/json; charset=utf-8", cabecalhos)
