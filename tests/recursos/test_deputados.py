"""Testes de `contador/recursos/deputados.py`."""
import unittest

from contador.recursos import deputados


def cand(numero, nome, votos, situacao=""):
    return {"n": numero, "nm": nome.upper(), "nmu": nome.upper(), "vap": str(votos), "pvap": "0,00", "st": situacao}


def arquivo(agrupamentos, vagas=3, final=False, secoes=(100, 50)):
    """Arquivo de deputados no formato do TSE. agrupamentos: [(tipo, composição, [(sigla, [candidatos])])]."""
    return {
        "tf": "s" if final else "n",
        "s": {"ts": str(secoes[0]), "st": str(secoes[1]), "pst": "50,00"},
        "carg": [{"nv": str(vagas), "agr": [
            {"tp": tipo, "com": composicao, "par": [{"sg": sigla, "cand": candidatos} for sigla, candidatos in partidos]}
            for tipo, composicao, partidos in agrupamentos
        ]}],
    }


SP = arquivo([
    ("f", "PP / UNIÃO", [("PP", [cand("1111", "Ana", 9000, "Eleito por QP"), cand("1112", "Bia", 100, "Suplente")]),
                         ("UNIÃO", [cand("4411", "Caio", 7000, "Eleito por média")])]),
    ("i", "PL", [("PL", [cand("2211", "Dani", 12000, "Eleito por QP"), cand("2212", "Edu", 12000, "Não eleito")])]),
], vagas=3, secoes=(1000, 500))


def resumo_de(partidos, blocos, vagas=None, final=False, topo=()):
    return {"uf": "xx", "vagas": vagas or sum(partidos.values()), "eleitos": sum(partidos.values()), "partidos": partidos,
            "blocos": blocos, "mais_votados": list(topo), "secoes": {"total": 1, "apuradas": 1}, "final": final}


class ResumirArquivo(unittest.TestCase):
    def test_cadeiras_por_partido_e_por_bloco(self):
        resumo = deputados.resumir_arquivo(SP, "sp")
        self.assertEqual((resumo["uf"], resumo["vagas"], resumo["eleitos"]), ("sp", 3, 3))
        self.assertEqual(resumo["partidos"], {"PP": 1, "UNIÃO": 1, "PL": 1})
        self.assertEqual(resumo["blocos"], [
            {"nome": "PP / UNIÃO", "federacao": True, "partidos": ["PP", "UNIÃO"], "cadeiras": 2},
            {"nome": "PL", "federacao": False, "partidos": ["PL"], "cadeiras": 1},
        ])
        self.assertEqual(resumo["secoes"], {"total": 1000, "apuradas": 500})
        self.assertFalse(resumo["final"])

    def test_mais_votados_do_maior_para_o_menor_com_empate_pelo_numero(self):
        topo = deputados.resumir_arquivo(SP, "sp")["mais_votados"]
        self.assertEqual([c["nome"] for c in topo], ["EDU", "DANI", "ANA", "CAIO", "BIA"])  # 12000 empatado: número maior primeiro
        self.assertEqual(topo[1], {"nome": "DANI", "partido": "PL", "numero": "2211", "votos": 12000, "eleito": True, "uf": "sp"})

    def test_so_marca_eleito_quem_o_tse_marca(self):
        for texto, esperado in (("Eleito por QP", True), ("Eleito por média", True), ("Eleito", True), ("Suplente", False),
                                ("Não eleito", False), ("", False), (None, False)):
            with self.subTest(texto=texto):
                self.assertEqual(deputados.eleito({"st": texto}), esperado)

    def test_guarda_so_os_mais_votados_de_cada_uf(self):
        grande = arquivo([("i", "PL", [("PL", [cand(str(i), f"c{i}", i) for i in range(1, 51)])])])
        topo = deputados.resumir_arquivo(grande, "sp")["mais_votados"]
        self.assertEqual((len(topo), topo[0]["votos"], topo[-1]["votos"]), (deputados.TOP_POR_UF, 50, 31))

    def test_antes_da_apuracao_ninguem_foi_eleito(self):
        zerado = arquivo([("i", "PL", [("PL", [cand("1", "a", 0)])])])
        resumo = deputados.resumir_arquivo(zerado, "ac")
        self.assertEqual((resumo["eleitos"], resumo["partidos"]), (0, {}))

    def test_arquivo_fora_do_formato_levanta_para_o_varredor_tratar(self):
        for ruim in ({}, {"carg": []}, {"carg": [{"agr": [{}]}], "s": {}}):
            with self.subTest(ruim=ruim), self.assertRaises((KeyError, IndexError, TypeError)):
                deputados.resumir_arquivo(ruim, "sp")

    def test_final(self):
        self.assertTrue(deputados.resumir_arquivo(arquivo([("i", "PL", [("PL", [cand("1", "a", 1)])])], final=True), "sp")["final"])

    def test_intervalo(self):
        self.assertEqual(deputados.intervalo(None), deputados.INTERVALO_APURANDO_S)
        self.assertEqual(deputados.intervalo({"final": False}), deputados.INTERVALO_APURANDO_S)
        self.assertEqual(deputados.intervalo({"final": True}), deputados.INTERVALO_FINAL_S)


class Camara(unittest.TestCase):
    def test_soma_as_ufs_e_junta_os_blocos_pelo_nome(self):
        uniao = {"nome": "UNIÃO/PP", "federacao": True, "partidos": ["UNIÃO", "PP"]}
        a = resumo_de({"PP": 2, "PL": 3}, [{**uniao, "cadeiras": 2}, {"nome": "PL", "federacao": False, "partidos": ["PL"], "cadeiras": 3}])
        b = resumo_de({"UNIÃO": 1, "PL": 1}, [{**uniao, "cadeiras": 1}, {"nome": "PL", "federacao": False, "partidos": ["PL"], "cadeiras": 1}])
        corpo = deputados.camara({"sp": a, "rj": b, "ac": None})
        self.assertEqual([(p["partido"], p["cadeiras"], p["bloco"]) for p in corpo["partidos"]],
                         [("PL", 4, "PL"), ("PP", 2, "UNIÃO/PP"), ("UNIÃO", 1, "UNIÃO/PP")])
        self.assertEqual([(x["bloco"], x["cadeiras"], x["partidos"]) for x in corpo["blocos"]],
                         [("PL", 4, ["PL"]), ("UNIÃO/PP", 3, ["UNIÃO", "PP"])])
        self.assertEqual((corpo["total"], corpo["eleitos"], corpo["ufs_com_dados"], corpo["ufs_total"]), (513, 7, 2, 3))
        self.assertEqual(corpo["casa"], "camara")

    def test_sem_nenhuma_uf_o_hemiciclo_vem_vazio(self):
        corpo = deputados.camara({"sp": None, "rj": None})
        self.assertEqual((corpo["partidos"], corpo["blocos"], corpo["eleitos"], corpo["ufs_com_dados"], corpo["final"]), ([], [], 0, 0, False))

    def test_final_so_quando_todas_as_ufs_responderam_e_estao_finais(self):
        final = resumo_de({"PL": 1}, [{"nome": "PL", "federacao": False, "partidos": ["PL"], "cadeiras": 1}], final=True)
        self.assertTrue(deputados.camara({"sp": final, "rj": final})["final"])
        self.assertFalse(deputados.camara({"sp": final, "rj": None})["final"])
        self.assertFalse(deputados.camara({"sp": final, "rj": {**final, "final": False}})["final"])

    def test_bloco_sem_cadeira_nao_aparece(self):
        r = resumo_de({"PL": 1}, [{"nome": "PL", "federacao": False, "partidos": ["PL"], "cadeiras": 1}, {"nome": "NOVO", "federacao": False, "partidos": ["NOVO"], "cadeiras": 0}])
        self.assertEqual([b["bloco"] for b in deputados.camara({"sp": r})["blocos"]], ["PL"])

    def test_nao_mexe_nos_resumos(self):
        r = resumo_de({"PL": 1}, [{"nome": "PL", "federacao": False, "partidos": ["PL"], "cadeiras": 1}])
        antes = repr(r)
        deputados.camara({"sp": r})
        deputados.mais_votados({"sp": r})
        self.assertEqual(repr(r), antes)


class MaisVotados(unittest.TestCase):
    def test_junta_ordena_e_limita(self):
        def c(nome, votos, uf, numero="1"):
            return {"nome": nome, "partido": "PL", "numero": numero, "votos": votos, "eleito": False, "uf": uf}

        sp = resumo_de({}, [], topo=[c("A", 900, "sp"), c("B", 500, "sp")], final=True)
        rj = resumo_de({}, [], topo=[c("C", 700, "rj"), c("D", 900, "rj")], final=True)
        corpo = deputados.mais_votados({"sp": sp, "rj": rj, "ac": None}, limite=3)
        self.assertEqual([(x["posicao"], x["nome"]) for x in corpo["candidatos"]], [(1, "D"), (2, "A"), (3, "C")])  # empate em 900: rj antes de sp
        self.assertEqual((corpo["ufs_com_dados"], corpo["ufs_total"], corpo["final"]), (2, 3, False))

    def test_sem_dados_nao_inventa_ranking(self):
        self.assertEqual(deputados.mais_votados({"sp": None})["candidatos"], [])
