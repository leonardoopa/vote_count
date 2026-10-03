-include .env
PORTA ?= 8000
export PORTA

.DEFAULT_GOAL := ajuda
.PHONY: ajuda web terminal teste up down logs

ajuda: ## lista os comandos
	@grep -E '^[a-z]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-9s %s\n", $$1, $$2}'

web: ## página web local, sem Docker (porta 8000 ou a do .env)
	python3 servidor.py --porta $(PORTA)

terminal: ## placar no terminal (presidente, Brasil)
	python3 contador.py

teste: ## roda os testes
	python3 -m unittest -v

up: ## sobe a página web no Docker
	docker compose up -d --build
	@echo "No ar: http://127.0.0.1:$(PORTA)"

down: ## para o Docker
	docker compose down

logs: ## acompanha os logs do Docker
	docker compose logs -f
