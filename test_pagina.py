"""Conferências estáticas da página (web/index.html, estilo e scripts) e do gerador de contornos do mapa."""
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import contador
from tools import gerar_mapa

WEB = Path(__file__).with_name("web")
HTML = (WEB / "index.html").read_text(encoding="utf-8")
CSS = (WEB / "estilo.css").read_text(encoding="utf-8")
ARQUIVOS_JS = re.findall(r'<script defer src="/js/([a-z0-9-]+)\.js"></script>', HTML)  # na ordem em que a página carrega


def script():
    """Os scripts da página juntos, na ordem de carga (compartilham o mesmo escopo global)."""
    return "\n".join((WEB / "js" / f"{nome}.js").read_text(encoding="utf-8") for nome in ARQUIVOS_JS)


def chaves_do_objeto(nome):
    """Chaves (siglas) do objeto JavaScript `const nome = { sp: ..., rj: ... }`, no nível de cima."""
    corpo = re.search(rf"const {nome} = \{{(.*?)\n\}};", script(), re.S).group(1)
    return re.findall(r'\b([a-z]{2}): [{"]', corpo)


class Pagina(unittest.TestCase):
    def test_todas_as_ufs_tem_nome_e_contorno(self):
        self.assertEqual(sorted(chaves_do_objeto("UFS")), sorted(contador.UFS))
        self.assertEqual(sorted(chaves_do_objeto("MAPA_UFS")), sorted(contador.UFS))

    def test_contornos_sao_caminhos_fechados(self):
        for sigla, d in re.findall(r'(?:^|\n)\s*([a-z]{2}): \{"d":"([^"]+)"', script()):
            with self.subTest(uf=sigla):
                self.assertTrue(d.startswith("M") and d.endswith("z"))
                self.assertRegex(d, r"^[Mlz0-9 .\-]+$")

    def test_sem_dependencia_externa(self):
        # Scripts e estilo vêm do próprio servidor (pasta web/), nunca de um CDN.
        self.assertEqual(sorted(re.findall(r'<script[^>]+src="([^"]+)"', HTML)), sorted(f"/js/{nome}.js" for nome in ARQUIVOS_JS))
        self.assertEqual(re.findall(r'<link[^>]+rel="stylesheet"[^>]*href="([^"]+)"', HTML), ["/estilo.css"])
        self.assertNotRegex(HTML, r"<script>")
        self.assertNotRegex(HTML, r"<style")
        for texto in (HTML, CSS, script()):
            self.assertNotIn("@import", texto)
            self.assertNotRegex(texto, r"url\(\s*['\"]?(?:https?:)?//")
            self.assertNotRegex(texto, r"\b(?:src|action)=[\"'](?:https?:)?//")

    def test_todo_script_da_pasta_esta_na_pagina(self):
        em_disco = sorted(arquivo.stem for arquivo in (WEB / "js").glob("*.js"))
        self.assertEqual(em_disco, sorted(ARQUIVOS_JS))
        self.assertEqual((ARQUIVOS_JS[0], ARQUIVOS_JS[-1]), ("base", "iniciar"))   # base define o que os outros usam; iniciar roda por último
        self.assertEqual(len(ARQUIVOS_JS), len(set(ARQUIVOS_JS)))

    def test_scripts_carregam_na_ordem_sem_referencia_quebrada(self):
        """Roda os scripts na ordem da página num DOM de mentira: um nome usado no carregamento antes de existir é ReferenceError."""
        node = shutil.which("node")
        if not node:
            self.skipTest("node não está instalado")
        programa = r"""
const vm = require("vm"), fs = require("fs");
process.on("unhandledRejection", () => {});
const falso = new Proxy(function () {}, {
  get: (_, chave) => (chave === Symbol.toPrimitive ? () => "" : chave === "then" ? undefined : falso),
  apply: () => falso, construct: () => falso, set: () => true,
});
const contexto = vm.createContext({
  document: falso, window: falso, navigator: falso, history: falso, localStorage: falso, sessionStorage: falso, Notification: falso, Option: falso, Image: falso,
  location: { search: "", protocol: "http:", hostname: "localhost", href: "http://localhost/", origin: "http://localhost", pathname: "/" },
  fetch: () => new Promise(() => {}), setInterval: () => 0, setTimeout: () => 0, clearTimeout() {}, clearInterval() {},
  requestAnimationFrame: () => 0, cancelAnimationFrame() {}, matchMedia: () => falso,
  console: { log() {}, error() {}, warn() {} }, URLSearchParams, URL, Blob, TextEncoder,
});
const quebrados = [];
for (const arquivo of process.argv.slice(1)) {
  try { vm.runInContext(fs.readFileSync(arquivo, "utf8"), contexto, { filename: arquivo }); }
  catch (erro) { if (erro && (erro.name === "ReferenceError" || erro.name === "SyntaxError")) quebrados.push(arquivo + ": " + erro.message); }
}
process.stdout.write(JSON.stringify(quebrados));
"""
        arquivos = [str(WEB / "js" / f"{nome}.js") for nome in ARQUIVOS_JS]
        resultado = subprocess.run([node, "-e", programa, *arquivos], capture_output=True, text=True)
        self.assertEqual(resultado.returncode, 0, resultado.stderr[-600:])
        self.assertEqual(json.loads(resultado.stdout), [])

    def test_ids_usados_pelo_script_existem_na_pagina(self):
        ids = set(re.findall(r'\bid="([^"]+)"', HTML))
        usados = set(re.findall(r'\$\("([a-z0-9-]+)"\)', script()))
        self.assertEqual(sorted(usados - ids), [])

    def test_csv_para_planilha_brasileira_e_sem_formula(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node não está instalado")
        fonte = re.search(r"(function celulaCsv.*?\nfunction montarCsv.*?\n\})", script(), re.S).group(1)
        candidatos = [
            {"posicao": 1, "numero": "13", "nome": "ANA LIMA", "partido": "PT", "votos": 1200, "percentual": 37.58, "situacao": ""},
            {"posicao": 2, "numero": "22", "nome": "=CMD|'/c calc'!A1", "partido": "P;L", "votos": 900, "percentual": 31.8, "situacao": 'Eleito "com aspas"'},
        ]
        programa = f"{fonte}\nprocess.stdout.write(JSON.stringify(montarCsv({json.dumps(candidatos)})));"
        saida = subprocess.run([node, "-e", programa], capture_output=True, text=True, check=True).stdout
        self.assertEqual(json.loads(saida), (
            "\ufeffposicao;numero;nome;partido;votos;percentual;situacao\r\n"
            "1;13;ANA LIMA;PT;1200;37,58;\r\n"
            "2;22;'=CMD|'/c calc'!A1;\"P;L\";900;31,8;\"Eleito \"\"com aspas\"\"\"\r\n"
        ))

    def test_service_worker_so_responde_pela_pagina_e_pelos_arquivos_dela(self):
        """O service worker de verdade num ambiente de mentira: /api, /geo e outras origens passam direto, sem cache."""
        node = shutil.which("node")
        if not node:
            self.skipTest("node não está instalado")
        programa = r"""
const vm = require("vm"), fs = require("fs");
const ouvintes = {}, guardados = [];
const contexto = vm.createContext({
  self: { addEventListener: (nome, f) => { ouvintes[nome] = f; }, skipWaiting() {}, clients: { claim() {} } },
  location: { origin: "http://x" }, URL, Response: class {},
  caches: { open: async () => ({ put: (chave) => guardados.push(chave) }), match: async () => undefined, keys: async () => [], delete: async () => true },
  fetch: () => Promise.resolve({ ok: true, clone: () => ({}) }),
});
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), contexto);
const casos = JSON.parse(process.argv[2]);
(async () => {
  const respondeu = [];
  for (const [metodo, modo, url] of casos) {
    let sim = false;
    ouvintes.fetch({ request: { method: metodo, mode: modo, url }, respondWith: (p) => { sim = true; p.catch(() => {}); } });
    respondeu.push(sim);
  }
  await new Promise((r) => setTimeout(r, 20));
  process.stdout.write(JSON.stringify({ respondeu, guardados }));
})();
"""
        casos = [
            ("GET", "navigate", "http://x/", True), ("GET", "navigate", "http://x/?cargo=presidente&uf=sp", True),
            ("GET", "cors", "http://x/js/base.js", True), ("GET", "no-cors", "http://x/estilo.css", True),
            ("GET", "cors", "http://x/api/placar?cargo=presidente", False), ("GET", "navigate", "http://x/api/mapa-municipal", False),
            ("GET", "cors", "http://x/geo/pe.json", False), ("GET", "navigate", "http://x/og.png", False),
            ("POST", "cors", "http://x/js/base.js", False), ("GET", "cors", "http://outro/js/base.js", False),
            ("GET", "cors", "http://x/js/../servidor.py", False), ("GET", "cors", "http://x/js/dir/base.js", False),
        ]
        resultado = subprocess.run([node, "-e", programa, str(WEB / "sw.js"), json.dumps([caso[:3] for caso in casos])], capture_output=True, text=True)
        self.assertEqual(resultado.returncode, 0, resultado.stderr[-600:])
        saida = json.loads(resultado.stdout)
        self.assertEqual(saida["respondeu"], [caso[3] for caso in casos])
        self.assertEqual(saida["guardados"], ["/", "/", "/js/base.js", "/estilo.css"])      # só a página e os arquivos dela

    def test_sintaxe_do_javascript(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node não está instalado")
        for arquivo in [*(WEB / "js").glob("*.js"), WEB / "sw.js"]:
            with self.subTest(arquivo=arquivo.name):
                resultado = subprocess.run([node, "--check", str(arquivo)], capture_output=True, text=True)
                self.assertEqual(resultado.returncode, 0, resultado.stderr)


class GerarMapa(unittest.TestCase):
    def test_simplificar_tira_pontos_alinhados(self):
        reta = [(0, 0), (1, 0.01), (2, 0), (3, 0.01), (4, 0)]
        self.assertEqual(gerar_mapa.douglas_peucker(reta, 0.5), [(0, 0), (4, 0)])
        self.assertEqual(gerar_mapa.douglas_peucker(reta, 0.0001), reta)

    def test_caminho_usa_deslocamentos_inteiros(self):
        self.assertEqual(gerar_mapa.caminho([(10.2, 20.4), (13, 20), (13, 25)]), "M10 20l3 0 0 5z")
        self.assertEqual(gerar_mapa.caminho([(5, 5), (3, 7), (6, 4)]), "M5 5l-2 2 3-3z")

    def test_area_e_centro_de_um_quadrado(self):
        area, centro = gerar_mapa.area_e_centro([(0, 0), (10, 0), (10, 10), (0, 10)])
        self.assertEqual((area, centro), (100, (5, 5)))

    def test_gera_o_objeto_a_partir_de_uma_malha(self):
        def quadrado(x, y, lado=20):
            return [[x, y], [x + lado, y], [x + lado, y + lado], [x, y + lado], [x, y]]

        malha = {"features": [
            {"properties": {"codarea": "35"}, "geometry": {"type": "Polygon", "coordinates": [quadrado(-50, -25)]}},
            {"properties": {"codarea": "33"}, "geometry": {"type": "MultiPolygon", "coordinates": [[quadrado(-30, -20)], [quadrado(-60, -10, 0.001)]]}},
        ]}
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "malha.json"
            arquivo.write_text(json.dumps(malha), encoding="utf-8")
            saida = io.StringIO()
            with mock.patch.object(sys, "argv", ["gerar_mapa.py", str(arquivo)]), redirect_stdout(saida):
                gerar_mapa.main()
        texto = saida.getvalue()
        self.assertIn("const MAPA_TAMANHO = [1000,", texto)
        self.assertRegex(texto, r'\n  sp: \{"d":"M[^"]+z","c":\[\d+,\d+\],"l":\d+\},')
        self.assertRegex(texto, r'\n  rj: \{"d":"M[^"]+z","c"')
        self.assertEqual(texto.count('"d":"M'), 2)  # a ilha minúscula do RJ some

    def test_mundo_so_com_paises_de_codigo_iso_e_sem_antartida(self):
        def pais(iso, nome, x, y, lado, nome_en="x"):
            quadrado = [[x, y], [x + lado, y], [x + lado, y + lado], [x, y + lado], [x, y]]
            return {"properties": {"ISO_A2_EH": iso, "NAME_PT": nome, "NAME": nome_en}, "geometry": {"type": "Polygon", "coordinates": [quadrado]}}

        malha = {"features": [
            pais("BR", "Brasil", -60, -20, 25), pais("SG", "Singapura", 103.6, 1.2, 0.3),   # minúsculo: não pode sumir
            pais("AQ", "Antártida", -60, -80, 20), pais("-9", "Sem código", 0, 0, 5), pais("-99", "Sem código", 10, 10, 5),
            {"properties": {"ISO_A2_EH": "ID", "NAME_PT": "Indonésia"}, "geometry": {"type": "MultiPolygon", "coordinates": [
                [[[100, -5], [110, -5], [110, 5], [100, 5], [100, -5]]], [[[120, -1], [120.05, -1], [120.05, -0.95], [120, -0.95], [120, -1]]]]}},
        ]}
        largura, altura, formas, nomes = gerar_mapa.converter_mundo(malha)
        self.assertEqual(largura, gerar_mapa.LARGURA_MUNDO)
        self.assertEqual(sorted(formas), ["BR", "ID", "SG"])
        self.assertEqual(nomes, {"BR": "Brasil", "ID": "Indonésia", "SG": "Singapura"})
        self.assertTrue(all(d.startswith("M") and d.endswith("z") for d in formas.values()))
        self.assertEqual(formas["ID"].count("M"), 1)        # a ilhota some, a ilha grande fica
        self.assertGreater(altura, 0)

    def test_miller_afasta_menos_os_polos_que_mercator(self):
        x, y = gerar_mapa.miller(180, 0)
        self.assertAlmostEqual(x, 3.14159, places=4)
        self.assertEqual(round(y, 6), 0)
        self.assertLess(gerar_mapa.miller(0, 80)[1], 3.0)
        self.assertLess(gerar_mapa.miller(0, -30)[1], 0)


if __name__ == "__main__":
    unittest.main()
