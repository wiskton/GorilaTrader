#!/usr/bin/env bash
# ==============================================================================
# GorilaTrader - Monitor Quantitativo Cripto (Gráfico 1h)
# Inicia o GorilaTrader no terminal
# ==============================================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

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

# Executa o GorilaTrader
exec python3 gorilatrader.py "$@"
