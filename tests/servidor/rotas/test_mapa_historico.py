"""Testes de `/api/mapa-historico` (contador/servidor/rotas/mapa.py) e do registro feito pela rodada do mapa."""
import unittest
from unittest import mock

from contador.recursos.historico_mapa import HistoricoDoMapa
from contador.servidor import estado, respostas, rotas
from contador.tse import catalogo
from tests.dados import AGORA, DOIS, arquivo, url


class RotaMapaHistorico(unittest.TestCase):
    def setUp(self):
        respostas._PRONTAS.clear()
        self.addCleanup(respostas._PRONTAS.clear)
        patch = mock.patch.object(estado, "HISTORICO_DO_MAPA", HistoricoDoMapa())
        patch.start()
        self.addCleanup(patch.stop)

    def obter(self, cargo="presidente", extras=("br", "zz")):
        dados = {url(cargo, uf): (arquivo(DOIS), 200, AGORA) for uf in (*catalogo.UFS, *extras)}
        return mock.patch.object(estado.CACHE, "obter", side_effect=lambda u, ttl=None: dados.get(u, (None, 404, 0)))

    def test_a_rodada_do_mapa_guarda_a_foto_e_a_rota_devolve(self):
        consulta = {"cargo": ["presidente"], "turno": ["1"], "ambiente": ["oficial"]}
        with self.obter():
            self.assertEqual(rotas.mapa_por_uf(consulta)[0], 200)
        status, corpo = rotas.mapa_historico(consulta)
        self.assertEqual(status, 200)
        self.assertEqual(len(corpo["fotos"]), 1)
        self.assertEqual(set(corpo["fotos"][0]["ufs"]), set(catalogo.UFS))
        self.assertEqual(corpo["fotos"][0]["ufs"]["sp"][0], "PT")

    def test_rodada_igual_nao_cria_foto_nova(self):
        with self.obter():
            rotas.mapa_por_uf({})
            respostas._PRONTAS.clear()   # força uma segunda rodada de consultas
            rotas.mapa_por_uf({})
        self.assertEqual(len(rotas.mapa_historico({})[1]["fotos"]), 1)

    def test_rodada_que_falhou_nao_vira_foto(self):
        with mock.patch.object(estado.CACHE, "obter", return_value=(None, 404, 0)):
            self.assertEqual(rotas.mapa_por_uf({})[0], 404)
        self.assertEqual(rotas.mapa_historico({}), (200, {"fotos": []}))

    def test_senador_nao_tem_foto_do_mapa(self):
        with self.obter("senador", extras=()):
            rotas.senado_em_disputa({})
        self.assertEqual(estado.HISTORICO_DO_MAPA.consultar(("oficial", "senador", 1)), {"fotos": []})

    def test_entradas_invalidas(self):
        for consulta in ({"cargo": ["senador"]}, {"cargo": ["x"]}, {"turno": ["3"]}, {"ambiente": ["https://exemplo.com"]}):
            with self.subTest(consulta=consulta):
                self.assertEqual(rotas.mapa_historico(consulta)[0], 400)

    def test_a_rota_nunca_toca_o_tse(self):
        recusa = AssertionError("o histórico do mapa não pode consultar o TSE")
        with mock.patch.object(estado.CACHE, "obter", side_effect=recusa):
            self.assertEqual(rotas.mapa_historico({"cargo": ["governador"]}), (200, {"fotos": []}))

    def test_rota_na_tabela(self):
        self.assertIs(rotas.ROTAS_API["/api/mapa-historico"], rotas.mapa_historico)


if __name__ == "__main__":
    unittest.main()
