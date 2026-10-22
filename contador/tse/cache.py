"""Cache das consultas ao TSE.

Uma consulta por URL serve todos os visitantes. O TSE bloqueia o IP que passar do limite, então este módulo
segura as buscas novas (teto por segundo e por minuto de 404) e reaproveita a resposta de antes.
"""
import threading
import time
from collections import OrderedDict, deque

from contador.tse import cliente

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


class Entrada:
    """Uma URL no cache: o último arquivo, o ETag e até quando vale."""

    def __init__(self):
        self.trava = threading.Lock()
        self.dados = None
        self.etag = None
        self.status = 0
        self.valido_ate = 0.0
        self.verificado_em = 0.0  # último contato bem-sucedido com o TSE (200 ou 304)


class Cache:
    """Arquivos do TSE por URL: todos os visitantes dividem a mesma consulta, com teto de buscas e de 404."""

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

    def espiar(self, url):
        """Dados já guardados para a URL. Não consulta o TSE nem muda a ordem de uso das entradas."""
        with self._trava:
            entrada = self._entradas.get(url)
        return entrada.dados if entrada else None

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
        resposta = cliente.buscar(url, entrada.etag)
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
            entrada.valido_ate = agora + cliente.ESPERA_BLOQUEIO
        else:
            entrada.valido_ate = agora + ESPERA_FALHA
