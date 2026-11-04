#!/usr/bin/env bash
set -e

VERSION="2.1.0"
PKG_NAME="android-connect_${VERSION}_all"
STAGING_DIR="/tmp/${PKG_NAME}"

echo "==> Preparando diretorio temporario de empacotamento..."
rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"

cp -r DEBIAN "$STAGING_DIR/"
cp -r usr "$STAGING_DIR/"

# Permissoes padrao Debian
find "$STAGING_DIR" -type d -exec chmod 755 {} +
find "$STAGING_DIR" -type f -exec chmod 644 {} +
chmod 755 "$STAGING_DIR/DEBIAN/postinst" "$STAGING_DIR/DEBIAN/prerm"
chmod 755 "$STAGING_DIR/usr/bin/android-connect"
chmod 755 "$STAGING_DIR/usr/share/android-connect/main.py"

echo "==> Compilando pacote .deb..."
dpkg-deb --root-owner-group --build "$STAGING_DIR" "./${PKG_NAME}.deb"

echo "[OK] Pacote compilado com sucesso: ./${PKG_NAME}.deb"
