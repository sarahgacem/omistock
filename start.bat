@echo off
echo ==========================================
echo    LANCEMENT DU SERVEUR OMISTOCK ERP
echo ==========================================
echo.
echo [1/2] Verification de l'environnement...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERREUR: Python n'est pas installe ou pas dans le PATH.
    pause
    exit /b
)

echo [2/2] Demarrage de FastAPI sur http://localhost:8000...
echo (Utilisez Ctrl+C pour arreter le serveur)
echo.
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
pause
