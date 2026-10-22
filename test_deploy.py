"""O deploy/deploy.sh de verdade, num repositório git temporário e com um `docker` de mentira no PATH: nada sai da máquina."""
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("deploy") / "deploy.sh"

# `docker compose ... up` anota a chamada (e falha se FAKE_UP_RC != 0), `ps -q` devolve um id e `inspect` responde
# `unhealthy` quando o commit em uso (git HEAD do diretório atual) é o que o teste marcou como ruim.
DOCKER_FALSO = """#!/usr/bin/env bash
case "$*" in
  *" up "*) echo "up sha=$(git rev-parse HEAD)" >> "$FAKE_LOG"; exit "${FAKE_UP_RC:-0}" ;;
  *" ps "*) echo "id123" ;;
  inspect*) [ "$(git rev-parse HEAD)" = "${FAKE_RUIM:-}" ] && echo unhealthy || echo healthy ;;
esac
"""


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@unittest.skipUnless(shutil.which("bash") and shutil.which("git"), "precisa de bash e git")
class Deploy(unittest.TestCase):
    def setUp(self):
        raiz = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, raiz, ignore_errors=True)
        self.raiz = raiz
        self.origem, self.vps, self.bin = raiz / "origem.git", raiz / "vps", raiz / "bin"
        self.log = raiz / "docker.log"
        self.bin.mkdir()
        falso = self.bin / "docker"
        falso.write_text(DOCKER_FALSO)
        falso.chmod(falso.stat().st_mode | stat.S_IEXEC)
        git(raiz, "init", "-q", "--bare", "-b", "main", str(self.origem))
        trabalho = raiz / "trabalho"
        git(raiz, "clone", "-q", str(self.origem), str(trabalho))
        git(trabalho, "config", "user.email", "t@t")
        git(trabalho, "config", "user.name", "t")
        self.trabalho = trabalho
        self.c1 = self.commit("um")
        self.c2 = self.commit("dois")
        self.c3 = self.commit("tres")
        git(trabalho, "push", "-q", "origin", "main")
        git(raiz, "clone", "-q", str(self.origem), str(self.vps))
        git(self.vps, "reset", "-q", "--hard", self.c1)     # a VPS está no primeiro commit
        self.trava = raiz / "tmp"
        self.trava.mkdir()

    def commit(self, texto):
        for nome in ("compose.yaml", "compose.vps.yaml"):
            (self.trabalho / nome).write_text(f"# {texto}\n")
        git(self.trabalho, "add", ".")
        git(self.trabalho, "commit", "-q", "-m", texto)
        return git(self.trabalho, "rev-parse", "HEAD")

    def rodar(self, *args, **ambiente):
        env = {**os.environ, "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}", "FAKE_LOG": str(self.log), "ESPERA_S": "5",
               "INTERVALO_S": "0.05", "TMPDIR": str(self.trava), **ambiente}
        return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, env=env)

    def ups(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_deploy_leva_a_vps_ao_commit_e_sobe_o_compose(self):
        r = self.rodar(self.c2, str(self.vps))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(git(self.vps, "rev-parse", "HEAD"), self.c2)
        self.assertEqual(self.ups(), [f"up sha={self.c2}"])
        self.assertIn(f"No ar agora: {self.c1}", r.stdout)
        self.assertIn(f"Deploy de:   {self.c2}", r.stdout)

    def test_alteracao_local_na_vps_some_mas_o_env_fica(self):
        (self.vps / "compose.yaml").write_text("# mexido à mão\n")
        (self.vps / ".env").write_text("SEGREDO=1\n")
        self.assertEqual(self.rodar(self.c2, str(self.vps)).returncode, 0)
        self.assertEqual((self.vps / "compose.yaml").read_text(), "# dois\n")
        self.assertEqual((self.vps / ".env").read_text(), "SEGREDO=1\n")

    def test_nunca_mostra_o_env(self):
        (self.vps / ".env").write_text("SEGREDO=valor-secreto\n")
        r = self.rodar(self.c2, str(self.vps))
        self.assertNotIn("valor-secreto", r.stdout + r.stderr)

    def test_contenir_nao_saudavel_volta_ao_commit_anterior_e_falha(self):
        r = self.rodar(self.c3, str(self.vps), FAKE_RUIM=self.c3)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(git(self.vps, "rev-parse", "HEAD"), self.c1)       # voltou para o que estava no ar
        self.assertEqual(self.ups(), [f"up sha={self.c3}", f"up sha={self.c1}"])
        self.assertIn(f"Voltando para {self.c1}", r.stderr)
        self.assertIn("Rollback concluído", r.stderr)

    def test_compose_que_falha_tambem_faz_rollback(self):
        r = self.rodar(self.c2, str(self.vps), FAKE_UP_RC="1")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(git(self.vps, "rev-parse", "HEAD"), self.c1)
        self.assertEqual(len(self.ups()), 2)                                # tentou o novo e tentou voltar

    def test_commit_fora_da_main_e_recusado_antes_de_mexer_em_qualquer_coisa(self):
        git(self.trabalho, "checkout", "-q", "-b", "outra")
        fora = self.commit("fora da main")
        git(self.trabalho, "push", "-q", "origin", "outra")
        git(self.vps, "fetch", "-q", "origin")          # a VPS já conhece o commit (veio de outra branch), mas ele não está na main
        r = self.rodar(fora, str(self.vps))
        self.assertEqual(r.returncode, 2)
        self.assertIn("não está na main", r.stderr)
        self.assertEqual(git(self.vps, "rev-parse", "HEAD"), self.c1)
        self.assertEqual(self.ups(), [])

    def test_sha_invalido_ou_inexistente(self):
        for sha in ("", "abc", "main", self.c2.upper(), self.c2[:39], "g" * 40, f"{self.c2};rm -rf /"):
            with self.subTest(sha=sha[:12]):
                r = self.rodar(sha, str(self.vps))
                self.assertEqual(r.returncode, 2)
        r = self.rodar("0" * 40, str(self.vps))
        self.assertEqual(r.returncode, 2)
        self.assertIn("não existe", r.stderr)
        self.assertEqual(self.ups(), [])

    def test_diretorio_errado(self):
        self.assertEqual(self.rodar(self.c2, str(self.raiz / "nada")).returncode, 2)
        self.assertEqual(self.rodar(self.c2, str(self.bin)).returncode, 2)       # existe, mas não é repositório

    def test_commit_que_ja_esta_no_ar_e_saudavel_nao_refaz(self):
        r = self.rodar(self.c1, str(self.vps))
        self.assertEqual(r.returncode, 0)
        self.assertIn("já está no ar", r.stdout)
        self.assertEqual(self.ups(), [])
        self.assertEqual(self.rodar(self.c1, str(self.vps), FORCAR="1").returncode, 0)
        self.assertEqual(self.ups(), [f"up sha={self.c1}"])

    def test_dois_deploys_ao_mesmo_tempo_nao_se_atropelam(self):
        (self.trava / "vote_count-deploy.lock").mkdir()
        r = self.rodar(self.c2, str(self.vps))
        self.assertEqual(r.returncode, 3)
        self.assertIn("outro deploy", r.stderr)
        self.assertEqual(git(self.vps, "rev-parse", "HEAD"), self.c1)

    def test_trava_some_ao_terminar(self):
        self.rodar(self.c2, str(self.vps))
        self.assertFalse((self.trava / "vote_count-deploy.lock").exists())
        self.rodar(self.c3, str(self.vps), FAKE_RUIM=self.c3)
        self.assertFalse((self.trava / "vote_count-deploy.lock").exists())


class Workflow(unittest.TestCase):
    """Conferências estáticas do workflow: o que não pode mudar sem querer."""

    TEXTO = Path(__file__).with_name(".github").joinpath("workflows", "deploy.yml").read_text(encoding="utf-8")

    def test_so_roda_depois_da_ci_na_main_e_nunca_em_pull_request(self):
        for trecho in ("workflows: [CI]", "branches: [main]", "github.event.workflow_run.conclusion == 'success'", "github.event.workflow_run.event == 'push'",
                       "github.event.workflow_run.head_branch == 'main'", "head_repository.full_name == github.repository"):
            self.assertIn(trecho, self.TEXTO)
        self.assertNotIn("pull_request", self.TEXTO)

    def test_um_deploy_por_vez_sem_cortar_o_que_esta_rodando(self):
        self.assertIn("group: deploy-producao", self.TEXTO)
        self.assertIn("cancel-in-progress: false", self.TEXTO)

    def test_permissoes_minimas_e_ambiente_de_producao(self):
        self.assertIn("permissions:\n  contents: read", self.TEXTO)
        self.assertIn("environment: production", self.TEXTO)
        self.assertNotIn("write", self.TEXTO.replace("persist-credentials", ""))

    def test_ssh_confere_a_chave_do_servidor(self):
        self.assertIn("StrictHostKeyChecking=yes", self.TEXTO)
        self.assertNotIn("StrictHostKeyChecking=no", self.TEXTO)
        self.assertNotIn("ssh-keyscan", self.TEXTO)          # o known_hosts vem de um secret, não da rede na hora do deploy

    def test_secrets_so_entram_por_variavel_de_ambiente(self):
        """`${{ secrets.X }}` dentro do script de `run:` viraria texto do comando (e pode vazar ou quebrar): só em `env:`."""
        for linha in self.TEXTO.splitlines():
            if "secrets." in linha:
                self.assertRegex(linha, r"^\s+[A-Z_]+: \$\{\{ secrets\.[A-Z_]+ \}\}$", linha)

    def test_desligar_pela_variavel(self):
        self.assertIn("vars.DEPLOY_AUTOMATICO != 'false'", self.TEXTO)

    def test_chave_nao_fica_no_runner(self):
        self.assertIn("rm -f ~/.ssh/deploy_key", self.TEXTO)


if __name__ == "__main__":
    unittest.main()
