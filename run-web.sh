#!/usr/bin/env bash
# ==============================================================================
# GorilaTrader Web - Dashboard com gráfico profissional (Lightweight Charts)
# Sobe o servidor local e abre o navegador automaticamente
# ==============================================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PORT="${GORILATRADER_WEB_PORT:-8000}"
URL="http://127.0.0.1:${PORT}"

# Se executado fora de um terminal interativo (ex: clique direto pelo explorador),
# abre automaticamente no emulador de terminal padrão (COSMIC Terminal ou similar)
if [ ! -t 0 ] && [ ! -t 1 ] && [ -z "$GORILATRADER_IN_TERM" ]; then
    export GORILATRADER_IN_TERM=1
    if command -v cosmic-term >/dev/null 2>&1; then
        exec cosmic-term -w "$SCRIPT_DIR" -- "$0" "$@"
    elif command -v x-terminal-emulator >/dev/null 2>&1; then
        exec x-terminal-emulator -e "$0" "$@"
    elif command -v gnome-terminal >/dev/null 2>&1; then
        exec gnome-terminal -- "$0" "$@"
    elif command -v xterm >/dev/null 2>&1; then
        exec xterm -e "$0" "$@"
    fi
fi

echo "🦍 Iniciando GorilaTrader Web em $URL ..."
echo "   (feche esta janela ou pressione Ctrl+C para encerrar o servidor)"
echo

python3 gorilatrader.py --serve --port "$PORT" &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null' EXIT

# Aguarda o servidor responder antes de abrir o navegador
for _ in $(seq 1 40); do
    if curl -s -o /dev/null "$URL" 2>/dev/null; then
        break
    fi
    sleep 0.5
done

if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" >/dev/null 2>&1 &
fi

wait "$SERVER_PID"
