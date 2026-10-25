"""Varredor: busca em segundo plano os arquivos do TSE que dependem de muitas UFs ou cidades.

Hemiciclo da Câmara, mais votados e mapa por município precisam de dezenas ou centenas de
arquivos. Para não aumentar o risco com o TSE (100 req/s por IP, bloqueio de 10 min):

- uma única thread faz todas as buscas, no máximo `por_segundo` por segundo no total
  (0 desliga o varredor e os recursos que dependem dele);
- só trabalha enquanto alguém está olhando: sem pedido por OCIOSO_S segundos, a thread encerra;
- cada arquivo é revalidado com ETag (resposta 304 não traz corpo) e só o resumo fica em memória;
- 403 ou 429 pausam tudo por 10 min; 3 respostas 404 seguidas pausam por 60 s;
- o que a pessoa está olhando (`priorizar`) passa na frente: o mesmo teto vale, só muda a ordem;
- com uma `pasta`, os resumos vão para o disco (a cada SALVAR_S e quando a thread encerra) e voltam quando o grupo é pedido
  de novo: depois de reiniciar o servidor, o mapa já nasce preenchido e cada arquivo só é revalidado na hora dele.

Este módulo não conhece nenhum recurso: cada um registra um grupo de trabalhos com a função que
transforma o arquivo do TSE no resumo que guarda.
"""
import hashlib
import json
import math
import os
import threading
import time

from contador.tse import cliente


OCIOSO_S = 300           # sem pedido por este tempo, a thread encerra
PAUSA_BLOQUEIO_S = cliente.ESPERA_BLOQUEIO
PAUSA_404_S = 60
LIMITE_404_SEGUIDOS = 3
ESPERA_FALHA_S = 30      # erro de rede ou 5xx: tenta o mesmo arquivo de novo depois disto
MAX_GRUPOS = 64
FOCO_S = 90              # tempo que uma prioridade dura se a página não a renovar
BUSCAS_POR_AJUDANTE = 3  # acima de 5 buscas por segundo entram mais threads: uma só não passa de ~3 por segundo (a rede demora)
MAX_TRABALHADORES = 8
RESERVA_S = 60           # a busca que uma thread começou fica reservada por isto, para outra não pegar o mesmo arquivo
SALVAR_S = 60            # de quanto em quanto tempo os resumos novos vão para o disco


class Trabalho:
    __slots__ = ("chave", "url", "etag", "resumo", "status", "proxima", "verificado", "foco_ate", "foco_pos")

    def __init__(self, chave, url):
        self.chave, self.url = chave, url
        self.etag = None
        self.resumo = None      # o que `resumir` devolveu no último 200
        self.status = 0         # último código HTTP (0 = nunca buscado ou sem resposta)
        self.proxima = 0.0      # a partir de quando buscar de novo
        self.verificado = 0.0   # último contato bem-sucedido (200 ou 304)
        self.foco_ate = 0.0     # enquanto o relógio estiver antes disto, o trabalho fura a fila
        self.foco_pos = 0       # e, entre os que furam a fila, o de menor posição vai primeiro


class Grupo:
    def __init__(self, trabalhos, resumir, intervalo):
        self.nome = None            # preenchido por `pedir`; dá o nome do arquivo no disco
        self.trabalhos = trabalhos  # {chave: Trabalho}
        self.resumir = resumir      # (dados do TSE, chave) -> resumo; pode levantar KeyError/ValueError/TypeError
        self.intervalo = intervalo  # resumo -> segundos até buscar de novo
        self.ultimo_pedido = 0.0


class Varredor:
    def __init__(self, por_segundo, buscar=None, relogio=time.time, dormir=time.sleep, pasta=None):
        self.por_segundo = por_segundo
        self.pasta = pasta     # onde guardar os resumos entre uma execução e outra (None: só na memória)
        self._sujos = set()    # grupos com resumo novo ainda não gravado
        self._salvo_em = 0.0
        self.buscar = buscar  # None: usa `cliente.buscar` na hora de cada busca (a demonstração troca essa função)
        self.relogio, self.dormir = relogio, dormir
        self._grupos = {}
        self._trava = threading.RLock()
        self._thread = None
        self._ajudantes = []    # threads a mais, só quando o teto por segundo pede (veja `trabalhadores`)
        self._pausa_ate = 0.0
        self._seguidos_404 = 0

    @property
    def ligado(self):
        return self.por_segundo > 0

    @property
    def trabalhadores(self):
        """Quantas threads buscam ao mesmo tempo: uma até 5 buscas por segundo; acima disso, o bastante para o teto ser atingível.

        O teto continua valendo para o conjunto: cada thread espera `trabalhadores / por_segundo` entre uma busca e a próxima.
        """
        if self.por_segundo <= 5:
            return 1
        return min(MAX_TRABALHADORES, math.ceil(self.por_segundo / BUSCAS_POR_AJUDANTE))

    def pedir(self, nome, fabrica, total=None):
        """Marca o grupo como em uso (criando-o com `fabrica()` se for novo) e garante que a thread esteja rodando.

        Devolve o Grupo, ou None com o varredor desligado. `fabrica` devolve (trabalhos, resumir, intervalo).
        Com `total`, um grupo que nasceu com menos trabalhos que isso é refeito com `fabrica()`, mantendo o que já foi
        buscado: sem isso, um grupo criado enquanto o TSE ainda não tinha respondido ficava vazio até reiniciar.
        """
        if not self.ligado:
            return None
        with self._trava:
            grupo = self._grupos.get(nome)
            if grupo is None:
                grupo = self._grupos[nome] = Grupo(*fabrica())
                grupo.nome = nome
                self._carregar(grupo)
                while len(self._grupos) > MAX_GRUPOS:
                    self._grupos.pop(next(iter(self._grupos)))
            elif total is not None and len(grupo.trabalhos) < total:
                trabalhos, grupo.resumir, grupo.intervalo = fabrica()
                velhos = grupo.trabalhos
                grupo.trabalhos = {chave: velhos.get(chave, novo) for chave, novo in trabalhos.items()}
                novos = [t for chave, t in grupo.trabalhos.items() if chave not in velhos]
                self._carregar(grupo, so=novos)
            grupo.ultimo_pedido = self.relogio()
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._rodar, name="varredor", daemon=True)
                self._thread.start()
            self._ajudantes = [t for t in self._ajudantes if t.is_alive()]
            while len(self._ajudantes) < self.trabalhadores - 1:
                ajudante = threading.Thread(target=self._rodar, args=(False,), name="varredor-ajudante", daemon=True)
                self._ajudantes.append(ajudante)
                ajudante.start()
            return grupo

    def priorizar(self, grupo, chaves):
        """As `chaves`, em ordem, passam na frente dos outros trabalhos do grupo por FOCO_S segundos (o que a pessoa vê agora).

        Cada chamada troca a lista anterior. Chaves desconhecidas são ignoradas.
        """
        with self._trava:
            ate = self.relogio() + FOCO_S
            for trabalho in grupo.trabalhos.values():
                trabalho.foco_ate = 0.0
            for posicao, chave in enumerate(chaves):
                trabalho = grupo.trabalhos.get(chave)
                if trabalho is not None:
                    trabalho.foco_ate, trabalho.foco_pos = ate, posicao

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
            candidatos = [((0, t.foco_pos) if t.foco_ate > agora else (1, 0), t.proxima, g, t)
                          for g in ativos for t in g.trabalhos.values() if t.proxima <= agora]
            if not candidatos:
                return False
            _, _, grupo, trabalho = min(candidatos, key=lambda c: c[:2])
            etag = trabalho.etag
            trabalho.proxima = agora + RESERVA_S   # reservado: outra thread não pega o mesmo arquivo enquanto a rede responde
        resposta = (self.buscar or cliente.buscar)(trabalho.url, etag)  # fora da trava: a rede é lenta
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
                        self._sujos.add(grupo.nome)
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

    def _arquivo(self, nome):
        return os.path.join(self.pasta, "varredor-" + hashlib.sha1(repr(nome).encode()).hexdigest()[:16] + ".json")

    def _carregar(self, grupo, so=None):
        """Devolve ao grupo recém-criado (ou só aos trabalhos `so`) os resumos que ficaram no disco (com o ETag, para a revalidação custar um 304)."""
        if not self.pasta:
            return
        try:
            with open(self._arquivo(grupo.nome), encoding="utf-8") as arquivo:
                salvo = json.load(arquivo)["resumos"]
        except (OSError, ValueError, KeyError, TypeError):
            return
        for trabalho in grupo.trabalhos.values() if so is None else so:
            item = salvo.get(trabalho.chave) if isinstance(salvo, dict) else None
            if not (isinstance(item, list) and len(item) == 3 and isinstance(item[0], dict)):
                continue
            trabalho.resumo, trabalho.etag, trabalho.verificado = item
            trabalho.status = 200
            trabalho.proxima = trabalho.verificado + grupo.intervalo(trabalho.resumo)   # a hora dele, como se o servidor não tivesse parado

    def salvar(self):
        """Grava no disco os grupos que receberam resumo novo. Erro de disco não derruba o varredor."""
        if not self.pasta:
            return
        with self._trava:
            instantaneos = []
            for nome in self._sujos:
                grupo = self._grupos.get(nome)
                if grupo is not None:
                    instantaneos.append((nome, {c: [t.resumo, t.etag, t.verificado] for c, t in grupo.trabalhos.items() if t.resumo}))
            self._sujos.clear()
            self._salvo_em = self.relogio()
        try:
            os.makedirs(self.pasta, exist_ok=True)
            for nome, resumos in instantaneos:
                arquivo = self._arquivo(nome)
                with open(arquivo + ".tmp", "w", encoding="utf-8") as saida:
                    json.dump({"versao": 1, "resumos": resumos}, saida, separators=(",", ":"))
                os.replace(arquivo + ".tmp", arquivo)
        except (OSError, TypeError, ValueError):
            with self._trava:
                self._sujos.update(nome for nome, _ in instantaneos)   # tenta de novo na próxima

    def _rodar(self, principal=True):
        espera = self.trabalhadores / self.por_segundo
        while True:
            with self._trava:
                agora = self.relogio()
                ocioso = not any(agora - g.ultimo_pedido < OCIOSO_S for g in self._grupos.values())
                if ocioso and principal:
                    self._thread = None
                precisa_salvar = bool(self._sujos) and (ocioso or agora - self._salvo_em >= SALVAR_S)
            if precisa_salvar:
                self.salvar()   # fora da trava: o disco também é lento
            if ocioso:
                return
            inicio = self.relogio()
            buscou = self.passo()
            self.dormir(max(0.0, espera - (self.relogio() - inicio)) if buscou else 1.0)   # a rede já gastou parte da espera
