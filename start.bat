@echo off
chcp 65001 >nul
title OMISTOCK - Lancement Systeme
color 0A

echo.
echo  ██████╗ ███╗   ███╗██╗███████╗████████╗ ██████╗  ██████╗██╗  ██╗
echo  ██╔═══██╗████╗ ████║██║██╔════╝╚══██╔══╝██╔═══██╗██╔════╝██║ ██╔╝
echo  ██║   ██║██╔████╔██║██║███████╗   ██║   ██║   ██║██║     █████╔╝
echo  ██║   ██║██║╚██╔╝██║██║╚════██║   ██║   ██║   ██║██║     ██╔═██╗
echo  ╚██████╔╝██║ ╚═╝ ██║██║███████║   ██║   ╚██████╔╝╚██████╗██║  ██╗
echo   ╚═════╝ ╚═╝     ╚═╝╚═╝╚══════╝   ╚═╝    ╚═════╝  ╚═════╝╚═╝  ╚═╝
echo.
echo  =========================================================
echo   OMISTOCK ERP  ^|  Lancement de tous les services...
echo  =========================================================
echo.

:: ---- Verification Python ----
echo  [1/4] Verification de Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERREUR] Python n'est pas installe ou pas dans le PATH.
    pause
    exit /b
)
echo  [OK] Python detecte.
echo.

:: ---- Verification et installation des dependances ----
echo  [2/4] Verification des dependances (requirements.txt)...
pip install -r backend\requirements.txt -q --no-warn-script-location
if %errorlevel% neq 0 (
    echo  [ERREUR] Impossible d'installer les dependances. Verifiez votre connexion.
    pause
    exit /b
)
echo  [OK] Dependances a jour.
echo.

:: ---- Recuperer la cle API Agent depuis la BDD (ou utiliser la valeur par defaut) ----
echo  [3/4] Configuration de l'authentification MCP Agent...
:: On génère une clé dynamique en interrogeant la BDD via Python
for /f "tokens=*" %%i in ('python -c "import sys; sys.path.insert(0, \"backend\"); from database import SessionLocal; from models import User; db = SessionLocal(); agent = db.query(User).filter(User.user_type==\"AGENT\", User.api_key != None).first(); print(agent.api_key if agent and agent.api_key else \"NO_KEY\")"  2^>nul') do (
    set AGENT_API_KEY=%%i
)

if "%AGENT_API_KEY%"=="NO_KEY" (
    echo  [INFO] Aucun agent configure dans la BDD. Le MCP fonctionnera sans cle.
    echo         Allez dans l'application et creez un Agent pour activer l'auth.
    set AGENT_API_KEY=
) else (
    echo  [OK] Cle API Agent chargee depuis la base de donnees.
)
echo.

:: ---- Lancement des services ----
echo  [4/4] Demarrage des services...
echo.

echo  --- Lancement du Serveur FastAPI (Backend API)...
start "OMISTOCK - Backend API :8000" cmd /k "chcp 65001 >nul && color 0B && echo. && echo  [BACKEND] FastAPI - http://localhost:8000 && echo  [BACKEND] Docs   - http://localhost:8000/docs && echo  [BACKEND] App    - http://localhost:8000/app && echo. && python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000"

:: Attendre que l'API soit prête avant de lancer le MCP
echo  [INFO] Attente du demarrage de l'API (5 secondes)...
ping -n 6 127.0.0.1 >nul

echo  --- Lancement du Serveur MCP (Agent IA)...
start "OMISTOCK - MCP Agent IA" cmd /k "chcp 65001 >nul && color 0E && echo. && echo  [MCP] Serveur Agent IA - En ecoute (stdio) && echo  [MCP] API cible : http://localhost:8000 && echo  [MCP] Cle Agent : %AGENT_API_KEY:~0,8%... && echo. && set AGENT_API_KEY=%AGENT_API_KEY% && set API_BASE_URL=http://localhost:8000 && cd mcp && python server.py"

echo.
echo  =========================================================
echo   OMISTOCK est demarre avec succes !
echo  =========================================================
echo.
echo   Application Web  : http://localhost:8000/app
echo   API REST         : http://localhost:8000
echo   Documentation    : http://localhost:8000/docs
echo.
echo   Deux fenetres de console sont ouvertes :
echo    - Bleue  : Backend FastAPI
echo    - Jaune  : Serveur MCP (Agent IA)
echo.
echo   Fermez cette fenetre ou appuyez sur une touche pour quitter.
pause >nul

