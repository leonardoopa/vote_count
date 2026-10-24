"""Pré-aquecimento: ao subir, o servidor já começa a buscar as cidades do mapa do Brasil por município.

Sem isto, a primeira pessoa a abrir o mapa depois de uma partida via os estados (cada município com a cor do estado, mais fraca)
até o varredor terminar o país inteiro. Aqui o servidor faz o primeiro pedido sozinho, para presidente nos dois turnos, e repete
de minuto em minuto até as cidades chegarem (ou por MAX_RODADAS). O teto de buscas por segundo é o mesmo de sempre
(BUSCAS_EXTRAS_POR_SEGUNDO); com HISTORICO_DIR o que já foi buscado volta do disco e quase não há o que buscar.
"""
import os
import threading
import time

from contador.servidor import estado
from contador.servidor.rotas import municipios

TURNOS = ("1", "2")
ESPERA_S = 60
MAX_RODADAS = 60   # no máximo uma hora de insistência


def aquecer(dormir=time.sleep):
    """Pede o mapa do país por município até todas as cidades chegarem. Devolve os turnos que ainda faltavam (vazio = tudo pronto)."""
    pendentes = list(TURNOS)
    for rodada in range(MAX_RODADAS):
        if not estado.VARREDOR.ligado:
            return pendentes
        for turno in list(pendentes):
            try:
                status, corpo = municipios.mapa_municipal_do_brasil({"uf": ["br"], "cargo": ["presidente"], "turno": [turno], "ambiente": ["oficial"]})
            except Exception:   # o aquecimento nunca derruba o servidor
                continue
            if status == 200 and corpo["total"] and corpo["carregadas"] >= corpo["total"]:
                pendentes.remove(turno)
        if not pendentes:
            return pendentes
        dormir(ESPERA_S)
    return pendentes


def iniciar():
    """Começa o aquecimento numa thread à parte. AQUECER_MAPA=0 desliga."""
    if os.environ.get("AQUECER_MAPA", "1") == "0" or not estado.VARREDOR.ligado:
        return None
    thread = threading.Thread(target=aquecer, name="aquecimento", daemon=True)
    thread.start()
    return thread
