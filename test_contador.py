import unittest
from argparse import Namespace

import contador

DADOS = {
    "tf": "n",
    "dt": "04/10/2026",
    "ht": "18:01:02",
    "dg": "04/10/2026",
    "hg": "18:01:30",
    "s": {"ts": "1000", "st": "250", "pst": "25,00"},
    "e": {"te": "5000", "c": "900", "pc": "90,00", "a": "100", "pa": "2,00"},
    "v": {"tv": "900", "vb": "20", "pvb": "2,22", "tvn": "30", "ptvn": "3,33"},
    "carg": [
        {
            "agr": [
                {
                    "par": [
                        {
                            "sg": "AAA",
                            "cand": [
                                {"n": "11", "nm": "ANA", "nmu": "ANA", "vap": "100", "pvap": "20,00"},
                                {"n": "12", "nm": "BIA", "nmu": "BIA", "vap": "400", "pvap": "80,00", "st": "2º turno"},
                            ],
                        }
                    ]
                }
            ]
        }
    ],
}

ARGS = Namespace(cargo="presidente", uf="br", turno=1, ambiente="oficial", top=10, intervalo=10)


class MontarUrl(unittest.TestCase):
    def test_presidente_oficial(self):
        self.assertEqual(
            contador.montar_url("oficial", "presidente", "br", 1),
            "https://resultados.tse.jus.br/oficial/ele2026/6257/dados/br/br-c0001-e006257-u.json",
        )

    def test_governador_segundo_turno(self):
        self.assertEqual(
            contador.montar_url("oficial", "governador", "sp", 2),
            "https://resultados.tse.jus.br/oficial/ele2026/6260/dados/sp/sp-c0003-e006260-u.json",
        )

    def test_simulado(self):
        self.assertIn("resultados-sim.tse.jus.br/simulado/simulado2026/ele2026/21272/", contador.montar_url("simulado", "senador", "ac", 1))


class Candidatos(unittest.TestCase):
    def test_ordem_por_votos(self):
        self.assertEqual([c["nm"] for c in contador.candidatos(DADOS)], ["BIA", "ANA"])

    def test_partido_anexado(self):
        self.assertEqual(contador.candidatos(DADOS)[0]["partido"], "AAA")


class Renderizar(unittest.TestCase):
    def test_placar(self):
        texto = contador.renderizar(DADOS, ARGS)
        self.assertIn("Totalização PARCIAL", texto)
        self.assertIn("seções apuradas 250 de 1.000 (25,00%)", texto)
        self.assertLess(texto.index("BIA"), texto.index("ANA"))
        self.assertIn("2º turno", texto)

    def test_zero_votos_sem_divisao_por_zero(self):
        zerado = {**DADOS, "carg": [{"agr": [{"par": [{"sg": "A", "cand": [{"n": "1", "nm": "X", "vap": "0", "pvap": "0,00"}]}]}]}]}
        self.assertIn("X", contador.renderizar(zerado, ARGS))

    def test_top_limita_linhas(self):
        texto = contador.renderizar(DADOS, Namespace(**{**vars(ARGS), "top": 1}))
        self.assertNotIn("ANA", texto)


class Argumentos(unittest.TestCase):
    def test_presidente_padrao_br(self):
        self.assertEqual(contador.ler_argumentos([]).uf, "br")

    def test_governador_exige_uf(self):
        with self.assertRaises(SystemExit):
            contador.ler_argumentos(["-c", "governador"])

    def test_intervalo_minimo(self):
        with self.assertRaises(SystemExit):
            contador.ler_argumentos(["--intervalo", "1"])


if __name__ == "__main__":
    unittest.main()
