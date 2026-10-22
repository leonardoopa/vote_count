import json
import unittest
from pathlib import Path
from unittest import mock

import contador
import deputados
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
        self.assertEqual(len(sp), len(tse_falso.cidades_da_uf("sp")))
        self.assertEqual(pedir("governador", "sp", 1, 0.5, municipio=sp[0]["codigo"]).status, 200)
        self.assertEqual(pedir("governador", "sp", 1, 0.5, municipio="99999").status, 404)

    def test_deputados_so_no_primeiro_turno_e_nas_ufs_do_cargo(self):
        self.assertEqual(pedir("deputado-federal", "sp", 1, 0.5).status, 200)
        self.assertEqual(pedir("deputado-estadual", "sp", 1, 0.5).status, 200)
        self.assertEqual(pedir("deputado-distrital", "df", 1, 0.5).status, 200)
        for cargo, uf, turno in (("deputado-federal", "sp", 2), ("deputado-federal", "br", 1), ("deputado-federal", "zz", 1),
                                 ("deputado-estadual", "df", 1), ("deputado-distrital", "sp", 1)):
            with self.subTest(cargo=cargo, uf=uf, turno=turno):
                self.assertEqual(pedir(cargo, uf, turno, 0.5).status, 404)
        self.assertEqual(pedir("deputado-federal", "sp", 1, 0.5, municipio="10000").status, 404)

    def test_deputados_tem_federacoes_vagas_e_eleitos_so_depois_da_metade(self):
        antes = deputados.resumir_arquivo(pedir("deputado-federal", "ac", 1, 0.4).dados, "ac")
        depois = deputados.resumir_arquivo(pedir("deputado-federal", "ac", 1, 1.0).dados, "ac")
        self.assertEqual(antes["eleitos"], 0)
        self.assertEqual((depois["eleitos"], depois["vagas"]), (tse_falso.VAGAS_FEDERAL["ac"], tse_falso.VAGAS_FEDERAL["ac"]))
        self.assertTrue(depois["final"] and not antes["final"])
        self.assertEqual({b["nome"] for b in depois["blocos"] if b["federacao"]}, {"PT/PC do B/PV", "UNIÃO/PP", "PSOL/REDE", "PSDB/CIDADANIA"})
        self.assertEqual(sum(b["cadeiras"] for b in depois["blocos"]), depois["eleitos"])

    def test_cadeiras_da_camara_somam_513(self):
        self.assertEqual(sum(tse_falso.VAGAS_FEDERAL.values()), 513)
        self.assertTrue(all(v >= 8 for v in tse_falso.VAGAS_FEDERAL.values()))
        resumos = {uf: deputados.resumir_arquivo(pedir("deputado-federal", uf, 1, 1.0).dados, uf) for uf in contador.UFS}
        self.assertEqual(deputados.camara(resumos)["eleitos"], 513)

    def test_deputado_cabe_no_resumo_do_servidor(self):
        resumo = servidor.resumir(pedir("deputado-federal", "sp", 1, 1.0).dados, 5)
        self.assertEqual(resumo["secoes"]["percentual"], 100.0)
        self.assertTrue(resumo["candidatos"][0]["eleito"])

    def test_uma_cidade_por_municipio_do_desenho_com_codigo_ibge(self):
        geo = json.loads(Path("geo/sp.json").read_text(encoding="utf-8"))["m"]
        cidades = tse_falso.cidades_da_uf("sp")
        self.assertEqual(sorted(ibge for _, ibge, _ in cidades), sorted(geo))
        self.assertEqual(len({tse for tse, _, _ in cidades}), len(cidades))      # códigos do TSE não se repetem
        todos = [tse for uf in contador.UFS for tse, _, _ in tse_falso.cidades_da_uf(uf)]
        self.assertEqual(len(todos), len(set(todos)))                            # nem entre UFs
        self.assertTrue(all(len(c) == 5 for c in todos))
        mu = tse_falso.lista_de_cidades()["abr"][contador.UFS.index("sp")]["mu"]
        self.assertEqual(mu[0]["cdi"], cidades[0][1])

    def test_cargo_sem_suporte_da_404(self):
        self.assertEqual(pedir("deputado-federal", "sp", 1, 0.5, ambiente="oficial").status, 404)


if __name__ == "__main__":
    unittest.main()
