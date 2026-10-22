"""Testes de `contador/servidor/validacao.py`."""
import unittest

from contador.servidor.validacao import TOP_MAXIMO, TOP_PADRAO, validar, validar_municipio


class Validar(unittest.TestCase):
    def test_padroes(self):
        self.assertEqual(validar({}), ("presidente", "br", "oficial", 1, TOP_PADRAO))

    def test_top_limitado(self):
        self.assertEqual(validar({"top": ["5000"]})[4], TOP_MAXIMO)
        self.assertEqual(validar({"top": ["0"]})[4], 1)

    def test_entradas_invalidas(self):
        for consulta in (
            {"cargo": ["x"]},
            {"cargo": ["governador"]},  # sem UF
            {"uf": ["../etc"]},
            {"turno": ["3"]},
            {"ambiente": ["https://exemplo.com"]},
            {"top": ["-1"]},
            {"cargo": ["deputado-distrital"], "uf": ["sp"]},
            {"cargo": ["deputado-estadual"], "uf": ["df"]},
            {"cargo": ["senador"], "uf": ["sp"], "turno": ["2"]},
        ):
            with self.subTest(consulta=consulta), self.assertRaises(ValueError):
                validar(consulta)


class ValidarMunicipio(unittest.TestCase):
    def test_sem_municipio(self):
        self.assertEqual(validar_municipio({}, "sp"), "")

    def test_codigo_valido(self):
        self.assertEqual(validar_municipio({"municipio": ["71072"]}, "sp"), "71072")

    def test_recusa_formato_estranho_antes_de_virar_url(self):
        for codigo in ("7107", "710723", "7107a", "../../", "７１０７２"):
            with self.subTest(codigo=codigo), self.assertRaises(ValueError):
                validar_municipio({"municipio": [codigo]}, "sp")

    def test_brasil_inteiro_nao_tem_cidade(self):
        with self.assertRaises(ValueError):
            validar_municipio({"municipio": ["71072"]}, "br")
