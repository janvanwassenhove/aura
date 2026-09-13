@echo off
rem ============================================================
rem  AURA - easy start (broncheckout)
rem  Dubbelklik om de desktop-app te starten (brain + console).
rem  Synct de Python-omgeving, herbouwt de console als die
rem  achterloopt, en start de Electron-shell.
rem ============================================================
setlocal enabledelayedexpansion
title AURA starten...
cd /d "%~dp0"

where uv >nul 2>nul || (
  echo [FOUT] 'uv' niet gevonden. Installeer eerst: https://docs.astral.sh/uv/
  pause & exit /b 1
)
where npm >nul 2>nul || (
  echo [FOUT] 'npm' niet gevonden. Installeer eerst Node 20+: https://nodejs.org/
  pause & exit /b 1
)

rem --- Python-omgeving ---------------------------------------------------
rem De bootstrap in de Electron-shell is packaged-only ("if (!IS_PACKAGED)
rem return" in apps\desktop\main.cjs), dus een checkout synct zelf. Zonder de
rem extras erbij snoeit uv sync ze weg: recognition (gezichten), computeruse
rem (pyautogui) en presentation (pywin32/dia-detectie). Dezelfde ladder als de
rem bootstrap, zodat een wheel die hier niet bouwt de rest niet meesleurt.
rem 3.11 omdat CI alleen dat draait; requires-python laat ook 3.14 toe en daar
rem stierf de brain al eens voor zijn eerste regel werk (U332).
echo Python-omgeving synchroniseren...
set "SYNCED="
for %%X in (
  "--extra recognition --extra computeruse --extra presentation"
  "--extra recognition --extra presentation"
  "--extra presentation"
  " "
) do (
  if not defined SYNCED (
    uv sync --all-packages --python 3.11 %%~X && set "SYNCED=1"
  )
)
if not defined SYNCED (
  echo [FOUT] 'uv sync' mislukt - zie de uitvoer hierboven.
  pause & exit /b 1
)

rem --- console: bouwen zodra de bron verschilt van wat er in dist ligt ----
rem Afgaan op het bestaan van dist\index.html liet na elke pull een oude console
rem draaien tegen een nieuwe brain. De boomhash van de consolemap verandert
rem precies wanneer er aan de console iets veranderd is.
set "CONSOLE_REV="
for /f %%H in ('git rev-parse HEAD:apps/operator-console 2^>nul') do set "CONSOLE_REV=%%H"
set "BUILT_REV="
if exist apps\operator-console\dist\.built-from set /p BUILT_REV=<apps\operator-console\dist\.built-from
if not exist apps\operator-console\dist\index.html set "BUILT_REV=none"
if "!CONSOLE_REV!"=="" set "BUILT_REV=none"

if not "!BUILT_REV!"=="!CONSOLE_REV!" (
  echo Console bouwen...
  pushd apps\operator-console
  if not exist node_modules call npm install || (echo [FOUT] npm install console mislukt & popd & pause & exit /b 1)
  rem Geen VITE_*-variabelen meer: de shell injecteert window.__AURA_RUNTIME__ met
  rem de poorten die hij echt kreeg, en dat wint van elke ingebakken waarde (U234).
  call npm run build || (echo [FOUT] console build mislukt & popd & pause & exit /b 1)
  popd
  if "!CONSOLE_REV!"=="" (
    del apps\operator-console\dist\.built-from >nul 2>nul
  ) else (
    rem Omleiding vooraan: een hash die op een cijfer eindigt zou anders als
    rem streamnummer gelezen worden ("...9>bestand" is stream 9).
    >apps\operator-console\dist\.built-from echo !CONSOLE_REV!
  )
)

rem --- desktop-app: dependencies (alleen eerste keer) ---
if not exist apps\desktop\node_modules\electron\dist\electron.exe (
  echo Desktop-app installeren ^(eenmalig^)...
  pushd apps\desktop
  call npm install || (echo [FOUT] npm install desktop mislukt & popd & pause & exit /b 1)
  popd
)

echo AURA start... ^(dit venster sluit vanzelf^)
rem electron.exe direct aanroepen - de .bin\electron.cmd shim start niet via 'start'
start "" "%~dp0apps\desktop\node_modules\electron\dist\electron.exe" "%~dp0apps\desktop"
exit /b 0
