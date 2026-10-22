"""Histórico da apuração: um ponto do placar a cada totalização nova do TSE.

O servidor entrega para cá os dados que já tem no cache; este módulo nunca consulta o TSE. Cada
seleção (ambiente, cargo, UF, turno e cidade) é uma série, e só presidente, governador e senador
têm série. Os pontos alimentam o gráfico de evolução e o replay da página.

Sem pasta configurada o histórico fica só em memória. Com `HISTORICO_DIR`, cada ponto novo também
é acrescentado a um arquivo JSONL, relido na partida, para sobreviver a um reinício.
"""
import json
import os
import sys
import threading
from collections import OrderedDict, deque

from contador.tse import catalogo, leitura


CARGOS = ("presidente", "governador", "senador")
MAX_PONTOS = 600      # por série; os mais antigos saem primeiro
MAX_SERIES = 120      # séries em memória; sai a menos usada recentemente
MAX_CANDIDATOS = 12   # por ponto, os mais votados
MAX_PONTOS_API = 120  # pontos devolvidos por consulta (a série é reduzida por igual)
MAX_EVENTOS = 40      # itens do feed de atualizações
ARQUIVO = "historico.jsonl"
MAX_ARQUIVO = 64 * 1024 * 1024  # passou disso, para de gravar: o disco da VPS não é infinito
CAMPOS_DO_PONTO = {"totalizacao", "percentual", "apuradas", "secoes", "final", "placar"}


def codigo_situacao(cand):
    """'e' eleito, '2' vai ao 2º turno, '' nenhum dos dois (inclui "não eleito" e antes de decidir)."""
    marca = (cand.get("st") or "").lower()
    if marca.startswith("eleito"):
        return "e"
    return "2" if marca.startswith("2") else ""


def ponto_de(dados):
    """(ponto, nomes) a partir do arquivo do TSE. O ponto é JSON puro; `nomes` é {número: [nome, partido]}.

    Cada linha de `placar` é [número, votos, percentual sobre os válidos, situação], do mais votado
    ao menos votado. Antes da apuração, `totalizacao` vem vazia e todos os votos são zero.
    """
    secoes = dados["s"]
    ranking = leitura.candidatos(dados)[:MAX_CANDIDATOS]
    ponto = {
        "totalizacao": f"{dados.get('dt', '')} {dados.get('ht', '')}".strip(),
        "percentual": leitura.decimal(secoes["pst"]),
        "apuradas": leitura.inteiro(secoes["st"]),
        "secoes": leitura.inteiro(secoes["ts"]),
        "final": dados.get("tf") == "s",
        "placar": [
            [str(c["n"]), leitura.inteiro(c["vap"]), leitura.decimal(c["pvap"]), codigo_situacao(c)]
            for c in ranking
        ],
    }
    nomes = {str(c["n"]): [c.get("nmu") or c["nm"], c["partido"]] for c in ranking}
    return ponto, nomes


def zerado(ponto):
    """Antes de a apuração começar ninguém tem voto: serve de origem do replay, não entra no gráfico."""
    return not any(linha[1] for linha in ponto["placar"])


def reduzir(itens, maximo):
    """No máximo `maximo` itens espalhados por igual, sempre com o primeiro e o último."""
    total = len(itens)
    if total <= maximo:
        return list(itens)
    return [itens[round(i * (total - 1) / (maximo - 1))] for i in range(maximo)]


def variacao(delta):
    """'+0,30' ou '−0,10' (pontos percentuais)."""
    return f"{'+' if delta >= 0 else '−'}{leitura.numero_br(abs(delta))}"


def eventos_do_ponto(anterior, atual, nomes):
    """Eventos desta totalização em relação à anterior, em ordem cronológica: o resumo vem antes dos destaques."""
    if zerado(atual):
        return []
    nome = lambda numero: nomes.get(numero, [numero, ""])[0]
    antes = {linha[0]: linha for linha in anterior["placar"]} if anterior else {}
    andamento = f"{leitura.numero_br(atual['percentual'])}% das seções apuradas"
    if anterior is None or zerado(anterior):
        inicio = "Primeira totalização registrada por este servidor" if anterior is None else "A apuração começou"
        resumo = ("inicio", f"{inicio}: {andamento}.")
    else:
        novas = atual["apuradas"] - anterior["apuradas"]
        topo = []
        for numero, _, percentual, _ in atual["placar"][:2]:
            if numero in antes:
                topo.append(f"{nome(numero)} {leitura.numero_br(percentual)}% ({variacao(percentual - antes[numero][2])})")
            else:
                topo.append(f"{nome(numero)} {leitura.numero_br(percentual)}%")
        quanto = f"+{leitura.milhar(novas)} seções apuradas ({leitura.numero_br(atual['percentual'])}% do total)" if novas > 0 else "Placar atualizado"
        resumo = ("totalizacao", f"{quanto}. {'; '.join(topo)}.")
    eventos = [resumo]
    if anterior and not zerado(anterior):
        lider, antigo = atual["placar"][0][0], anterior["placar"][0][0]
        if lider != antigo:
            eventos.append(("lider", f"{nome(lider)} passou à frente de {nome(antigo)}."))
    for numero, _, _, situacao in atual["placar"]:
        era = antes[numero][3] if numero in antes else ""
        if situacao == "e" and era != "e":
            eventos.append(("eleito", f"{nome(numero)} foi eleito."))
        elif situacao == "2" and era != "2":
            eventos.append(("segundo_turno", f"{nome(numero)} vai ao 2º turno."))
    if atual["final"] and not (anterior and anterior["final"]):
        eventos.append(("final", f"Apuração concluída: {andamento}."))
    return [{"hora": atual["totalizacao"], "tipo": tipo, "texto": texto} for tipo, texto in eventos]


def eventos(pontos, nomes, maximo=MAX_EVENTOS):
    """Feed de atualizações: compara cada totalização com a anterior. Do mais recente para o mais antigo."""
    todos, anterior = [], None
    for ponto in pontos:
        todos.extend(eventos_do_ponto(anterior, ponto, nomes))
        anterior = ponto
    return todos[::-1][:maximo]


def ponto_valido(ponto):
    """Confere um ponto lido do arquivo: linha adulterada ou de outra versão não pode quebrar a API."""
    try:
        return (
            set(ponto) == CAMPOS_DO_PONTO
            and isinstance(ponto["totalizacao"], str)
            and isinstance(ponto["percentual"], (int, float))
            and isinstance(ponto["apuradas"], int)
            and isinstance(ponto["secoes"], int)
            and isinstance(ponto["final"], bool)
            and len(ponto["placar"]) <= MAX_CANDIDATOS
            and all(
                isinstance(numero, str) and isinstance(votos, int)
                and isinstance(pct, (int, float)) and situacao in ("", "e", "2")
                for numero, votos, pct, situacao in ponto["placar"]
            )
        )
    except (TypeError, ValueError):
        return False


def nomes_validos(nomes):
    return isinstance(nomes, dict) and all(
        isinstance(numero, str) and isinstance(par, list) and len(par) == 2
        and all(isinstance(texto, str) for texto in par)
        for numero, par in nomes.items()
    )


def chave_valida(chave):
    return (
        isinstance(chave, tuple) and len(chave) == 5
        and chave[0] in catalogo.AMBIENTES and chave[1] in CARGOS
        and isinstance(chave[2], str) and chave[3] in (1, 2) and isinstance(chave[4], str)
    )


class Serie:
    __slots__ = ("pontos", "ultimo", "nomes")

    def __init__(self):
        # Cada ponto fica como JSON compacto: ocupa umas cinco vezes menos memória que o dict, e
        # 120 séries de 600 pontos cabem folgadamente. `ultimo` guarda o mais recente já como dict.
        self.pontos = deque(maxlen=MAX_PONTOS)
        self.ultimo = None
        self.nomes = {}


class Historico:
    def __init__(self, diretorio=None):
        self._series = OrderedDict()  # da menos para a mais recentemente usada
        self._trava = threading.Lock()
        self._caminho = None
        self._tamanho = 0
        self._quebra_pendente = False  # a última linha do arquivo ficou cortada
        if diretorio:
            try:
                os.makedirs(diretorio, exist_ok=True)
                self._caminho = os.path.join(diretorio, ARQUIVO)
            except OSError as erro:
                self._avisar(diretorio, erro)
        if self._caminho:
            self._carregar()

    def registrar(self, chave, dados):
        """Guarda o ponto desta totalização se algo mudou desde o último. Devolve True se guardou."""
        if chave[1] not in CARGOS:
            return False
        try:
            ponto, nomes = ponto_de(dados)
        except (KeyError, TypeError, ValueError):  # arquivo fora do formato: o placar já avisa
            return False
        with self._trava:
            return self._acrescentar(chave, ponto, nomes, gravar=True)

    def consultar(self, chave):
        """Corpo de /api/historico: os candidatos da série e até MAX_PONTOS_API pontos."""
        with self._trava:
            serie = self._series.get(chave)
            if serie is None:
                return {"candidatos": [], "pontos": []}
            self._series.move_to_end(chave)
            textos, nomes = list(serie.pontos), dict(serie.nomes)
        pontos = [json.loads(texto) for texto in reduzir(textos, MAX_PONTOS_API)]
        ordem = [linha[0] for linha in pontos[-1]["placar"]]  # os mais votados agora, primeiro
        ordem += sorted(numero for numero in nomes if numero not in ordem)
        candidatos = [{"numero": n, "nome": nomes[n][0], "partido": nomes[n][1]} for n in ordem if n in nomes]
        return {"candidatos": candidatos, "pontos": pontos}

    def atualizacoes(self, chave):
        """Corpo de /api/atualizacoes: o que mudou entre totalizações vizinhas, do mais recente para o mais antigo."""
        with self._trava:
            serie = self._series.get(chave)
            if serie is None:
                return {"eventos": []}
            self._series.move_to_end(chave)
            textos, nomes = list(serie.pontos), dict(serie.nomes)
        return {"eventos": eventos([json.loads(texto) for texto in textos], nomes)}

    def _acrescentar(self, chave, ponto, nomes, gravar):
        serie = self._series.get(chave)
        if serie is None:
            serie = self._series[chave] = Serie()
            while len(self._series) > MAX_SERIES:
                self._series.popitem(last=False)
        self._series.move_to_end(chave)
        if serie.ultimo == ponto:
            return False
        novos = {numero: par for numero, par in nomes.items() if serie.nomes.get(numero) != par}
        serie.nomes.update(novos)
        serie.ultimo = ponto
        serie.pontos.append(json.dumps(ponto, ensure_ascii=False, separators=(",", ":")))
        if gravar:
            self._gravar(chave, ponto, novos)
        return True

    def _carregar(self):
        try:
            with open(self._caminho, "rb") as arquivo:
                for bruto in arquivo:
                    self._tamanho += len(bruto)
                    self._quebra_pendente = not bruto.endswith(b"\n")
                    try:
                        registro = json.loads(bruto)
                        chave, ponto, nomes = tuple(registro["k"]), registro["p"], registro.get("n") or {}
                    except (ValueError, KeyError, TypeError):
                        continue  # linha corrompida: segue com as outras
                    if chave_valida(chave) and ponto_valido(ponto) and nomes_validos(nomes):
                        self._acrescentar(chave, ponto, nomes, gravar=False)
        except FileNotFoundError:
            pass
        except OSError as erro:
            self._avisar(self._caminho, erro)

    def _gravar(self, chave, ponto, novos):
        if not self._caminho:
            return
        if self._tamanho > MAX_ARQUIVO:
            self._avisar(self._caminho, "arquivo grande demais")
            return
        linha = json.dumps({"k": chave, "p": ponto, "n": novos}, ensure_ascii=False, separators=(",", ":")) + "\n"
        if self._quebra_pendente:
            linha = "\n" + linha  # não cola o ponto novo na linha que ficou cortada
        try:
            with open(self._caminho, "a", encoding="utf-8") as arquivo:
                arquivo.write(linha)
        except OSError as erro:
            self._avisar(self._caminho, erro)
            return
        self._quebra_pendente = False
        self._tamanho += len(linha)

    def _avisar(self, local, erro):
        """Falha de disco não derruba nada: avisa uma vez e segue só em memória."""
        print(f"Histórico: sem gravar em {local} ({erro}). Segue só em memória.", file=sys.stderr, flush=True)
        self._caminho = None


def do_ambiente():
    """O histórico do servidor: grava na pasta de HISTORICO_DIR, se a variável existir."""
    return Historico(os.environ.get("HISTORICO_DIR"))
