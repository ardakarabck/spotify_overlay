@echo off
rem Double-click launcher for the overlay helper.
rem
rem Runs helper.py from this file's own folder, so it works from a desktop
rem shortcut as well as from the project directory. Any arguments are passed
rem straight through, which means a shortcut can carry --reauth or --port.
rem
rem The window stays open after the helper stops, so a startup error is
rem readable instead of vanishing with the console.

setlocal
title Spotify Overlay Helper
cd /d "%~dp0"

python helper.py %*
rem 9009 is cmd's "command not found" - fall back to the py launcher, which is
rem what a Microsoft Store install of Python usually leaves on PATH.
if errorlevel 9009 goto trypy
goto done

:trypy
echo.
echo "python" was not found on PATH. Trying the py launcher instead.
echo.
py helper.py %*

:done
echo.
echo Helper stopped. Press any key to close this window.
pause >nul
