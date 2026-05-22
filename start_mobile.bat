@echo off
title OMISTOCK Mobile Launcher
echo Lancement de l'application mobile OMISTOCK sur le PC...
echo.
echo Le navigateur va s'ouvrir sur l'adresse locale securisee (http://localhost:8000).
echo En passant par localhost, le navigateur autorisera l'ouverture de la camera 
echo meme sans HTTPS.
echo.
echo Patientez...
timeout /t 2 >nul
start http://localhost:8000/app/app_mobile.html
exit

