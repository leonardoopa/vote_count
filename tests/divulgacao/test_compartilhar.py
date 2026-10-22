"""Testes de `contador/divulgacao/compartilhar.py`."""
import unittest

from contador.divulgacao import compartilhar, imagem
from contador.recursos import placar
from tests.dados import ler_png, tse


class Compartilhar(unittest.TestCase):
    def test_cor_segue_o_partido(self):
        self.assertEqual(compartilhar.cor_do_partido("PT"), imagem.hex_rgb("#e66767"))
        self.assertEqual(compartilhar.cor_do_partido("PL"), imagem.hex_rgb("#3987e5"))
        self.assertEqual(compartilhar.cor_do_partido("União"), imagem.hex_rgb("#9085e9"))
        self.assertEqual(compartilhar.cor_do_partido("XYZ"), imagem.hex_rgb("#898781"))
        self.assertEqual(compartilhar.cor_do_partido(None), imagem.hex_rgb("#898781"))

    def test_titulo(self):
        self.assertEqual(compartilhar.titulo_da_selecao("presidente", "br", 1), "Presidente · Brasil · 1º turno")
        self.assertEqual(compartilhar.titulo_da_selecao("governador", "sp", 2, "Campinas"), "Governador · Campinas (SP) · 2º turno")
        self.assertEqual(compartilhar.titulo_da_selecao("senador", "mg", 1), "Senador · Minas Gerais · 1º turno")

    def test_descricao(self):
        resumo = placar.resumir(tse([700, 300], apuradas=500), 3)
        self.assertEqual(compartilhar.descricao_do_placar(resumo), "ANA LIMA 70,00% · BRUNO CASTRO 30,00% · 50,00% das seções apuradas")
        final = placar.resumir(tse([700, 300], final=True), 3)
        self.assertTrue(compartilhar.descricao_do_placar(final).endswith("apuração final"))
        self.assertEqual(compartilhar.descricao_do_placar(None), compartilhar.DESCRICAO_PADRAO)
        self.assertEqual(compartilhar.descricao_do_placar(placar.resumir(tse([0, 0], apuradas=0), 3)), compartilhar.DESCRICAO_PADRAO)

    def test_base_publica(self):
        self.assertEqual(compartilhar.base_publica("https://votos.exemplo.com/", {"Host": "x"}), "https://votos.exemplo.com")
        self.assertEqual(compartilhar.base_publica("", {"Host": "127.0.0.1:8000"}), "http://127.0.0.1:8000")
        self.assertEqual(compartilhar.base_publica("", {"Host": "votos.exemplo.com", "X-Forwarded-Proto": "https"}), "https://votos.exemplo.com")
        self.assertEqual(compartilhar.base_publica("", {"Host": "votos.exemplo.com", "X-Forwarded-Proto": "javascript"}), "http://votos.exemplo.com")
        for ruim in ("", "a b", "evil.com/<script>", 'x"onload="y', "a" * 300):
            with self.subTest(host=ruim):
                self.assertEqual(compartilhar.base_publica("", {"Host": ruim}), "")

    def test_meta_tags_escapam_tudo(self):
        meta = compartilhar.meta_tags("https://x.com", "cargo=presidente", 'Ataque "><script>alert(1)</script>', "a & b <i>")
        self.assertNotIn("<script>", meta)
        self.assertIn("&quot;&gt;&lt;script&gt;", meta)
        self.assertIn("a &amp; b &lt;i&gt;", meta)
        self.assertIn('content="https://x.com/og.png?cargo=presidente"', meta)
        self.assertIn('<link rel="manifest" href="/manifest.webmanifest">', meta)

    def test_sem_base_nao_ha_url_absoluta(self):
        meta = compartilhar.meta_tags("", "")
        self.assertNotIn("og:image", meta)
        self.assertIn("og:title", meta)

    def test_cartao_com_e_sem_dados(self):
        resumo = placar.resumir(tse([700, 300], apuradas=500, situacoes={"13": "Eleito"}), 4)
        for dados in (resumo, None):
            largura, altura, linhas = ler_png(compartilhar.cartao("Presidente · Brasil · 1º turno", dados, "simulado"))
            self.assertEqual((largura, altura), (imagem.LARGURA_OG, imagem.ALTURA_OG))
        _, _, linhas = ler_png(compartilhar.cartao("Presidente · Brasil · 1º turno", resumo))
        pixels = b"".join(linhas)
        self.assertIn(bytes(compartilhar.cor_do_partido("PT")) * 50, pixels)   # a barra do PT
        self.assertIn(bytes(compartilhar.cor_do_partido("PL")) * 50, pixels)

    def test_titulo_enorme_nao_estoura(self):
        _, _, linhas = ler_png(compartilhar.cartao("X" * 500, None))
        self.assertEqual(len(linhas), imagem.ALTURA_OG)
