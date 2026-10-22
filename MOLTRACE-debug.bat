@echo off
chcp 65001 >nul
rem MOLTRACE launcher, DEBUG version.
rem Same install logic as MOLTRACE.bat, but keeps the console open
rem so startup errors and Python tracebacks stay visible.

call "%~dp0MOLTRACE.bat" debug
