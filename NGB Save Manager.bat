@echo off
chcp 65001 >nul
where python >nul 2>nul && (python "%~dp0ngb_save_manager.py" %* & goto :end)
where py >nul 2>nul && (py "%~dp0ngb_save_manager.py" %* & goto :end)
echo 没有找到 Python，请先安装 Python 3（python.org，安装时勾选 Add to PATH）。
echo Python not found. Please install Python 3 from python.org and tick "Add to PATH" during setup.
pause
:end
if errorlevel 1 pause
