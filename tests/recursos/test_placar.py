"""Testes de `contador/recursos/placar.py`."""
import unittest

from contador.recursos import placar
from tests.dados import DADOS


class Resumir(unittest.TestCase):
    def test_estrutura(self):
        resumo = placar.resumir(DADOS, 10)
        self.assertFalse(resumo["final"])
        self.assertEqual(resumo["secoes"], {"total": 1000, "apuradas": 250, "percentual": 25.0})
        self.assertEqual(resumo["votos"]["pct_nulos"], 3.33)
        self.assertEqual([c["nome"] for c in resumo["candidatos"]], ["BIA", "ANA"])
        self.assertEqual(resumo["candidatos"][0]["situacao"], "2º turno")

    def test_top(self):
        resumo = placar.resumir(DADOS, 1)
        self.assertEqual(len(resumo["candidatos"]), 1)
        self.assertEqual(resumo["total_candidatos"], 2)
