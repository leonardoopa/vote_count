"""Testes de `contador/divulgacao/imagem.py`."""
import unittest

from contador.divulgacao import imagem
from tests.dados import ler_png


class Imagem(unittest.TestCase):
    def test_png_valido(self):
        tela = imagem.Tela(40, 20, (1, 2, 3))
        tela.retangulo(5, 5, 10, 4, (255, 0, 0))
        largura, altura, linhas = ler_png(tela.png())
        self.assertEqual((largura, altura), (40, 20))
        self.assertEqual(linhas[0][:3], bytes((1, 2, 3)))
        self.assertEqual(linhas[5][5 * 3:5 * 3 + 3], bytes((255, 0, 0)))
        self.assertEqual(linhas[5][15 * 3:15 * 3 + 3], bytes((1, 2, 3)))  # fora do retângulo

    def test_retangulo_fora_da_tela_e_cortado(self):
        tela = imagem.Tela(10, 10)
        tela.retangulo(-5, -5, 8, 8, (9, 9, 9))
        tela.retangulo(8, 8, 50, 50, (7, 7, 7))
        tela.retangulo(20, 20, 5, 5, (1, 1, 1))
        _, _, linhas = ler_png(tela.png())
        self.assertEqual(linhas[0][:3], bytes((9, 9, 9)))
        self.assertEqual(linhas[9][27:30], bytes((7, 7, 7)))

    def test_fonte_bem_formada(self):
        for letra, linhas in imagem.FONTE.items():
            with self.subTest(letra=letra):
                self.assertEqual(len(linhas), imagem.ALTURA_GLIFO)
                self.assertTrue(all(len(linha) == imagem.LARGURA_GLIFO and set(linha) <= {".", "#"} for linha in linhas))

    def test_tem_todas_as_letras_numeros_e_a_pontuacao_usada(self):
        esperado = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,:;-+%/()·º!?'")
        self.assertEqual(esperado - set(imagem.FONTE), set())

    def test_acentos_viram_marcas_sobre_a_letra(self):
        self.assertEqual(imagem.glifos("Ação"), [("A", []), ("C", ["̧"]), ("A", ["̃"]), ("O", [])])
        self.assertEqual(imagem.glifos("é"), [("E", ["́"])])

    def test_o_que_a_fonte_nao_tem_vira_interrogacao(self):
        self.assertEqual([letra for letra, _ in imagem.glifos("a☃b")], ["A", "?", "B"])

    def test_texto_desenha_a_letra_e_o_acento_acima(self):
        tela = imagem.Tela(40, 40)
        tela.texto(10, 20, "Á", (255, 255, 255), 2)
        _, _, linhas = ler_png(tela.png())
        branco = bytes((255, 255, 255))
        acesos = {(x, y) for y, linha in enumerate(linhas) for x in range(40) if linha[x * 3:x * 3 + 3] == branco}
        self.assertTrue(any(y >= 20 for _, y in acesos))      # a letra
        self.assertTrue(any(16 <= y < 20 for _, y in acesos))  # o acento: duas linhas de escala 2 acima
        self.assertFalse(any(y < 16 for _, y in acesos))

    def test_larguras_e_alinhamento(self):
        self.assertEqual(imagem.largura_do_texto("AB", 2), (5 + 1 + 5) * 2)
        self.assertEqual(imagem.largura_do_texto("", 3), 0)
        tela = imagem.Tela(100, 20)
        usada = tela.texto(90, 0, "AB", (255, 255, 255), 2, "direita")
        self.assertEqual(usada, 22)
        _, _, linhas = ler_png(tela.png())
        self.assertTrue(any(linha[(90 - 22) * 3 + i] for linha in linhas for i in range(66)))
        self.assertFalse(any(linha[91 * 3 + i] for linha in linhas for i in range(27)))

    def test_texto_que_cabe_diminui_e_depois_corta(self):
        self.assertEqual(imagem.texto_que_cabe("OI", 1000), (6, "OI"))
        escala, texto = imagem.texto_que_cabe("A" * 20, imagem.largura_do_texto("A" * 20, 4))
        self.assertEqual((escala, texto), (4, "A" * 20))
        escala, texto = imagem.texto_que_cabe("PALAVRA" * 10, 200)
        self.assertEqual(escala, 2)
        self.assertTrue(texto.endswith("...") and imagem.largura_do_texto(texto, 2) <= 200)

    def test_icones_nos_tamanhos_pedidos(self):
        for lado, mascara in ((192, False), (512, False), (512, True)):
            with self.subTest(lado=lado, mascara=mascara):
                largura, altura, linhas = ler_png(imagem.icone(lado, mascara))
                self.assertEqual((largura, altura), (lado, lado))
                self.assertIn(bytes((255, 255, 255)), linhas[lado // 2] + linhas[int(lado * 0.6)])  # o visto
        _, _, linhas = ler_png(imagem.icone(192))
        self.assertEqual(linhas[0][:3], bytes((13, 13, 13)))
