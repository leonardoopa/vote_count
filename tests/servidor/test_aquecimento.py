"""Testes de `contador/servidor/aquecimento.py`."""
import unittest
from unittest import mock

from contador import varredor
from contador.servidor import aquecimento, estado
from contador.servidor.rotas import municipios


class Aquecimento(unittest.TestCase):
    def test_pede_o_mapa_do_pais_nos_dois_turnos_e_para_quando_tudo_chegou(self):
        pedidos, esperas = [], []

        def mapa(consulta):
            pedidos.append((consulta["cargo"][0], consulta["turno"][0], consulta["uf"][0], consulta["ambiente"][0]))
            rodada = len(pedidos)   # a cada pedido, mais cidades chegam; o turno 2 é o último a completar
            return 200, {"total": 10, "carregadas": 10 if rodada > 3 else 5}

        with mock.patch.object(estado, "VARREDOR", varredor.Varredor(2)), mock.patch.object(municipios, "mapa_municipal_do_brasil", mapa):
            pendentes = aquecimento.aquecer(dormir=esperas.append)
        self.assertEqual(pendentes, [])
        self.assertEqual({(c, t, uf, a) for c, t, uf, a in pedidos}, {("presidente", "1", "br", "oficial"), ("presidente", "2", "br", "oficial")})
        self.assertEqual(esperas, [aquecimento.ESPERA_S] * 2)   # esperou entre as rodadas até o último turno completar

    def test_erro_do_tse_nao_derruba_e_a_insistencia_tem_limite(self):
        esperas = []

        def mapa(consulta):
            raise RuntimeError("TSE fora do ar")

        with mock.patch.object(estado, "VARREDOR", varredor.Varredor(2)), mock.patch.object(municipios, "mapa_municipal_do_brasil", mapa):
            pendentes = aquecimento.aquecer(dormir=esperas.append)
        self.assertEqual(pendentes, list(aquecimento.TURNOS))
        self.assertEqual(len(esperas), aquecimento.MAX_RODADAS)

    def test_varredor_desligado_ou_aquecer_mapa_zero_nao_inicia_nada(self):
        with mock.patch.object(estado, "VARREDOR", varredor.Varredor(0)):
            self.assertIsNone(aquecimento.iniciar())
            self.assertEqual(aquecimento.aquecer(dormir=lambda s: None), list(aquecimento.TURNOS))
        with mock.patch.object(estado, "VARREDOR", varredor.Varredor(2)), mock.patch.dict("os.environ", {"AQUECER_MAPA": "0"}):
            self.assertIsNone(aquecimento.iniciar())
