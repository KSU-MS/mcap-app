.PHONY: dev-up dev-down dev-logs prod-up prod-down prod-logs prod-config

dev-up:
	docker compose -f compose.dev.yml up -d

dev-down:
	docker compose -f compose.dev.yml down

dev-logs:
	docker compose -f compose.dev.yml logs -f

prod-up:
	docker compose -f compose.prod.yml up -d --build

prod-down:
	docker compose -f compose.prod.yml down

prod-logs:
	docker compose -f compose.prod.yml logs -f

prod-config:
	docker compose -f compose.prod.yml config
