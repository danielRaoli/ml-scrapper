#!/bin/bash
set -e

if [ "${RUN_LOOP:-false}" = "true" ]; then
  INTERVAL="${LOOP_INTERVAL_SECONDS:-3600}"
  echo "[entrypoint] modo loop ativado - executando a cada ${INTERVAL}s"
  while true; do
    echo "[entrypoint] iniciando execucao: $(date -u +%FT%TZ)"
    python mercadolivre_scraper.py || echo "[entrypoint] execucao falhou, tentando novamente no proximo ciclo"
    echo "[entrypoint] aguardando ${INTERVAL}s ate a proxima execucao"
    sleep "$INTERVAL"
  done
else
  exec python mercadolivre_scraper.py
fi
