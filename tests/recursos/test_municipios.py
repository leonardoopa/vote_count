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
            "lider": {"numero": "13", "nome": "ANA", "partido": "PT", "percentual": 60.0, "votos": 600, "eleito": False, "segundo_turno": False},
            "segundo": {"numero": "22", "nome": "BIA", "partido": "PL", "percentual": 40.0, "votos": 400},
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


class DoBrasil(unittest.TestCase):
    def test_resumo_compacto_traz_o_sqcand_para_a_foto(self):
        dados = arquivo(DOIS, secoes=(100, 80))
        dados["carg"][0]["agr"][0]["par"][0]["cand"][0]["sqcand"] = "111"
        resumo = municipios.resumir_cidade_do_brasil(dados)
        self.assertEqual(resumo["lider"], {"numero": "13", "nome": "ANA", "partido": "PT", "percentual": 60.0, "sqcand": "111"})
        self.assertEqual((resumo["segundo"]["numero"], resumo["segundo"]["sqcand"], resumo["margem_votos"]), ("22", None, 200))

    def test_ordem_espalhada_pega_uma_cidade_de_cada_estado_por_vez(self):
        self.assertEqual(municipios.ordem_espalhada({"ac": ["a1", "a2", "a3"], "al": ["b1"], "am": ["c1", "c2"]}), ["a1", "b1", "c1", "a2", "c2", "a3"])
        self.assertEqual(municipios.ordem_espalhada({}), [])

    def test_montar_brasil_em_listas_curtas(self):
        def cidade(partido, pct, numero, margem=100, situacao="lider"):
            resumo = {"situacao": situacao, "apurado": 90.0, "final": False}
            if situacao == "lider":
                resumo.update(lider={"numero": numero, "nome": partido, "partido": partido, "percentual": pct, "sqcand": "1"},
                              segundo={"numero": "99", "nome": "OUTRO", "partido": "XX", "percentual": 100 - pct, "sqcand": None}, margem_votos=margem)
            return (resumo, 1000.0, 200)
        resumos = {"2611606": cidade("PT", 55.0, "13"), "3550308": cidade("PL", 51.0, "22"), "2304400": cidade("PT", 70.0, "13", situacao="zerado"), "1100015": (None, 0, 0)}
        corpo = municipios.montar_brasil("presidente", resumos, 4, lambda uf, sq: f"foto/{uf}/{sq}", 1010.0)
        self.assertEqual((corpo["total"], corpo["carregadas"], corpo["idade_s"]), (4, 3, 10))
        self.assertEqual(set(corpo["cidades"]), {"2611606", "3550308"})     # cidade zerada não pinta
        self.assertEqual(corpo["cidades"]["2611606"], [0, 55.0, 1, 45.0, 90.0, 100, 0])
        self.assertEqual(corpo["candidatos"][0], {"numero": "13", "nome": "PT", "partido": "PT", "foto": "foto/pe/1"})
        # presidente: o mesmo candidato é um só no país; governador: um por UF
        mesmos = municipios.montar_brasil("presidente", {"2611606": cidade("PT", 55.0, "13"), "3550308": cidade("PT", 60.0, "13")}, 2, lambda uf, sq: None, 0)
        self.assertEqual(len(mesmos["candidatos"]), 2)   # PT e o "outro"
        por_uf = municipios.montar_brasil("governador", {"2611606": cidade("PT", 55.0, "13"), "3550308": cidade("PT", 60.0, "13")}, 2, lambda uf, sq: None, 0)
        self.assertEqual(len(por_uf["candidatos"]), 4)

