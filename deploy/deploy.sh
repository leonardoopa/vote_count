#!/usr/bin/env bash
# Deploy na VPS: leva o código para um commit da main, sobe o compose e confere a saúde do contêiner.
# Se não ficar saudável, volta ao commit que estava no ar e sai com erro (para o deploy aparecer como falho).
#
#   bash deploy.sh <sha com 40 caracteres> [diretório do projeto na VPS]
#
# O workflow `.github/workflows/deploy.yml` roda este arquivo por SSH (`bash -s -- <sha> <diretório> < deploy.sh`),
# então ele funciona mesmo no primeiro deploy, antes de existir na VPS. Também dá para rodar à mão, dentro do projeto.
# Nunca lê nem mostra o .env: só chama git e docker compose.
#
# Variáveis opcionais: ESPERA_S (tempo máximo para ficar saudável, padrão 120), INTERVALO_S (entre conferências,
# padrão 3), FORCAR=1 (refaz o deploy mesmo que o commit já esteja no ar e saudável).
set -euo pipefail

SHA="${1:-}"
DIR="${2:-$PWD}"
ESPERA_S="${ESPERA_S:-120}"
INTERVALO_S="${INTERVALO_S:-3}"
TRAVA="${TMPDIR:-/tmp}/vote_count-deploy.lock"
COMPOSE=(docker compose -f compose.yaml -f compose.vps.yaml)

falhar() {
  echo "ERRO: $*" >&2
  exit "${CODIGO:-1}"
}

# Estado do contêiner do contador: healthy, unhealthy, starting, running (imagem sem HEALTHCHECK) ou sem-conteiner.
estado_do_contador() {
  local id
  id="$("${COMPOSE[@]}" ps -q contador 2>/dev/null | head -n 1 || true)"
  if [ -z "$id" ]; then
    echo "sem-conteiner"
    return
  fi
  docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$id" 2>/dev/null \
    || echo "sem-conteiner"
}

# Espera o contêiner ficar saudável. `unhealthy` já é resposta final: o Docker só o marca depois das tentativas dele.
esperar_saude() {
  local limite=$((SECONDS + ESPERA_S)) estado=""
  while [ "$SECONDS" -lt "$limite" ]; do
    estado="$(estado_do_contador)"
    case "$estado" in
      healthy | running) echo "Contêiner: $estado"; return 0 ;;
      unhealthy) break ;;
    esac
    sleep "$INTERVALO_S"
  done
  echo "Contêiner não ficou saudável (estado: ${estado:-desconhecido})" >&2
  return 1
}

# Código exatamente no commit pedido (alterações locais na VPS somem; o .env, que o git ignora, não) e compose no ar.
subir() {
  git reset --hard --quiet "$1"
  "${COMPOSE[@]}" up -d --build --remove-orphans
}

[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || CODIGO=2 falhar "uso: deploy.sh <sha com 40 caracteres hexadecimais> [diretório]"
cd "$DIR" || CODIGO=2 falhar "diretório não existe: $DIR"
git rev-parse --is-inside-work-tree > /dev/null 2>&1 || CODIGO=2 falhar "$DIR não é um repositório git"
[ -f compose.yaml ] && [ -f compose.vps.yaml ] || CODIGO=2 falhar "compose.yaml e compose.vps.yaml precisam estar em $DIR"

# Um deploy por vez; a trava some ao terminar (mesmo se o SSH cair).
if ! mkdir "$TRAVA" 2> /dev/null; then
  CODIGO=3 falhar "outro deploy está em andamento (apague $TRAVA se tiver certeza de que não)"
fi
trap 'rmdir "$TRAVA" 2> /dev/null || true' EXIT

anterior="$(git rev-parse HEAD)"
git fetch --quiet origin main
git cat-file -e "$SHA^{commit}" 2> /dev/null || CODIGO=2 falhar "o commit $SHA não existe no repositório da VPS"
git merge-base --is-ancestor "$SHA" origin/main || CODIGO=2 falhar "o commit $SHA não está na main: só a main vai para produção"

echo "No ar agora: $anterior"
echo "Deploy de:   $SHA"

if [ "$anterior" = "$SHA" ] && [ "${FORCAR:-0}" != 1 ] && [ "$(estado_do_contador)" = healthy ]; then
  echo "Esse commit já está no ar e saudável. Nada a fazer (FORCAR=1 refaz)."
  exit 0
fi

if subir "$SHA" && esperar_saude; then
  echo "Deploy concluído: $SHA (antes: $anterior)"
  exit 0
fi

echo "O deploy de $SHA falhou." >&2
if [ "$anterior" != "$SHA" ]; then
  echo "Voltando para $anterior" >&2
  if subir "$anterior" && esperar_saude; then
    echo "Rollback concluído: $anterior está no ar de novo." >&2
  else
    echo "ATENÇÃO: o rollback também falhou. Olhe a VPS: docker compose -f compose.yaml -f compose.vps.yaml logs contador" >&2
  fi
fi
exit 1
