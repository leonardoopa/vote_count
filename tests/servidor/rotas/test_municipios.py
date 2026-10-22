"""Testes de `contador/servidor/rotas/municipios.py`."""
import threading
import unittest
from unittest import mock

from contador.demo import tse_falso
from contador.servidor import estado, respostas, rotas
from contador.tse import catalogo, cliente
from contador.tse.cache import Cache
from contador.varredor import Varredor


class Relogio:
    agora = 1000.0

    def __call__(self):
        return self.agora


class Rota(unittest.TestCase):
    """A rota de verdade com varredor e cache de verdade, sem thread e com o TSE falso no lugar da rede."""

    def setUp(self):
        self.pedidos = []

        def buscar(url, etag=None):
            self.pedidos.append(url)
            return tse_falso.buscar_falso(url, etag)

        patches = [
            mock.patch.object(estado, "VARREDOR", Varredor(100, buscar=buscar, relogio=Relogio(), dormir=lambda s: None)),
            mock.patch.object(estado, "CACHE", Cache()),
            mock.patch.object(cliente, "buscar", side_effect=buscar),
            mock.patch.object(threading.Thread, "start"),
            mock.patch.object(tse_falso, "progresso", return_value=(150, 0.5)),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.consulta = {"ambiente": ["simulado"], "cargo": ["governador"], "uf": ["ac"]}

    def test_comeca_vazio_e_enche_conforme_o_varredor_busca(self):
        status, corpo = rotas.mapa_municipal(self.consulta)
        total = len(tse_falso.cidades_da_uf("ac"))
        self.assertEqual((status, corpo["total"], corpo["carregadas"], corpo["cidades"]), (200, total, 0, {}))
        for _ in range(4):
            estado.VARREDOR.passo()
        corpo = rotas.mapa_municipal(self.consulta)[1]
        self.assertEqual(corpo["carregadas"], 4)
        ibge = {ibge for _, ibge, _ in tse_falso.cidades_da_uf("ac")}
        self.assertTrue(set(corpo["cidades"]) <= ibge and len(corpo["cidades"]) == 4)
        primeira = next(iter(corpo["cidades"].values()))
        self.assertEqual(primeira["situacao"], "lider")
        self.assertEqual((corpo["cargo"], corpo["turno"], corpo["ambiente"], corpo["uf"]), ("governador", 1, "simulado", "ac"))

    def test_o_varredor_so_pede_arquivos_de_cidade_da_uf(self):
        rotas.mapa_municipal(self.consulta)
        antes = len(self.pedidos)
        while estado.VARREDOR.passo():
            pass
        cidades = {catalogo.montar_url("simulado", "governador", "ac", 1, municipio=tse) for tse, _, _ in tse_falso.cidades_da_uf("ac")}
        self.assertEqual(set(self.pedidos[antes:]), cidades)

    def test_cidades_so_depois_do_arquivo_da_uf_existir(self):
        # governador no 2º turno numa UF decidida no 1º: o TSE não tem arquivo, então nenhuma cidade é varrida
        uf = next(uf for uf in catalogo.UFS if tse_falso.base_do_turno("governador", uf, 2) is None)
        status, corpo = rotas.mapa_municipal({"ambiente": ["simulado"], "cargo": ["governador"], "uf": [uf], "turno": ["2"]})
        self.assertEqual(status, 404)
        self.assertEqual(estado.VARREDOR._grupos, {})

    def test_so_presidente_e_governador_dentro_de_um_estado(self):
        for consulta in ({"cargo": ["senador"], "uf": ["sp"]}, {"cargo": ["presidente"], "uf": ["br"]}, {"cargo": ["x"]},
                         {"cargo": ["governador"], "uf": ["sp"], "ambiente": ["../x"]}, {"cargo": ["governador"], "uf": ["sp"], "turno": ["7"]}):
            with self.subTest(consulta=consulta):
                self.assertEqual(rotas.mapa_municipal(consulta)[0], 400)
        self.assertEqual(self.pedidos, [])

    def test_presidente_em_uma_uf_funciona(self):
        status, corpo = rotas.mapa_municipal({"ambiente": ["simulado"], "cargo": ["presidente"], "uf": ["ac"]})
        self.assertEqual((status, corpo["cargo"]), (200, "presidente"))

    def test_o_foco_da_pagina_fura_a_fila_do_varredor(self):
        rotas.mapa_municipal(self.consulta)                       # cria o grupo, sem nada em foco
        vistas = tse_falso.cidades_da_uf("ac")[-3:]                  # as últimas da lista: a página as está vendo
        foco = ",".join(ibge for _, ibge, _ in reversed(vistas))
        self.assertEqual(rotas.mapa_municipal({**self.consulta, "foco": [foco]})[0], 200)
        antes = len(self.pedidos)
        for _ in range(3):
            estado.VARREDOR.passo()
        esperados = [catalogo.montar_url("simulado", "governador", "ac", 1, municipio=tse) for tse, _, _ in reversed(vistas)]
        self.assertEqual(self.pedidos[antes:], esperados)

    def test_foco_com_lixo_nao_derruba_a_rota(self):
        for foco in ("", ",,,", "x,9999999,\U0001f4a5", "1" * 5000, ",".join(["3000000"] * 500)):
            with self.subTest(foco=foco[:20]):
                self.assertEqual(rotas.mapa_municipal({**self.consulta, "foco": [foco]})[0], 200)

    def test_varredor_desligado_da_503(self):
        with mock.patch.object(estado, "VARREDOR", Varredor(0)):
            self.assertEqual(rotas.mapa_municipal(self.consulta), respostas.RECURSO_DESLIGADO)

    def test_tse_sem_a_lista_de_cidades(self):
        with mock.patch.object(estado, "CACHE", Cache()), mock.patch.object(cliente, "buscar", return_value=cliente.Resposta(404, None, None)):
            self.assertEqual(rotas.mapa_municipal(self.consulta)[0], 404)

    def test_rota_na_tabela(self):
        self.assertIs(rotas.ROTAS_API["/api/mapa-municipal"], rotas.mapa_municipal)
