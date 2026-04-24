# Convenience wrappers around `docker compose`. Not required — the raw
# commands are in the README — but these save typing.

.PHONY: help build up down start stop restart logs ps shell db-shell psql \
        smoketest backup promote-admin reset-db

help:  ## Show this help
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build:          ## Rebuild the web image
	docker compose build --pull

up:             ## Start the whole stack in the background
	docker compose up -d

down:           ## Stop and remove containers (volumes preserved)
	docker compose down

start:          ## Start previously-stopped containers
	docker compose start

stop:           ## Stop containers without removing them
	docker compose stop

restart:        ## Restart the web service only
	docker compose restart web

logs:           ## Tail logs from all services
	docker compose logs -f --tail=100

ps:             ## Show container status
	docker compose ps

shell:          ## Open a shell inside the web container
	docker compose exec web bash

db-shell:       ## Open a shell inside the db container
	docker compose exec db bash

psql:           ## Open a psql prompt on the running database
	docker compose exec db psql -U $${DB_USER:-nielit} $${DB_NAME:-nielit_community}

smoketest:      ## Run the in-process route test (uses a temp SQLite DB)
	docker compose exec web env DATABASE_URL=sqlite:////tmp/smoketest.db \
	    python scripts/smoketest.py

backup:         ## Dump the db to ./backups/<timestamp>.sql.gz
	bash scripts/backup-db.sh

promote-admin:  ## Promote a user to admin (prompts for username/email)
	docker compose exec web flask promote-admin

reset-db:       ## DANGER: drop and recreate the database (all data gone)
	docker compose down
	docker volume rm $$(basename $$(pwd) | tr '[:upper:]' '[:lower:]')_postgres_data || true
	docker compose up -d
