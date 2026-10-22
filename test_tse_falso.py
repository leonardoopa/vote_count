import unittest
from unittest import mock

import contador
import servidor
import tse_falso


def pedir(cargo, uf, turno, p, ambiente="simulado", municipio=None, etag=None):
    url = contador.montar_url(ambiente, cargo, uf, turno, municipio=municipio)
    with mock.patch.object(tse_falso, "progresso", return_value=(int(p * 30), p)):
        return tse_falso.buscar_falso(url, etag)


class TseFalso(unittest.TestCase):
    def test_presidente_cabe_no_resumo_do_servidor(self):
        resposta = pedir("presidente", "br", 1, 0.5)
        self.assertEqual(resposta.status, 200)
        resumo = servidor.resumir(resposta.dados, 10)
        self.assertEqual(resumo["secoes"]["percentual"], 50.0)
        self.assertEqual(resumo["total_candidatos"], 6)
        self.assertAlmostEqual(sum(c["percentual"] for c in resumo["candidatos"]), 100, delta=0.2)

    def test_oficial_nunca_responde(self):
        self.assertEqual(pedir("presidente", "br", 1, 0.5, ambiente="oficial").status, 404)

    def test_comeca_zerado(self):
        dados = pedir("presidente", "br", 1, 0).dados
        self.assertEqual(servidor.resumir(dados, 10)["votos"]["total"], 0)
        self.assertEqual(dados["dt"], "")
        self.assertTrue(all(c["st"] == "" for c in contador.candidatos(dados)))

    def test_no_fim_marca_segundo_turno_e_eleito(self):
        primeiro = pedir("presidente", "br", 1, 1).dados
        self.assertEqual(primeiro["tf"], "s")
        self.assertEqual(sorted(c["st"] for c in contador.candidatos(primeiro))[:2], ["2º turno", "2º turno"])
        segundo = pedir("presidente", "br", 2, 1).dados
        self.assertEqual([c["st"] for c in contador.candidatos(segundo)], ["Eleito", "Não eleito"])

    def votos_de(self, dados, numero):
        return next(int(c["vap"]) for c in contador.candidatos(dados) if c["n"] == numero)

    def test_brasil_e_a_soma_das_ufs_e_do_exterior(self):
        total = sum(self.votos_de(pedir("presidente", uf, 1, 0.4).dados, "13") for uf in (*contador.UFS, "zz"))
        self.assertEqual(self.votos_de(pedir("presidente", "br", 1, 0.4).dados, "13"), total)

    def test_exterior_so_para_presidente(self):
        self.assertEqual(pedir("presidente", "zz", 1, 0.5).status, 200)
        for cargo in ("governador", "senador"):
            with self.subTest(cargo=cargo):
                self.assertEqual(pedir(cargo, "zz", 1, 0.5).status, 404)

    def test_governador_so_tem_segundo_turno_onde_ninguem_passou_de_50(self):
        com, sem = [], []
        for uf in contador.UFS:
            primeiro = contador.candidatos(pedir("governador", uf, 1, 1).dados)
            segundo = pedir("governador", uf, 2, 1)
            if segundo.status == 200:
                com.append(uf)
                self.assertEqual(len(contador.candidatos(segundo.dados)), 2)
                self.assertEqual(primeiro[0]["st"], "2º turno")
            else:
                sem.append(uf)
                self.assertEqual(segundo.status, 404)
                self.assertEqual(primeiro[0]["st"], "Eleito")
        self.assertTrue(com and sem)

    def test_mesma_marca_devolve_304(self):
        marca = pedir("presidente", "br", 1, 0.5).etag
        self.assertEqual(pedir("presidente", "br", 1, 0.5, etag=marca).status, 304)

    def test_cidades(self):
        config = tse_falso.lista_de_cidades()
        sp = contador.municipios(config, "sp")
        self.assertEqual(len(sp), len(tse_falso.CIDADES))
        self.assertEqual(pedir("governador", "sp", 1, 0.5, municipio=sp[0]["codigo"]).status, 200)
        self.assertEqual(pedir("governador", "sp", 1, 0.5, municipio="99999").status, 404)

    def test_cargo_sem_suporte_da_404(self):
        self.assertEqual(pedir("deputado-federal", "sp", 1, 0.5).status, 404)


if __name__ == "__main__":
    unittest.main()
