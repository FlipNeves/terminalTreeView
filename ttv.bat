@echo off
for /f "delims=" %%i in ('python src\terminaltreeview\app.py') do set "NEW_DIR=%%i"
if defined NEW_DIR (
    if exist "%NEW_DIR%" (
        cd /d "%NEW_DIR%"
    )
)
set "NEW_DIR="
