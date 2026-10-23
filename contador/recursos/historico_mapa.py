"""Replay do mapa: uma foto compacta do mapa por UF a cada mudança, para a página rever a noite estado por estado.

O servidor entrega para cá o resumo por UF que já montou para o mapa; este módulo nunca consulta o TSE. Cada
seleção (ambiente, cargo e turno) é uma série, e só presidente e governador têm mapa. Fica só em memória: uma
foto tem 27 estados de poucos bytes e os limites abaixo mantêm a série pequena.
"""
import threading
from collections import OrderedDict, deque

from contador.recursos.historico import reduzir

CARGOS = ("presidente", "governador")
MAX_FOTOS = 240       # por série; as mais antigas saem primeiro
MAX_SERIES = 12       # séries em memória (ambiente x cargo x turno); sai a menos usada recentemente
MAX_FOTOS_API = 120   # fotos devolvidas por consulta (a série é reduzida por igual)


def foto_do_mapa(corpo, agora):
    """{"t": segundos, "ufs": {uf: [partido do líder, margem, % das seções]}} de um resumo por UF.

    UF sem líder (zerada, empate, sem dados) vai com partido vazio: a página a pinta de neutro.
    """
    ufs = {}
    for uf, resumo in corpo["ufs"].items():
        apurado = round((resumo.get("secoes") or {}).get("percentual", 0.0), 1)
        if resumo["situacao"] == "lider":
            ufs[uf] = [resumo["lider"]["partido"], round(resumo["margem"], 1), apurado]
        else:
            ufs[uf] = ["", 0.0, apurado]
    return {"t": int(agora), "ufs": ufs}


class HistoricoDoMapa:
    def __init__(self):
        self._series = OrderedDict()  # da menos para a mais recentemente usada
        self._trava = threading.Lock()

    def registrar(self, chave, corpo, agora):
        """Guarda a foto se algo mudou desde a última. `chave` é (ambiente, cargo, turno). Devolve True se guardou."""
        if chave[1] not in CARGOS:
            return False
        try:
            foto = foto_do_mapa(corpo, agora)
        except (KeyError, TypeError, AttributeError):  # resumo fora do formato: o mapa já avisa
            return False
        with self._trava:
            serie = self._series.get(chave)
            if serie is None:
                serie = self._series[chave] = deque(maxlen=MAX_FOTOS)
                while len(self._series) > MAX_SERIES:
                    self._series.popitem(last=False)
            self._series.move_to_end(chave)
            if serie and serie[-1]["ufs"] == foto["ufs"]:
                return False
            serie.append(foto)
            return True

    def consultar(self, chave):
        """Corpo de /api/mapa-historico: até MAX_FOTOS_API fotos, da mais antiga para a mais nova."""
        with self._trava:
            serie = self._series.get(chave)
            if serie is None:
                return {"fotos": []}
            self._series.move_to_end(chave)
            fotos = list(serie)
        return {"fotos": reduzir(fotos, MAX_FOTOS_API)}
