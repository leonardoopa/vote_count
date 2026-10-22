"""Varredor: busca em segundo plano os arquivos do TSE que dependem de muitas UFs ou cidades.

Hemiciclo da Câmara, mais votados e mapa por município precisam de dezenas ou centenas de
arquivos. Para não aumentar o risco com o TSE (100 req/s por IP, bloqueio de 10 min):

- uma única thread faz todas as buscas, no máximo `por_segundo` por segundo no total
  (0 desliga o varredor e os recursos que dependem dele);
- só trabalha enquanto alguém está olhando: sem pedido por OCIOSO_S segundos, a thread encerra;
- cada arquivo é revalidado com ETag (resposta 304 não traz corpo) e só o resumo fica em memória;
- 403 ou 429 pausam tudo por 10 min; 3 respostas 404 seguidas pausam por 60 s.

Este módulo não conhece nenhum recurso: cada um registra um grupo de trabalhos com a função que
transforma o arquivo do TSE no resumo que guarda.
"""
import threading
import time

import contador

OCIOSO_S = 300           # sem pedido por este tempo, a thread encerra
PAUSA_BLOQUEIO_S = contador.ESPERA_BLOQUEIO
PAUSA_404_S = 60
LIMITE_404_SEGUIDOS = 3
ESPERA_FALHA_S = 30      # erro de rede ou 5xx: tenta o mesmo arquivo de novo depois disto
MAX_GRUPOS = 64


class Trabalho:
    __slots__ = ("chave", "url", "etag", "resumo", "status", "proxima", "verificado")

    def __init__(self, chave, url):
        self.chave, self.url = chave, url
        self.etag = None
        self.resumo = None      # o que `resumir` devolveu no último 200
        self.status = 0         # último código HTTP (0 = nunca buscado ou sem resposta)
        self.proxima = 0.0      # a partir de quando buscar de novo
        self.verificado = 0.0   # último contato bem-sucedido (200 ou 304)


class Grupo:
    def __init__(self, trabalhos, resumir, intervalo):
        self.trabalhos = trabalhos  # {chave: Trabalho}
        self.resumir = resumir      # (dados do TSE, chave) -> resumo; pode levantar KeyError/ValueError/TypeError
        self.intervalo = intervalo  # resumo -> segundos até buscar de novo
        self.ultimo_pedido = 0.0


class Varredor:
    def __init__(self, por_segundo, buscar=None, relogio=time.time, dormir=time.sleep):
        self.por_segundo = por_segundo
        self.buscar = buscar  # None: usa `contador.buscar` na hora de cada busca (a demonstração troca essa função)
        self.relogio, self.dormir = relogio, dormir
        self._grupos = {}
        self._trava = threading.RLock()
        self._thread = None
        self._pausa_ate = 0.0
        self._seguidos_404 = 0

    @property
    def ligado(self):
        return self.por_segundo > 0

    def pedir(self, nome, fabrica):
        """Marca o grupo como em uso (criando-o com `fabrica()` se for novo) e garante que a thread esteja rodando.

        Devolve o Grupo, ou None com o varredor desligado. `fabrica` devolve (trabalhos, resumir, intervalo).
        """
        if not self.ligado:
            return None
        with self._trava:
            grupo = self._grupos.get(nome)
            if grupo is None:
                grupo = self._grupos[nome] = Grupo(*fabrica())
                while len(self._grupos) > MAX_GRUPOS:
                    self._grupos.pop(next(iter(self._grupos)))
            grupo.ultimo_pedido = self.relogio()
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._rodar, name="varredor", daemon=True)
                self._thread.start()
            return grupo

    def resumos(self, grupo):
        """{chave: (resumo, verificado, status)} dos trabalhos do grupo: uma foto, segura para ler de qualquer thread."""
        with self._trava:
            return {c: (t.resumo, t.verificado, t.status) for c, t in grupo.trabalhos.items()}

    def passo(self):
        """Faz uma busca, se houver algo vencido e a pausa permitir. Devolve True se buscou."""
        with self._trava:
            agora = self.relogio()
            if agora < self._pausa_ate:
                return False
            ativos = [g for g in self._grupos.values() if agora - g.ultimo_pedido < OCIOSO_S]
            candidatos = [(t.proxima, g, t) for g in ativos for t in g.trabalhos.values() if t.proxima <= agora]
            if not candidatos:
                return False
            _, grupo, trabalho = min(candidatos, key=lambda c: c[0])
            etag = trabalho.etag
        resposta = (self.buscar or contador.buscar)(trabalho.url, etag)  # fora da trava: a rede é lenta
        self._registrar(grupo, trabalho, resposta)
        return True

    def _registrar(self, grupo, trabalho, resposta):
        with self._trava:
            agora = self.relogio()
            trabalho.status = resposta.status
            if resposta.status in (200, 304):
                self._seguidos_404 = 0
                if resposta.status == 200:
                    try:
                        trabalho.resumo = grupo.resumir(resposta.dados, trabalho.chave)
                        trabalho.etag = resposta.etag
                    except (KeyError, ValueError, TypeError, IndexError):
                        trabalho.resumo = None  # arquivo fora do formato: o recurso mostra a UF sem dados
                trabalho.verificado = agora
                trabalho.proxima = agora + grupo.intervalo(trabalho.resumo)
            elif resposta.status == 404:
                self._seguidos_404 += 1
                trabalho.proxima = agora + PAUSA_404_S
                if self._seguidos_404 >= LIMITE_404_SEGUIDOS:
                    self._pausa_ate, self._seguidos_404 = agora + PAUSA_404_S, 0
            elif resposta.status in (403, 429):
                self._pausa_ate = agora + PAUSA_BLOQUEIO_S
                trabalho.proxima = agora + PAUSA_BLOQUEIO_S
            else:
                trabalho.proxima = agora + ESPERA_FALHA_S

    def _rodar(self):
        espera = 1.0 / self.por_segundo
        while True:
            with self._trava:
                agora = self.relogio()
                if not any(agora - g.ultimo_pedido < OCIOSO_S for g in self._grupos.values()):
                    self._thread = None
                    return
            self.dormir(espera if self.passo() else 1.0)
