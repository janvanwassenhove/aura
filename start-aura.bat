@echo off
rem ============================================================
rem  AURA - easy start
rem  Dubbelklik om de desktop-app te starten (brain + console).
rem  Eerste keer: installeert dependencies en bouwt de console.
rem ============================================================
setlocal
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

rem --- console: dependencies + build (alleen als die er nog niet is) ---
if not exist apps\operator-console\dist\index.html (
  echo Console bouwen ^(eenmalig^)...
  pushd apps\operator-console
  if not exist node_modules call npm install || (echo [FOUT] npm install console mislukt & pause & exit /b 1)
  set "VITE_ROBOT_RUNTIME_WS=ws://localhost:8020/ws/events"
  set "VITE_ORCHESTRATOR_URL=http://localhost:8020"
  set "VITE_BRAIN_URL=http://localhost:8020"
  set "VITE_CONVERSATION_URL=http://localhost:8020"
  set "VITE_IDENTITY_URL=http://localhost:8020"
  set "VITE_CONNECTOR_URL=http://localhost:8020"
  call npm run build || (echo [FOUT] console build mislukt & pause & exit /b 1)
  popd
)

rem --- desktop-app: dependencies (alleen eerste keer) ---
if not exist apps\desktop\node_modules\electron\dist\electron.exe (
  echo Desktop-app installeren ^(eenmalig^)...
  pushd apps\desktop
  call npm install || (echo [FOUT] npm install desktop mislukt & pause & exit /b 1)
  popd
)

echo AURA start... ^(dit venster sluit vanzelf^)
rem electron.exe direct aanroepen - de .bin\electron.cmd shim start niet via 'start'
start "" "%~dp0apps\desktop\node_modules\electron\dist\electron.exe" "%~dp0apps\desktop"
exit /b 0
