@echo off
chcp 65001 >nul
title Gestion fournisseurs - demonstration
cd /d "%~dp0backend"
where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo Python n'est pas installe. Installez-le depuis https://www.python.org/downloads/
  echo IMPORTANT : cochez la case "Add python.exe to PATH" pendant l'installation.
  pause
  exit /b 1
)
if not exist .venv (
  echo Premiere installation : preparation de l'environnement ^(quelques minutes^)...
  python -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
if not exist .secret_key python -c "import secrets;print(secrets.token_urlsafe(48))" > .secret_key
set /p AP_SECRET_KEY=<.secret_key
python manage.py migrate
python manage.py demo
echo.
echo ============================================================
echo  Logiciel demarre : http://localhost:8000
echo  Connexion : daf@demo.tn  /  mot de passe : Demo2026pass
echo  Pour arreter : fermez cette fenetre.
echo ============================================================
start "" http://localhost:8000
python -m uvicorn app.main:app --port 8000
pause
