@echo off
title OMISTOCK - Tunnel HTTPS (ngrok)
color 0A

echo =======================================================
echo Lancement du Tunnel HTTPS avec ngrok
echo =======================================================
echo.
echo Veuillez patienter, ngrok va demarrer...
echo Cherchez la ligne "Forwarding" pour trouver votre lien https://
echo.

ngrok http --url=limeade-deviator-exit.ngrok-free.dev 8000

