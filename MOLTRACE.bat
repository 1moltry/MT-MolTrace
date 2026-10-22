@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

rem MOLTRACE launcher.
rem First run: create .venv and install dependencies, then start the GUI.
rem Later runs: start directly. If pyproject.toml changed, reinstall first.
rem Run "MOLTRACE.bat debug" (or MOLTRACE-debug.bat) to keep the console open.

set "VENV_PY=.venv\Scripts\python.exe"
set "VENV_PYW=.venv\Scripts\pythonw.exe"

if not exist "%VENV_PY%" goto create_env
goto check_env

:create_env
echo.
echo [MOLTRACE] 首次运行，正在创建运行环境……
where python >nul 2>nul
if errorlevel 1 goto no_python
python -m venv .venv
if errorlevel 1 goto venv_failed
echo [MOLTRACE] 正在安装依赖，约 200 MB。首次需要 5～15 分钟，请保持网络畅通。
call :install
if errorlevel 1 goto pip_failed
goto mark_ready

:check_env
"%VENV_PY%" -c "import os,sys;sys.exit(0 if os.path.exists('.venv/.moltrace-ready') and os.path.getmtime('.venv/.moltrace-ready')>=os.path.getmtime('pyproject.toml') else 1)"
if errorlevel 1 (
    echo [MOLTRACE] 检测到依赖有更新，正在重新安装……
    call :install
    if errorlevel 1 goto pip_failed
    goto mark_ready
)
goto launch

:install
"%VENV_PY%" -m pip install --disable-pip-version-check -e ".[gui]"
if not errorlevel 1 exit /b 0
echo [MOLTRACE] 默认源失败，改用清华镜像重试一次……
"%VENV_PY%" -m pip install --disable-pip-version-check -e ".[gui]" -i https://pypi.tuna.tsinghua.edu.cn/simple
exit /b %errorlevel%

:mark_ready
> ".venv\.moltrace-ready" echo ok
goto launch

:launch
if /i "%~1"=="debug" (
    echo [MOLTRACE] 启动中。关闭窗口即退出程序。
    "%VENV_PY%" -m nanopore gui
    echo.
    echo [MOLTRACE] 程序已退出，退出码 %errorlevel%。
    pause
    exit /b 0
)
start "" "%VENV_PYW%" -m nanopore gui
exit /b 0

:no_python
echo.
echo [错误] 没有找到 Python。
echo 请安装 Python 3.11 或更高版本：https://www.python.org/downloads/
echo 安装时务必勾选 "Add python.exe to PATH"，装完再双击本文件。
echo.
pause
exit /b 1

:venv_failed
echo.
echo [错误] 创建运行环境失败。请确认 Python 版本不低于 3.11，然后重试。
echo.
pause
exit /b 1

:pip_failed
echo.
echo [错误] 依赖安装失败，通常是网络问题。
echo 请检查网络后重新双击本文件；脚本会自动改用清华镜像重试。
echo 若仍失败，双击 MOLTRACE-debug.bat 查看完整报错。
echo.
pause
exit /b 1
