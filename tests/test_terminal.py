"""Testes de `contador/terminal.py`."""
import unittest
from argparse import Namespace

from contador import terminal
from tests.dados import DADOS


ARGS = Namespace(cargo="presidente", uf="br", turno=1, ambiente="oficial", top=10, intervalo=10)


class Renderizar(unittest.TestCase):
    def test_placar(self):
        texto = terminal.renderizar(DADOS, ARGS)
        self.assertIn("Totalização PARCIAL", texto)
        self.assertIn("seções apuradas 250 de 1.000 (25,00%)", texto)
        self.assertLess(texto.index("BIA"), texto.index("ANA"))
        self.assertIn("2º turno", texto)

    def test_titulo_com_cidade(self):
        args = Namespace(**{**vars(ARGS), "uf": "sp", "cidade_nome": "Campinas"})
        self.assertIn("PRESIDENTE · SP · CAMPINAS", terminal.renderizar(DADOS, args))

    def test_zero_votos_sem_divisao_por_zero(self):
        zerado = {**DADOS, "carg": [{"agr": [{"par": [{"sg": "A", "cand": [{"n": "1", "nm": "X", "vap": "0", "pvap": "0,00"}]}]}]}]}
        self.assertIn("X", terminal.renderizar(zerado, ARGS))

    def test_top_limita_linhas(self):
        texto = terminal.renderizar(DADOS, Namespace(**{**vars(ARGS), "top": 1}))
        self.assertNotIn("ANA", texto)


class Argumentos(unittest.TestCase):
    def test_presidente_padrao_br(self):
        self.assertEqual(terminal.ler_argumentos([]).uf, "br")

    def test_governador_exige_uf(self):
        with self.assertRaises(SystemExit):
            terminal.ler_argumentos(["-c", "governador"])

    def test_cidade_precisa_de_uf(self):
        with self.assertRaises(SystemExit):
            terminal.ler_argumentos(["--cidade", "campinas"])

    def test_cidade_com_uf(self):
        args = terminal.ler_argumentos(["--uf", "sp", "--cidade", "campinas"])
        self.assertEqual((args.uf, args.cidade, args.municipio), ("sp", "campinas", None))

    def test_municipio_so_com_cinco_digitos(self):
        for codigo in ("123", "abcde", "123456", "../../"):
            with self.subTest(codigo=codigo), self.assertRaises(SystemExit):
                terminal.ler_argumentos(["--uf", "sp", "--municipio", codigo])

    def test_cidade_e_municipio_juntos(self):
        with self.assertRaises(SystemExit):
            terminal.ler_argumentos(["--uf", "sp", "--cidade", "campinas", "--municipio", "62910"])

    def test_intervalo_minimo(self):
        with self.assertRaises(SystemExit):
            terminal.ler_argumentos(["--intervalo", "1"])
