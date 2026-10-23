"""Testes de `contador/recursos/placar.py`."""
import copy
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

    def test_sem_funcao_de_foto_o_candidato_nao_tem_o_campo(self):
        self.assertNotIn("foto", placar.resumir(DADOS, 10)["candidatos"][0])

    def test_foto_vem_da_funcao_que_recebe_o_sqcand_do_candidato(self):
        dados = copy.deepcopy(DADOS)
        dados["carg"][0]["agr"][0]["par"][0]["cand"][0]["sqcand"] = "111"  # só a Ana tem
        resumo = placar.resumir(dados, 10, lambda sqcand: f"foto/{sqcand}" if sqcand else None)
        self.assertEqual([(c["nome"], c["foto"]) for c in resumo["candidatos"]], [("BIA", None), ("ANA", "foto/111")])

    def test_top(self):
        resumo = placar.resumir(DADOS, 1)
        self.assertEqual(len(resumo["candidatos"]), 1)
        self.assertEqual(resumo["total_candidatos"], 2)
