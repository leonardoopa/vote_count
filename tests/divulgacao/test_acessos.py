"""Testes de `contador/divulgacao/acessos.py`."""
import json
import os
import tempfile
import unittest
from unittest import mock

from contador.divulgacao import acessos

# 25/10/2026 20:30 em Brasília (23:30 UTC)
NOITE = 1792971000.0


class Relogio:
    def __init__(self, t=NOITE):
        self.t = t

    def __call__(self):
        return self.t


class Contagem(unittest.TestCase):
    def test_visitas_pessoas_e_cliques_por_hora(self):
        a = acessos.Acessos(relogio=Relogio())
        a.visita("1.1.1.1", "Firefox")
        a.visita("1.1.1.1", "Firefox")   # a mesma pessoa recarregando
        a.visita("2.2.2.2", "Safari")
        a.clique()
        resumo = a.resumo()
        self.assertEqual(resumo["hoje"], {"visitas": 3, "pessoas": 2, "cliques": 1})
        self.assertEqual(resumo["por_hora"][0], {"hora": "2026-10-25 20", "visitas": 3, "pessoas": 2, "cliques": 1})
        self.assertEqual(resumo["total_de_cliques"], 1)

    def test_a_mesma_pessoa_conta_de_novo_na_hora_seguinte_mas_nao_no_dia(self):
        relogio = Relogio()
        a = acessos.Acessos(relogio=relogio)
        a.visita("1.1.1.1", "Firefox")
        relogio.t += 3600
        a.visita("1.1.1.1", "Firefox")
        resumo = a.resumo()
        self.assertEqual([h["pessoas"] for h in resumo["por_hora"]], [1, 1])
        self.assertEqual(resumo["hoje"]["pessoas"], 1)

    def test_dia_novo_zera_as_pessoas_vistas(self):
        relogio = Relogio()
        a = acessos.Acessos(relogio=relogio)
        a.visita("1.1.1.1", "Firefox")
        relogio.t += 86400
        a.visita("1.1.1.1", "Firefox")
        self.assertEqual([d["pessoas"] for d in a.resumo()["por_dia"]], [1, 1])

    def test_nao_guarda_ip_no_disco_e_recarrega_os_numeros(self):
        with tempfile.TemporaryDirectory() as pasta:
            a = acessos.Acessos(pasta, relogio=Relogio())
            a.visita("203.0.113.9", "Firefox")
            a.clique()
            a.salvar(forcar=True)
            with open(os.path.join(pasta, "acessos.json"), encoding="utf-8") as arquivo:
                texto = arquivo.read()
            self.assertNotIn("203.0.113.9", texto)
            json.loads(texto)
            de_novo = acessos.Acessos(pasta, relogio=Relogio())
            de_novo.visita("203.0.113.9", "Firefox")   # depois de reiniciar, a mesma pessoa não conta outra vez
            self.assertEqual(de_novo.resumo()["hoje"], {"visitas": 2, "pessoas": 1, "cliques": 1})

    def test_arquivo_estragado_comeca_do_zero(self):
        with tempfile.TemporaryDirectory() as pasta:
            with open(os.path.join(pasta, "acessos.json"), "w", encoding="utf-8") as arquivo:
                arquivo.write("{nao e json")
            self.assertEqual(acessos.Acessos(pasta, relogio=Relogio()).resumo()["hoje"], {"visitas": 0, "pessoas": 0, "cliques": 0})

    def test_ip_vem_do_caddy_ou_da_conexao(self):
        self.assertEqual(acessos.ip_do_visitante({"X-Forwarded-For": "200.1.2.3, 172.18.0.5"}, "172.18.0.5"), "200.1.2.3")
        self.assertEqual(acessos.ip_do_visitante({}, "10.0.0.1"), "10.0.0.1")
