"""Testes de `contador/recursos/municipios.py`."""
import unittest

from contador.recursos import municipios
from contador.tse import leitura
from tests.dados import DOIS, arquivo


CONFIG = {"abr": [
    {"cd": "sp", "mu": [{"cd": "71072", "cdi": "3550308", "nm": "SÃO PAULO", "c": "s"}, {"cd": "62910", "cdi": "3509502", "nm": "CAMPINAS", "c": "n"},
                        {"cd": "11111", "nm": "SEM CODIGO IBGE", "c": "n"}]},
    {"cd": "df", "mu": [{"cd": "97012", "cdi": "5300108", "nm": "BRASÍLIA", "c": "s"}]},
]}


class ResumirCidade(unittest.TestCase):
    def test_lider_compacto(self):
        resumo = municipios.resumir_cidade(arquivo(DOIS, secoes=(100, 80)))
        self.assertEqual(resumo, {
            "situacao": "lider", "apurado": 80.0, "final": False, "margem": 20.0, "margem_votos": 200,
            "lider": {"nome": "ANA", "partido": "PT", "percentual": 60.0, "eleito": False, "segundo_turno": False},
        })

    def test_zerado_e_empate(self):
        zerado = municipios.resumir_cidade(arquivo([("13", "Ana", "PT", 0, "0,00", ""), ("22", "Bia", "PL", 0, "0,00", "")]))
        self.assertEqual(zerado, {"situacao": "zerado", "apurado": 50.0, "final": False})
        empate = municipios.resumir_cidade(arquivo([("13", "Ana", "PT", 500, "50,00", ""), ("22", "Bia", "PL", 500, "50,00", "")]))
        self.assertEqual((empate["situacao"], [c["partido"] for c in empate["empatados"]]), ("empate", ["PT", "PL"]))
        self.assertNotIn("lider", empate)

    def test_eleito_e_final_vem_do_arquivo(self):
        dados = arquivo([("13", "Ana", "PT", 600, "60,00", "Eleito"), ("22", "Bia", "PL", 400, "40,00", "")], final=True)
        resumo = municipios.resumir_cidade(dados)
        self.assertTrue(resumo["final"] and resumo["lider"]["eleito"])

    def test_arquivo_fora_do_formato_levanta_para_o_varredor_tratar(self):
        with self.assertRaises((KeyError, TypeError, IndexError)):
            municipios.resumir_cidade({})

    def test_intervalo(self):
        self.assertEqual(municipios.intervalo(None), municipios.INTERVALO_APURANDO_S)
        self.assertEqual(municipios.intervalo({"final": True}), municipios.INTERVALO_FINAL_S)


class Montar(unittest.TestCase):
    def test_ibge_das_cidades(self):
        self.assertEqual(municipios.ibge_das_cidades(CONFIG, "sp"), {"71072": "3550308", "62910": "3509502"})  # sem código IBGE, sem desenho
        self.assertEqual(municipios.ibge_das_cidades(CONFIG, "xx"), {})
        self.assertEqual(municipios.ibge_das_cidades({}, "sp"), {})

    def test_so_traz_o_que_ja_foi_buscado_e_tem_desenho(self):
        cidades = leitura.municipios(CONFIG, "sp")
        ibge = municipios.ibge_das_cidades(CONFIG, "sp")
        fotos = {"71072": ({"situacao": "zerado", "apurado": 0.0, "final": False}, 990.0, 200), "62910": (None, 0.0, 0),
                 "11111": ({"situacao": "zerado", "apurado": 0.0, "final": False}, 980.0, 200)}
        corpo = municipios.montar("sp", cidades, ibge, fotos, 1000.0)
        self.assertEqual(list(corpo["cidades"]), ["3550308"])
        self.assertEqual(corpo["cidades"]["3550308"]["nome"], "São Paulo")
        self.assertEqual(corpo["cidades"]["3550308"]["codigo"], "71072")
        self.assertEqual((corpo["uf"], corpo["total"], corpo["carregadas"], corpo["idade_s"]), ("sp", 3, 2, 20))

    def test_sem_nada_buscado(self):
        corpo = municipios.montar("sp", leitura.municipios(CONFIG, "sp"), {}, {}, 1000.0)
        self.assertEqual((corpo["cidades"], corpo["carregadas"], corpo["idade_s"]), ({}, 0, None))


class Foco(unittest.TestCase):
    IBGE = {"71072": "3550308", "71111": "3500105", "71120": "3500204"}

    def test_codigos_do_tse_na_ordem_pedida(self):
        self.assertEqual(municipios.codigos_em_foco("3500204, 3550308,3550308,lixo,9999999,", self.IBGE), ["71120", "71072"])

    def test_vazio_e_sem_cidade_conhecida(self):
        self.assertEqual(municipios.codigos_em_foco("", self.IBGE), [])
        self.assertEqual(municipios.codigos_em_foco("1234567", {}), [])

    def test_no_maximo_max_foco(self):
        ibge = {str(i): str(1000000 + i) for i in range(200)}
        pedido = ",".join(ibge.values())
        self.assertEqual(len(municipios.codigos_em_foco(pedido, ibge)), municipios.MAX_FOCO)
