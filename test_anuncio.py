import io
import unittest
from contextlib import redirect_stderr
from unittest import mock

import anuncio
import servidor


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

    def test_rotulo_invalido_volta_ao_padrao(self):
        self.assertEqual(ler(ANUNCIO_TEXTO="Oferta", ANUNCIO_ROTULO="x" * 40)[0]["rotulo"], "Publicidade")
        self.assertEqual(ler(ANUNCIO_TEXTO="Oferta", ANUNCIO_ROTULO="")[0]["rotulo"], "Publicidade")

    def test_do_ambiente_le_o_ambiente_do_processo(self):
        with mock.patch.dict("os.environ", {"ANUNCIO_TEXTO": "Do ambiente"}, clear=True):
            self.assertEqual(anuncio.do_ambiente()["texto"], "Do ambiente")


class Rota(unittest.TestCase):
    def test_rota_devolve_a_configuracao(self):
        configurado = {"ativo": True, "texto": "Oferta", "rotulo": "Publicidade"}
        with mock.patch.object(servidor, "ANUNCIO", configurado):
            self.assertEqual(servidor.ROTAS_API["/api/anuncio"]({}), (200, configurado))


if __name__ == "__main__":
    unittest.main()
