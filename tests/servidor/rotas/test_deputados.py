"""Testes de `contador/servidor/rotas/deputados.py`."""
import threading
import unittest
from unittest import mock

from contador.demo import tse_falso
from contador.recursos import deputados
from contador.servidor import estado, respostas, rotas
from contador.tse import catalogo, cliente
from contador.varredor import Varredor


class Relogio:
    agora = 1000.0

    def __call__(self):
        return self.agora


class Rotas(unittest.TestCase):
    """Rotas de verdade com o varredor de verdade, mas sem thread e com o TSE falso no lugar da rede."""

    def setUp(self):
        self.pedidos = []

        def buscar(url, etag=None):
            self.pedidos.append(url)
            return tse_falso.buscar_falso(url, etag)

        patches = [
            mock.patch.object(estado, "VARREDOR", Varredor(100, buscar=buscar, relogio=Relogio(), dormir=lambda s: None)),
            mock.patch.object(threading.Thread, "start"),
            mock.patch.object(tse_falso, "progresso", return_value=(300, 1.0)),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def carregar(self, quantas=27):
        for _ in range(quantas):
            estado.VARREDOR.passo()

    def test_camara_comeca_vazia_e_enche_conforme_o_varredor_busca(self):
        status, corpo = rotas.camara_dos_deputados({"ambiente": ["simulado"]})
        self.assertEqual((status, corpo["ufs_com_dados"], corpo["eleitos"], corpo["idade_s"]), (200, 0, 0, None))
        self.carregar(5)
        corpo = rotas.camara_dos_deputados({"ambiente": ["simulado"]})[1]
        self.assertEqual(corpo["ufs_com_dados"], 5)
        self.carregar()
        corpo = rotas.camara_dos_deputados({"ambiente": ["simulado"]})[1]
        self.assertEqual((corpo["ufs_com_dados"], corpo["ufs_total"], corpo["eleitos"], corpo["total"], corpo["final"]), (27, 27, 513, 513, True))
        self.assertEqual(sum(p["cadeiras"] for p in corpo["partidos"]), 513)
        self.assertEqual(corpo["idade_s"], 0)
        self.assertEqual(corpo["ambiente"], "simulado")

    def test_so_pede_arquivos_de_deputado_federal_de_cada_uf(self):
        rotas.camara_dos_deputados({"ambiente": ["simulado"]})
        self.carregar()
        self.assertEqual(sorted(self.pedidos), sorted(catalogo.montar_url("simulado", "deputado-federal", uf, 1) for uf in catalogo.UFS))

    def test_mais_votados_estadual_usa_distrital_no_df(self):
        rotas.mais_votados({"cargo": ["deputado-estadual"], "ambiente": ["simulado"]})
        self.carregar()
        esperados = {catalogo.montar_url("simulado", "deputado-distrital" if uf == "df" else "deputado-estadual", uf, 1) for uf in catalogo.UFS}
        self.assertEqual(set(self.pedidos), esperados)
        status, corpo = rotas.mais_votados({"cargo": ["deputado-distrital"], "ambiente": ["simulado"]})
        self.assertEqual((status, corpo["cargo"], len(corpo["candidatos"])), (200, "deputado-distrital", deputados.TOP_DO_PAIS))
        self.assertEqual([c["posicao"] for c in corpo["candidatos"]], list(range(1, 21)))
        self.assertGreaterEqual(corpo["candidatos"][0]["votos"], corpo["candidatos"][-1]["votos"])

    def test_federal_e_estadual_sao_grupos_diferentes(self):
        rotas.mais_votados({"cargo": ["deputado-federal"], "ambiente": ["simulado"]})
        rotas.mais_votados({"cargo": ["deputado-estadual"], "ambiente": ["simulado"]})
        self.assertEqual(len(estado.VARREDOR._grupos), 2)

    def test_entradas_invalidas(self):
        for rota, consulta in ((rotas.camara_dos_deputados, {"ambiente": ["http://x"]}),
                               (rotas.mais_votados, {"ambiente": ["../x"]}), (rotas.mais_votados, {"cargo": ["presidente"]}),
                               (rotas.mais_votados, {"cargo": ["senador"]})):
            with self.subTest(rota=rota.__name__, consulta=consulta):
                self.assertEqual(rota(consulta)[0], 400)
        self.assertEqual(estado.VARREDOR._grupos, {})  # nada foi pedido ao varredor

    def test_varredor_desligado_da_503(self):
        with mock.patch.object(estado, "VARREDOR", Varredor(0)):
            self.assertEqual(rotas.camara_dos_deputados({"ambiente": ["simulado"]}), respostas.RECURSO_DESLIGADO)
            self.assertEqual(rotas.mais_votados({})[0], 503)

    def test_a_rota_nunca_consulta_o_tse_sozinha(self):
        recusa = AssertionError("só o varredor busca")
        with mock.patch.object(cliente, "buscar", side_effect=recusa), mock.patch.object(estado.CACHE, "obter", side_effect=recusa):
            self.assertEqual(rotas.camara_dos_deputados({"ambiente": ["simulado"]})[0], 200)

    def test_rotas_na_tabela(self):
        self.assertIs(rotas.ROTAS_API["/api/camara"], rotas.camara_dos_deputados)
        self.assertIs(rotas.ROTAS_API["/api/maisvotados"], rotas.mais_votados)
        self.assertIs(rotas.ROTAS_API["/api/senado"], rotas.senado_em_disputa)


class Configuracao(unittest.TestCase):
    def test_limite_padrao_e_pequeno(self):
        self.assertLessEqual(estado.BUSCAS_EXTRAS_POR_SEGUNDO, 2)
        self.assertGreater(estado.BUSCAS_EXTRAS_POR_SEGUNDO, 0)
