"""Testes de `contador/recursos/historico_mapa.py`."""
import unittest

from contador.recursos import historico_mapa
from contador.recursos.historico_mapa import HistoricoDoMapa, foto_do_mapa

CHAVE = ("oficial", "presidente", 1)


def corpo(**ufs):
    """Resumo por UF mínimo: cada argumento é uf=(partido, margem, % das seções) ou uf=None (sem líder)."""
    saida = {}
    for uf, valor in ufs.items():
        if valor is None:
            saida[uf] = {"situacao": "zerado", "secoes": {"percentual": 0.0}}
        else:
            partido, margem, apurado = valor
            saida[uf] = {"situacao": "lider", "lider": {"partido": partido}, "margem": margem, "secoes": {"percentual": apurado}}
    return {"ufs": saida}


class Foto(unittest.TestCase):
    def test_traz_o_lider_a_margem_e_o_andamento_de_cada_uf(self):
        foto = foto_do_mapa(corpo(sp=("PT", 12.34, 55.55), rj=None), 1000.9)
        self.assertEqual(foto, {"t": 1000, "ufs": {"sp": ["PT", 12.3, 55.5], "rj": ["", 0.0, 0.0]}})

    def test_empate_e_sem_dados_vao_sem_partido(self):
        resumo = {"ufs": {"ac": {"situacao": "empate", "secoes": {"percentual": 40.0}}, "al": {"situacao": "sem_dados"}}}
        self.assertEqual(foto_do_mapa(resumo, 5)["ufs"], {"ac": ["", 0.0, 40.0], "al": ["", 0.0, 0.0]})


class Registro(unittest.TestCase):
    def test_so_guarda_quando_algo_mudou(self):
        h = HistoricoDoMapa()
        self.assertTrue(h.registrar(CHAVE, corpo(sp=("PT", 5.0, 10.0)), 100))
        self.assertFalse(h.registrar(CHAVE, corpo(sp=("PT", 5.0, 10.0)), 105))   # igual: só o horário passou
        self.assertTrue(h.registrar(CHAVE, corpo(sp=("PT", 5.0, 20.0)), 110))   # apurou mais
        self.assertTrue(h.registrar(CHAVE, corpo(sp=("PL", 1.0, 20.0)), 115))   # o líder virou
        self.assertEqual([f["t"] for f in h.consultar(CHAVE)["fotos"]], [100, 110, 115])

    def test_zerado_entra_como_origem_do_replay(self):
        h = HistoricoDoMapa()
        h.registrar(CHAVE, corpo(sp=None), 1)
        self.assertEqual(h.consultar(CHAVE)["fotos"][0]["ufs"], {"sp": ["", 0.0, 0.0]})

    def test_so_presidente_e_governador(self):
        h = HistoricoDoMapa()
        for cargo in ("senador", "deputado-federal", "x"):
            self.assertFalse(h.registrar(("oficial", cargo, 1), corpo(sp=("PT", 1.0, 1.0)), 1))
        self.assertEqual(h.consultar(("oficial", "senador", 1)), {"fotos": []})

    def test_resumo_fora_do_formato_nao_derruba(self):
        h = HistoricoDoMapa()
        for ruim in ({}, {"ufs": {"sp": {}}}, {"ufs": None}):
            self.assertFalse(h.registrar(CHAVE, ruim, 1))
        self.assertEqual(h.consultar(CHAVE), {"fotos": []})

    def test_selecoes_diferentes_sao_series_diferentes(self):
        h = HistoricoDoMapa()
        h.registrar(("oficial", "presidente", 1), corpo(sp=("PT", 1.0, 1.0)), 1)
        h.registrar(("oficial", "presidente", 2), corpo(sp=("PL", 1.0, 1.0)), 2)
        h.registrar(("simulado", "governador", 1), corpo(sp=("MDB", 1.0, 1.0)), 3)
        self.assertEqual([len(h.consultar(c)["fotos"]) for c in (("oficial", "presidente", 1), ("oficial", "presidente", 2), ("simulado", "governador", 1), ("oficial", "governador", 1))], [1, 1, 1, 0])


class Limites(unittest.TestCase):
    def test_fotos_por_serie(self):
        h = HistoricoDoMapa()
        for i in range(historico_mapa.MAX_FOTOS + 10):
            h.registrar(CHAVE, corpo(sp=("PT", 1.0, float(i % 100) + (i // 100) * 0.1)), i)
        serie = h._series[CHAVE]
        self.assertEqual(len(serie), historico_mapa.MAX_FOTOS)
        self.assertEqual(serie[0]["t"], 10)   # as mais antigas saíram

    def test_series_descarta_a_menos_usada_recentemente(self):
        h = HistoricoDoMapa()
        for turno in range(1, historico_mapa.MAX_SERIES + 1):
            h.registrar(("oficial", "presidente", turno), corpo(sp=("PT", 1.0, 1.0)), turno)
        h.consultar(("oficial", "presidente", 1))                                  # a mais antiga volta a ser usada
        h.registrar(("simulado", "presidente", 1), corpo(sp=("PT", 1.0, 1.0)), 99)   # uma a mais: sai a segunda
        self.assertIn(("oficial", "presidente", 1), h._series)
        self.assertNotIn(("oficial", "presidente", 2), h._series)

    def test_resposta_reduzida_a_cento_e_vinte_fotos_com_a_primeira_e_a_ultima(self):
        h = HistoricoDoMapa()
        for i in range(200):
            h.registrar(CHAVE, corpo(sp=("PT", 1.0, i * 0.5)), i)
        fotos = h.consultar(CHAVE)["fotos"]
        self.assertEqual(len(fotos), historico_mapa.MAX_FOTOS_API)
        self.assertEqual((fotos[0]["t"], fotos[-1]["t"]), (0, 199))

    def test_o_que_a_consulta_devolve_nao_mexe_na_serie(self):
        h = HistoricoDoMapa()
        h.registrar(CHAVE, corpo(sp=("PT", 1.0, 1.0)), 1)
        h.consultar(CHAVE)["fotos"][0]["ufs"]["sp"][0] = "MUDOU"
        self.assertEqual(h.consultar(CHAVE)["fotos"][0]["ufs"]["sp"][0], "MUDOU")   # as fotos são do chamador depois de devolvidas: o servidor só serializa


if __name__ == "__main__":
    unittest.main()
