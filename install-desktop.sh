#!/usr/bin/env bash
# ==============================================================================
# Instala os atalhos do GorilaTrader (terminal e web) no menu de aplicativos
# do Linux (funciona em qualquer desktop compatível com freedesktop.org - Pop!_OS/
# COSMIC, GNOME, KDE, etc). Resolve os caminhos automaticamente a partir de onde
# o projeto está clonado, então funciona em qualquer máquina/usuário.
# ==============================================================================

set -e
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
APPS_DIR="$HOME/.local/share/applications"
ICONS_DIR="$HOME/.local/share/icons"
ICON_PATH="$ICONS_DIR/gorilatrader.png"

mkdir -p "$APPS_DIR" "$ICONS_DIR"
cp "$PROJECT_DIR/gorilatrader.png" "$ICON_PATH"

for name in gorilatrader gorilatrader-web; do
    sed \
        -e "s#__PROJECT_DIR__#${PROJECT_DIR}#g" \
        -e "s#__ICON_PATH__#${ICON_PATH}#g" \
        "$PROJECT_DIR/desktop/${name}.desktop.template" > "$APPS_DIR/${name}.desktop"
    chmod +x "$PROJECT_DIR/run.sh" "$PROJECT_DIR/run-web.sh" 2>/dev/null || true
    echo "✅ Instalado: $APPS_DIR/${name}.desktop"
done

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPS_DIR" 2>/dev/null || true
fi

echo
echo "🦍 Pronto! Procure por 'GorilaTrader' e 'GorilaTrader Web' no menu de aplicativos."
