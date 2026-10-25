"""Contagem de acessos: visitas à página, pessoas diferentes e cliques no anúncio, por hora (horário de Brasília).

Sem cookie e sem guardar IP: cada pessoa vira um hash de IP + navegador com um sal que troca todo dia, e só o hash
do dia corrente fica na memória (e no disco, para um reinício não contar todo mundo de novo). Os números vão para
HISTORICO_DIR/acessos.json no máximo a cada SALVAR_S segundos. Quem olha os números é /api/acessos, protegida por
ACESSOS_CHAVE (sem a variável a rota não existe).
"""
import hashlib
import json
import os
import secrets
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

BRASILIA = timezone(timedelta(hours=-3))
SALVAR_S = 30
HORAS_NO_RESUMO = 48
DIAS_GUARDADOS = 60


class Acessos:
    def __init__(self, pasta=None, relogio=time.time):
        self.arquivo = os.path.join(pasta, "acessos.json") if pasta else None
        self.relogio = relogio
        self._trava = threading.Lock()
        self.horas = {}      # "AAAA-MM-DD HH" -> {"visitas", "pessoas", "cliques"}
        self.dias = {}       # "AAAA-MM-DD" -> {"visitas", "pessoas", "cliques"}
        self._dia, self._sal, self._vistos = None, "", set()   # pessoas já contadas hoje (hashes)
        self._vistos_na_hora = {}                              # "AAAA-MM-DD HH" -> hashes, só a hora corrente
        self._salvo_em, self._sujo = 0.0, False
        self._carregar()

    def _agora(self):
        agora = datetime.fromtimestamp(self.relogio(), BRASILIA)
        return agora.strftime("%Y-%m-%d"), agora.strftime("%Y-%m-%d %H")

    def _virar_o_dia(self, dia):
        if dia != self._dia:
            self._dia, self._sal, self._vistos = dia, secrets.token_hex(16), set()

    def _somar(self, chave_hora, dia, campo):
        self.horas.setdefault(chave_hora, {"visitas": 0, "pessoas": 0, "cliques": 0})[campo] += 1
        self.dias.setdefault(dia, {"visitas": 0, "pessoas": 0, "cliques": 0})[campo] += 1

    def visita(self, ip, navegador):
        """Uma abertura da página. Conta também a pessoa, se ela ainda não apareceu nesta hora ou neste dia."""
        with self._trava:
            dia, hora = self._agora()
            self._virar_o_dia(dia)
            pessoa = hashlib.sha256(f"{self._sal}|{ip}|{navegador}".encode()).hexdigest()[:20]
            self._somar(hora, dia, "visitas")
            if pessoa not in self._vistos:
                self._vistos.add(pessoa)
                self.dias[dia]["pessoas"] += 1
            na_hora = self._vistos_na_hora.setdefault(hora, set())
            if pessoa not in na_hora:
                na_hora.add(pessoa)
                self.horas[hora]["pessoas"] += 1
            for antiga in [h for h in self._vistos_na_hora if h != hora]:
                del self._vistos_na_hora[antiga]
            self._sujo = True
        self.salvar()

    def clique(self):
        """Um clique no anúncio (a passagem por /ir/anuncio)."""
        with self._trava:
            dia, hora = self._agora()
            self._virar_o_dia(dia)
            self._somar(hora, dia, "cliques")
            self._sujo = True
        self.salvar()

    def resumo(self):
        """Corpo de /api/acessos: hoje, as últimas horas e os dias."""
        with self._trava:
            dia, hora = self._agora()
            horas = sorted(self.horas)[-HORAS_NO_RESUMO:]
            return {
                "agora": hora,
                "hoje": self.dias.get(dia, {"visitas": 0, "pessoas": 0, "cliques": 0}),
                "total_de_cliques": sum(d["cliques"] for d in self.dias.values()),
                "por_hora": [{"hora": h, **self.horas[h]} for h in reversed(horas)],
                "por_dia": [{"dia": d, **self.dias[d]} for d in sorted(self.dias, reverse=True)],
                "observacao": "pessoas = navegadores diferentes (IP + navegador), contados uma vez por hora e uma vez por dia",
            }

    def salvar(self, forcar=False):
        """Grava no disco, no máximo a cada SALVAR_S segundos. Erro de disco não derruba a página."""
        if not self.arquivo:
            return
        with self._trava:
            if not self._sujo or (not forcar and self.relogio() - self._salvo_em < SALVAR_S):
                return
            for velho in sorted(self.dias)[:-DIAS_GUARDADOS]:
                del self.dias[velho]
            limite = min(self.dias) if self.dias else ""
            self.horas = {h: v for h, v in self.horas.items() if h[:10] >= limite}
            dados = {"horas": self.horas, "dias": self.dias, "dia": self._dia, "sal": self._sal, "vistos": sorted(self._vistos),
                     "vistos_na_hora": {h: sorted(v) for h, v in self._vistos_na_hora.items()}}
            self._salvo_em, self._sujo = self.relogio(), False
        try:
            temporario = self.arquivo + ".tmp"
            with open(temporario, "w", encoding="utf-8") as arquivo:
                json.dump(dados, arquivo)
            os.replace(temporario, self.arquivo)
        except OSError as erro:
            print(f"Acessos: não consegui gravar {self.arquivo}: {erro}", file=sys.stderr, flush=True)

    def _carregar(self):
        if not self.arquivo:
            return
        try:
            with open(self.arquivo, encoding="utf-8") as arquivo:
                dados = json.load(arquivo)
            self.horas, self.dias = dict(dados["horas"]), dict(dados["dias"])
            self._dia, self._sal, self._vistos = dados.get("dia"), dados.get("sal", ""), set(dados.get("vistos", []))
            self._vistos_na_hora = {h: set(v) for h, v in dados.get("vistos_na_hora", {}).items()}
        except (OSError, ValueError, KeyError, TypeError):
            pass   # sem arquivo ou estragado: começa do zero


def ip_do_visitante(cabecalhos, endereco):
    """O IP de quem pediu: o primeiro do X-Forwarded-For (o Caddy na frente) ou o da conexão."""
    encaminhado = (cabecalhos.get("X-Forwarded-For") or "").split(",")[0].strip()
    return encaminhado or endereco


def do_ambiente():
    return Acessos(os.environ.get("HISTORICO_DIR") or None)
