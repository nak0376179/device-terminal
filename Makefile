.PHONY: help install install-device install-backend install-frontend install-root \
        dev dev-device dev-backend dev-frontend \
        dev-local init-local stop-local clean

CONCURRENTLY := ./node_modules/.bin/concurrently

help: ## このヘルプを表示
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: install-device install-backend install-frontend install-root ## 全依存をインストール

install-device: ## device/ の依存を uv で同期
	cd device && uv sync

install-backend: ## backend/ の依存 (dev 含む) を uv で同期
	cd backend && uv sync

install-frontend: ## frontend/ の依存をインストール
	cd frontend && npm install

install-root: ## ルートの依存 (concurrently) をインストール
	npm install

dev: ## device, backend, frontend を同時起動 (Ctrl+C で全停止)
	@test -x $(CONCURRENTLY) || { echo "First run: make install-root"; exit 1; }
	@test -d device/.venv || { echo "First run: make install-device"; exit 1; }
	@test -d backend/.venv || { echo "First run: make install-backend"; exit 1; }
	@test -d frontend/node_modules || { echo "First run: make install-frontend"; exit 1; }
	@test -f device/config.json || { echo "First run: make init-local"; exit 1; }
	$(CONCURRENTLY) \
	  --names device,backend,frontend \
	  --prefix-colors blue,green,magenta \
	  --kill-others \
	  "cd device && exec uv run python device_agent.py" \
	  "cd backend && exec uv run uvicorn --app-dir app main:app --reload --port 9001" \
	  "cd frontend && exec npm run dev"

dev-device: ## device 単体起動
	cd device && uv run python device_agent.py

dev-backend: ## backend 単体起動
	cd backend && uv run uvicorn --app-dir app main:app --reload --port 9001

dev-frontend: ## frontend 単体起動
	cd frontend && npm run dev

dev-local: ## Floci 起動 → テーブル作成 → 全プロセス起動 (初回のみ init-local が自動実行)
	@test -x $(CONCURRENTLY) || { echo "First run: make install-root"; exit 1; }
	@test -d device/.venv || { echo "First run: make install-device"; exit 1; }
	@test -d backend/.venv || { echo "First run: make install-backend"; exit 1; }
	@test -d frontend/node_modules || { echo "First run: make install-frontend"; exit 1; }
	docker compose up -d
	@until aws --endpoint-url http://localhost:4566 --region ap-northeast-1 dynamodb list-tables >/dev/null 2>&1; do \
	  echo "  Waiting for Floci..."; sleep 0.5; done
	LOCALSTACK_ENDPOINT=http://localhost:4566 bash scripts/setup-floci.sh
	$(CONCURRENTLY) \
	  --names device,backend,frontend,init \
	  --prefix-colors blue,green,magenta,yellow \
	  --kill-others-on-fail \
	  "cd device && exec uv run python device_agent.py" \
	  "cd backend && LOCALSTACK_ENDPOINT=http://localhost:4566 exec uv run uvicorn --app-dir app main:app --reload --port 9001" \
	  "cd frontend && exec npm run dev" \
	  "LOCALSTACK_ENDPOINT=http://localhost:4566 BACKEND_URL=http://localhost:9001 bash scripts/init-local.sh"

init-local: ## ローカル開発用グループ・デバイスを初期化 (初回のみ必要)
	LOCALSTACK_ENDPOINT=http://localhost:4566 BACKEND_URL=http://localhost:9001 bash scripts/init-local.sh

stop-local: ## Floci を停止してデータを破棄
	docker compose down -v
	rm -f device/config.json

clean: ## venv, node_modules, ビルド成果物を削除
	rm -rf device/.venv backend/.venv
	rm -rf frontend/node_modules node_modules
	rm -rf frontend/dist
