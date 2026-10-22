"""Testes de `contador/tse/leitura.py`."""
import unittest

from contador.tse import leitura
from tests.dados import CONFIG_MUNICIPIOS, DADOS


class Candidatos(unittest.TestCase):
    def test_ordem_por_votos(self):
        self.assertEqual([c["nm"] for c in leitura.candidatos(DADOS)], ["BIA", "ANA"])

    def test_partido_anexado(self):
        self.assertEqual(leitura.candidatos(DADOS)[0]["partido"], "AAA")


class Cidades(unittest.TestCase):
    def test_nome_proprio(self):
        self.assertEqual(leitura.nome_proprio("SÃO PAULO"), "São Paulo")
        self.assertEqual(leitura.nome_proprio("SÃO JOÃO DEL REI"), "São João del Rei")
        self.assertEqual(leitura.nome_proprio("SANTA BÁRBARA D'OESTE"), "Santa Bárbara D'Oeste")
        self.assertEqual(leitura.nome_proprio("DE"), "De")  # a primeira palavra nunca fica minúscula

    def test_lista_da_uf_em_ordem_alfabetica_sem_acento(self):
        nomes = [m["nome"] for m in leitura.municipios(CONFIG_MUNICIPIOS, "sp")]
        self.assertEqual(nomes, ["Campinas", "São João da Boa Vista", "São João del Rei", "São Paulo"])

    def test_capital_marcada(self):
        capital = [m for m in leitura.municipios(CONFIG_MUNICIPIOS, "sp") if m["capital"]]
        self.assertEqual([m["codigo"] for m in capital], ["71072"])

    def test_uf_desconhecida_devolve_vazio(self):
        self.assertEqual(leitura.municipios(CONFIG_MUNICIPIOS, "xx"), [])

    def test_cidade_pelo_codigo(self):
        lista = leitura.municipios(CONFIG_MUNICIPIOS, "sp")
        self.assertEqual(leitura.cidade_por_codigo(lista, "71072")["nome"], "São Paulo")
        self.assertIsNone(leitura.cidade_por_codigo(lista, "00000"))

    def test_achar_ignora_acento_e_caixa(self):
        lista = leitura.municipios(CONFIG_MUNICIPIOS, "sp")
        cidade, _ = leitura.achar_municipio(lista, "sao paulo")
        self.assertEqual(cidade["codigo"], "71072")

    def test_achar_por_trecho_unico(self):
        lista = leitura.municipios(CONFIG_MUNICIPIOS, "sp")
        self.assertEqual(leitura.achar_municipio(lista, "campi")[0]["codigo"], "62910")

    def test_achar_ambiguo_devolve_candidatas(self):
        lista = leitura.municipios(CONFIG_MUNICIPIOS, "sp")
        cidade, parecidas = leitura.achar_municipio(lista, "joao")
        self.assertIsNone(cidade)
        self.assertEqual(len(parecidas), 2)

    def test_achar_nome_exato_vence_trecho(self):
        lista = [{"codigo": "1", "nome": "Itu"}, {"codigo": "2", "nome": "Ituiutaba"}]
        self.assertEqual(leitura.achar_municipio(lista, "itu")[0]["codigo"], "1")

    def test_achar_nada(self):
        lista = leitura.municipios(CONFIG_MUNICIPIOS, "sp")
        self.assertEqual(leitura.achar_municipio(lista, "xyz"), (None, []))
        self.assertEqual(leitura.achar_municipio(lista, ""), (None, []))


class Numeros(unittest.TestCase):
    def test_decimal_aceita_virgula_e_vazio(self):
        self.assertEqual(leitura.decimal("12,34"), 12.34)
        self.assertEqual((leitura.decimal(""), leitura.decimal(None)), (0.0, 0.0))

    def test_numero_br_usa_virgula(self):
        self.assertEqual((leitura.numero_br(12.3), leitura.numero_br(1.25, casas=1)), ("12,30", "1,2"))

    def test_milhar_usa_ponto(self):
        self.assertEqual((leitura.milhar("1234567"), leitura.milhar(None), leitura.milhar(999)), ("1.234.567", "0", "999"))
