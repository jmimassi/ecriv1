#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$SCRIPT_DIR/.venv"
DESKTOP_FILE="$HOME/.config/autostart/ecriv1.desktop"

echo "=== ecriv1 — Installation ==="
echo ""

# 1. System dependencies
echo "[1/3] Installing system packages..."
sudo apt install -y xclip xdotool python3-venv python3-gi gir1.2-appindicator3-0.1 libportaudio2

# 2. Virtual environment + Python dependencies
echo ""
echo "[2/3] Creating venv and installing Python dependencies..."
python3 -m venv "$VENV" --system-site-packages
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"

# 3. Desktop entry (autostart + launcher)
echo ""
echo "[3/3] Setting up autostart..."
mkdir -p "$HOME/.config/autostart"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=ecriv1
Comment=Voice-to-text widget (French)
Exec=$VENV/bin/python3 $SCRIPT_DIR/ecriv1.py
Icon=$SCRIPT_DIR/icons/mic-off.svg
Terminal=false
Categories=Utility;Accessibility;
StartupNotify=false
X-GNOME-Autostart-enabled=true
EOF

echo ""
echo "=== Installation complete ==="
echo ""
echo "The app will start automatically on each login."
echo "To launch now: $VENV/bin/python3 $SCRIPT_DIR/ecriv1.py &"
