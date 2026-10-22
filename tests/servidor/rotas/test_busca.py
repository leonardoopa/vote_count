"""Testes de `contador/servidor/rotas/busca.py`."""
import unittest
from unittest import mock

from contador.servidor import estado, rotas
from contador.servidor.rotas import busca
from contador.tse import catalogo
from tests.dados import CONFIG_MUNICIPIOS


CONFIG = {"abr": [
    {"cd": "sp", "mu": [
        {"cd": "71072", "nm": "SÃO PAULO", "c": "s"}, {"cd": "62910", "nm": "CAMPINAS", "c": "n"},
        {"cd": "70670", "nm": "SÃO JOÃO DA BOA VISTA", "c": "n"}, {"cd": "70001", "nm": "VARGEM GRANDE PAULISTA", "c": "n"},
    ]},
    {"cd": "rj", "mu": [{"cd": "60011", "nm": "RIO DE JANEIRO", "c": "s"}, {"cd": "60100", "nm": "SÃO PAULO DA SERRA", "c": "n"}]},
    {"cd": "df", "mu": [{"cd": "97012", "nm": "BRASÍLIA", "c": "s"}]},
    {"cd": "br", "mu": [{"cd": "00001", "nm": "NÃO É UF", "c": "n"}]},
]}


class BuscarCidades(unittest.TestCase):
    def nomes(self, termo, cargo="governador", **kw):
        return [f'{c["nome"]} {c["uf"]}' for c in busca.buscar_cidades(CONFIG, cargo, termo, **kw)]

    def test_ignora_acento_e_caixa(self):
        self.assertEqual(self.nomes("sao jo"), ["São João da Boa Vista sp"])
        self.assertEqual(self.nomes("BRASILIA"), ["Brasília df"])

    def test_quem_comeca_com_o_termo_vem_primeiro(self):
        config = {"abr": [{"cd": "sp", "mu": [
            {"cd": "1", "nm": "SAPAULOS", "c": "n"}, {"cd": "2", "nm": "SÃO PAULO", "c": "n"}, {"cd": "3", "nm": "PAULO AFONSO", "c": "n"},
        ]}]}
        achadas = busca.buscar_cidades(config, "governador", "paulo")
        self.assertEqual([c["nome"] for c in achadas], ["Paulo Afonso", "São Paulo", "Sapaulos"])  # começa, início de palavra, meio

    def test_capital_e_nome_curto_desempatam(self):
        self.assertEqual(self.nomes("paulo"), ["São Paulo sp", "São Paulo da Serra rj"])
        self.assertEqual(self.nomes("sao paulo"), ["São Paulo sp", "São Paulo da Serra rj"])

    def test_termo_curto_nao_busca(self):
        self.assertEqual(self.nomes("s"), [])
        self.assertEqual(self.nomes(" "), [])

    def test_limite(self):
        self.assertEqual(len(self.nomes("a", limite=3)), 0)  # 1 letra
        self.assertEqual(len(self.nomes("ri", limite=1)), 1)

    def test_so_cidades_de_ufs_validas_para_o_cargo(self):
        self.assertEqual(self.nomes("paulo", cargo="deputado-distrital"), [])
        self.assertEqual(self.nomes("brasilia", cargo="deputado-distrital"), ["Brasília df"])
        self.assertEqual(self.nomes("brasilia", cargo="deputado-estadual"), [])  # estadual não tem DF

    def test_abrangencia_que_nao_e_uf_fica_de_fora(self):
        self.assertEqual(self.nomes("uf"), [])

    def test_indice_e_reaproveitado_enquanto_o_arquivo_for_o_mesmo(self):
        primeiro = busca.indice_de_cidades(CONFIG)
        self.assertIs(busca.indice_de_cidades(CONFIG), primeiro)
        self.assertIsNot(busca.indice_de_cidades(CONFIG_MUNICIPIOS), primeiro)


class Rota(unittest.TestCase):
    def obter(self, config, status=200):
        return mock.patch.object(estado.CACHE, "obter", return_value=(config, status, 0))

    def test_devolve_cidades(self):
        with self.obter(CONFIG) as obter:
            status, corpo = rotas.busca_rapida({"q": ["campinas"], "cargo": ["governador"], "ambiente": ["simulado"]})
        self.assertEqual((status, [c["codigo"] for c in corpo["cidades"]]), (200, ["62910"]))
        self.assertEqual(obter.call_args.args[0], catalogo.url_municipios("simulado", "governador", 1))

    def test_sempre_usa_a_lista_do_primeiro_turno(self):
        with self.obter(CONFIG) as obter:
            rotas.busca_rapida({"q": ["campinas"], "turno": ["2"]})
        self.assertEqual(obter.call_args.args[0], catalogo.url_municipios("oficial", "presidente", 1))

    def test_termo_curto_nem_chega_ao_cache(self):
        with self.obter(CONFIG) as obter:
            self.assertEqual(rotas.busca_rapida({"q": ["c"]}), (200, {"cidades": []}))
            self.assertEqual(rotas.busca_rapida({}), (200, {"cidades": []}))
        obter.assert_not_called()

    def test_entradas_invalidas(self):
        for consulta in ({"q": ["campinas"], "cargo": ["x"]}, {"q": ["campinas"], "ambiente": ["../x"]},
                         {"q": ["a" * 41]}):
            with self.subTest(consulta=consulta), self.obter(CONFIG) as obter:
                self.assertEqual(rotas.busca_rapida(consulta)[0], 400)
                obter.assert_not_called()

    def test_tse_sem_a_lista(self):
        with self.obter(None, status=404):
            self.assertEqual(rotas.busca_rapida({"q": ["campinas"]})[0], 404)
        with self.obter(None, status=503):
            self.assertEqual(rotas.busca_rapida({"q": ["campinas"]})[0], 503)

    def test_rota_na_tabela(self):
        self.assertIs(rotas.ROTAS_API["/api/busca"], rotas.busca_rapida)
