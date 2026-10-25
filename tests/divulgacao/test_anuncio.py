"""Testes de `contador/divulgacao/anuncio.py`."""
import io
import unittest
from contextlib import redirect_stderr
from unittest import mock
from urllib.parse import quote

from contador.divulgacao import anuncio


def ler(**ambiente):
    erro = io.StringIO()
    with redirect_stderr(erro):
        return anuncio.ler(ambiente), erro.getvalue()


class Ler(unittest.TestCase):
    def test_sem_texto_nao_ha_faixa(self):
        for ambiente in ({}, {"ANUNCIO_TEXTO": ""}, {"ANUNCIO_TEXTO": "   \n "}, {"ANUNCIO_LINK": "https://exemplo.com"}):
            with self.subTest(ambiente=ambiente):
                self.assertEqual(ler(**ambiente), ({"ativo": False}, ""))

    def test_so_texto(self):
        corpo, aviso = ler(ANUNCIO_TEXTO="Anuncie aqui")
        self.assertEqual(corpo, {"ativo": True, "texto": "Anuncie aqui", "rotulo": "Publicidade"})
        self.assertEqual(aviso, "")

    def test_texto_link_e_rotulo(self):
        corpo, _ = ler(ANUNCIO_TEXTO="Oferta", ANUNCIO_LINK="https://exemplo.com.br/promo?a=1", ANUNCIO_ROTULO="Patrocinado")
        self.assertEqual(corpo, {"ativo": True, "texto": "Oferta", "rotulo": "Patrocinado", "link": "https://exemplo.com.br/promo?a=1"})

    def test_texto_vira_uma_linha_so(self):
        self.assertEqual(ler(ANUNCIO_TEXTO="  Duas \n linhas\t aqui ")[0]["texto"], "Duas linhas aqui")

    def test_texto_longo_demais_desliga_com_aviso(self):
        corpo, aviso = ler(ANUNCIO_TEXTO="x" * (anuncio.MAX_TEXTO + 1))
        self.assertEqual(corpo, {"ativo": False})
        self.assertIn("ANUNCIO_TEXTO ignorado", aviso)

    def test_texto_com_caractere_de_controle_desliga(self):
        self.assertEqual(ler(ANUNCIO_TEXTO="ruim\x00aqui")[0], {"ativo": False})

    def test_html_nao_e_interpretado_nem_barrado(self):
        # a página usa textContent: o texto passa como veio e aparece literal
        corpo, _ = ler(ANUNCIO_TEXTO="<b>oi</b> & <script>alert(1)</script>")
        self.assertEqual(corpo["texto"], "<b>oi</b> & <script>alert(1)</script>")

    def test_link_ruim_sai_sem_link_e_com_aviso(self):
        for link in ("javascript:alert(1)", "data:text/html,oi", "ftp://exemplo.com", "//exemplo.com", "exemplo.com",
                     "https://", "https://exemplo .com", "https://exemplo.com/" + "a" * 300, "https:///x"):
            with self.subTest(link=link):
                corpo, aviso = ler(ANUNCIO_TEXTO="Oferta", ANUNCIO_LINK=link)
                self.assertTrue(corpo["ativo"])
                self.assertNotIn("link", corpo)
                self.assertIn("ANUNCIO_LINK ignorado", aviso)

    def test_imagem_vai_junto_com_o_texto(self):
        corpo, aviso = ler(ANUNCIO_TEXTO="Oferta", ANUNCIO_IMAGEM=" https://cdn.exemplo.com.br/banner.png?v=2 ")
        self.assertEqual(corpo, {"ativo": True, "texto": "Oferta", "rotulo": "Publicidade", "imagem": "https://cdn.exemplo.com.br/banner.png?v=2"})
        self.assertEqual(aviso, "")

    def test_tudo_junto(self):
        corpo, _ = ler(ANUNCIO_TEXTO="Oferta", ANUNCIO_LINK="https://exemplo.com.br", ANUNCIO_ROTULO="Patrocinado", ANUNCIO_IMAGEM="http://127.0.0.1:8901/b.svg")
        self.assertEqual(corpo, {"ativo": True, "texto": "Oferta", "rotulo": "Patrocinado", "link": "https://exemplo.com.br", "imagem": "http://127.0.0.1:8901/b.svg"})

    def test_imagem_sem_texto_nao_ha_faixa(self):
        self.assertEqual(ler(ANUNCIO_IMAGEM="https://exemplo.com/b.png"), ({"ativo": False}, ""))

    def test_imagem_ruim_sai_sem_imagem_e_com_aviso_mas_o_texto_fica(self):
        for imagem in ("javascript:alert(1)", "data:image/png;base64,AAAA", "file:///etc/passwd", "ftp://exemplo.com/b.png", "//exemplo.com/b.png",
                       "/banner.png", "https://", "https://exemplo .com/b.png", "https://exemplo.com/" + "a" * 300):
            with self.subTest(imagem=imagem):
                corpo, aviso = ler(ANUNCIO_TEXTO="Oferta", ANUNCIO_IMAGEM=imagem)
                self.assertTrue(corpo["ativo"])
                self.assertNotIn("imagem", corpo)
                self.assertIn("ANUNCIO_IMAGEM ignorado", aviso)

    def test_icone_aceita_http_ou_arquivo_de_web_anuncios(self):
        for icone in ("https://cdn.exemplo.com.br/logo.png", "/anuncios/outlets-import.jpg", "/anuncios/marca-2.webp"):
            with self.subTest(icone=icone):
                corpo, aviso = ler(ANUNCIO_TEXTO="Oferta", ANUNCIO_ICONE=f" {icone} ")
                self.assertEqual(corpo["icone"], icone)
                self.assertEqual(aviso, "")

    def test_icone_ruim_sai_sem_icone_e_com_aviso_mas_o_texto_fica(self):
        for icone in ("javascript:alert(1)", "data:image/png;base64,AAAA", "/anuncios/../servidor.py", "/anuncios/Logo.png",
                      "/anuncios/logo.svg", "/js/logo.png", "anuncios/logo.png", "//exemplo.com/logo.png"):
            with self.subTest(icone=icone):
                corpo, aviso = ler(ANUNCIO_TEXTO="Oferta", ANUNCIO_ICONE=icone)
                self.assertTrue(corpo["ativo"])
                self.assertNotIn("icone", corpo)
                self.assertIn("ANUNCIO_ICONE ignorado", aviso)

    def test_whatsapp_vira_link_wa_me_com_mensagem_padrao(self):
        corpo, aviso = ler(ANUNCIO_TEXTO="Oferta", ANUNCIO_WHATSAPP="5581999999999")
        self.assertEqual(corpo["link"], "https://wa.me/5581999999999?text=" + quote(anuncio.MENSAGEM_PADRAO))
        self.assertTrue(anuncio.link_valido(corpo["link"]))
        self.assertEqual(aviso, "")

    def test_whatsapp_aceita_pontuacao_e_mensagem_propria(self):
        corpo, _ = ler(ANUNCIO_TEXTO="Oferta", ANUNCIO_WHATSAPP=" +55 (81) 99999-9999 ", ANUNCIO_WHATSAPP_MENSAGEM="Olá, quero anunciar & saber o preço?")
        self.assertEqual(corpo["link"], "https://wa.me/5581999999999?text=Ol%C3%A1%2C%20quero%20anunciar%20%26%20saber%20o%20pre%C3%A7o%3F")

    def test_mensagem_ruim_volta_a_padrao(self):
        for mensagem in ("x" * (anuncio.MAX_MENSAGEM + 1), "ruim\x00aqui", ""):
            with self.subTest(mensagem=mensagem[:10]):
                corpo, _ = ler(ANUNCIO_TEXTO="Oferta", ANUNCIO_WHATSAPP="5581999999999", ANUNCIO_WHATSAPP_MENSAGEM=mensagem)
                self.assertTrue(corpo["link"].endswith(quote(anuncio.MENSAGEM_PADRAO)))

    def test_whatsapp_ruim_sai_sem_link_e_com_aviso(self):
        for numero in ("123", "abc", "55819999999x", "5581999999999999", "https://wa.me/5581999999999", "+55 81 9999;9999"):
            with self.subTest(numero=numero):
                corpo, aviso = ler(ANUNCIO_TEXTO="Oferta", ANUNCIO_WHATSAPP=numero)
                self.assertTrue(corpo["ativo"])
                self.assertNotIn("link", corpo)
                self.assertIn("ANUNCIO_WHATSAPP ignorado", aviso)

    def test_link_explicito_vale_mais_que_o_whatsapp(self):
        corpo, aviso = ler(ANUNCIO_TEXTO="Oferta", ANUNCIO_LINK="https://exemplo.com.br", ANUNCIO_WHATSAPP="5581999999999")
        self.assertEqual(corpo["link"], "https://exemplo.com.br")
        self.assertIn("ANUNCIO_WHATSAPP ignorado", aviso)

    def test_link_ruim_nao_bloqueia_o_whatsapp(self):
        corpo, _ = ler(ANUNCIO_TEXTO="Oferta", ANUNCIO_LINK="javascript:alert(1)", ANUNCIO_WHATSAPP="5581999999999")
        self.assertTrue(corpo["link"].startswith("https://wa.me/5581999999999"))

    def test_rotulo_invalido_volta_ao_padrao(self):
        self.assertEqual(ler(ANUNCIO_TEXTO="Oferta", ANUNCIO_ROTULO="x" * 40)[0]["rotulo"], "Publicidade")
        self.assertEqual(ler(ANUNCIO_TEXTO="Oferta", ANUNCIO_ROTULO="")[0]["rotulo"], "Publicidade")

    def test_do_ambiente_le_o_ambiente_do_processo(self):
        with mock.patch.dict("os.environ", {"ANUNCIO_TEXTO": "Do ambiente"}, clear=True):
            self.assertEqual(anuncio.do_ambiente()["texto"], "Do ambiente")
