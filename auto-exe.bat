@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

:: =============== 配置区 ===============
set "MAIN_SCRIPT=yt.py"
set "OUTPUT_NAME=猛兽派对钓鱼辅助"
set "VENV_NAME=fishing_venv"
set "ICON_FILE=vicksy.ico"

:: 必须存在的资源文件（空格分隔）
set "RESOURCES=star_template.png bucket_full.wav ouhuang.wav huiben.wav dawo.wav vicksy_fishing.png"

:: 是否显示控制台窗口（1=调试模式带黑窗，0=静默运行）
set "USE_CONSOLE=0"

:: =============== 开始构建 ===============
echo.
echo **********************************************
echo *     猛兽派对钓鱼辅助 - 自动打包工具 v1.1     *
echo **********************************************
echo.

echo [0/7] 当前目录: %CD%

:: 检查主脚本
if not exist "%MAIN_SCRIPT%" (
    echo [ERROR] 主脚本 "%MAIN_SCRIPT%" 未找到！
    pause
    exit /b 1
)

:: 检查图标文件
if not exist "%ICON_FILE%" (
    echo [ERROR] 图标文件 "%ICON_FILE%" 未找到！请提供 .ico 文件。
    pause
    exit /b 1
)

echo [1/7] 正在检查资源文件...
for %%f in (%RESOURCES%) do (
    if exist "%%f" (
        echo     [OK] %%f
    ) else (
        echo     [MISSING] %%f
        echo [ERROR] 资源文件缺失，打包无法继续。
        pause
        exit /b 1
    )
)

echo.
echo [2/7] 设置 Python 虚拟环境...
if not exist "%VENV_NAME%\Scripts\python.exe" (
    echo     创建虚拟环境: %VENV_NAME%
    python -m venv "%VENV_NAME%"
    if errorlevel 1 (
        echo [ERROR] 无法创建虚拟环境。请确认已安装 Python 并添加到 PATH。
        pause
        exit /b 1
    )
)
call "%VENV_NAME%\Scripts\activate.bat" >nul

echo [3/7] 升级 pip 并安装依赖...
pip install --upgrade pip -q
pip install opencv-python-headless mss numpy pygetwindow pypiwin32 keyboard pyautogui pyinstaller pillow -q
if errorlevel 1 (
    echo [ERROR] 依赖安装失败。
    pause
    exit /b 1
)

echo [4/7] 清理旧构建产物...
rmdir /s /q build dist "__pycache__" 2>nul
del /f /q "%OUTPUT_NAME%.spec" 2>nul

echo [5/7] 构建 PyInstaller 参数...

set "PYI_ARGS=--onefile --clean --icon=%ICON_FILE%"

if %USE_CONSOLE%==1 (
    set "PYI_ARGS=!PYI_ARGS! --console"
) else (
    set "PYI_ARGS=!PYI_ARGS! --windowed"
)

:: 添加所有资源文件（格式：源;目标目录）
for %%f in (%RESOURCES%) do (
    set "PYI_ARGS=!PYI_ARGS! --add-data "%%f;.""
)

:: 排除无用模块以减小体积
set "PYI_ARGS=%PYI_ARGS% --exclude-module matplotlib --exclude-module scipy --exclude-module IPython --exclude-module sklearn"

echo [6/7] 执行打包: "%OUTPUT_NAME%.exe"
pyinstaller %PYI_ARGS% --name "%OUTPUT_NAME%" "%MAIN_SCRIPT%"

if errorlevel 1 (
    echo.
    echo [ERROR] 打包失败！
    pause
    exit /b 1
)

echo.
echo **********************************************
echo *              打包成功！??                *
echo **********************************************
echo 输出文件: %CD%\dist\%OUTPUT_NAME%.exe

:: 自动打开 dist 文件夹
if exist "dist\" start "" "dist"

pause