# 打包脚本：生成免安装的 Trans.exe（无控制台窗口）。
# 前置条件：pip install pyinstaller
#
# 用法（在仓库根目录执行）：
#   powershell -ExecutionPolicy Bypass -File .\build.ps1

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

Push-Location $root
try {
    python -m PyInstaller `
        --noconfirm `
        --clean `
        --windowed `
        --onedir `
        --name Trans `
        --icon "$root\assets\icon.ico" `
        --add-data "$root\assets;assets" `
        "$root\Trans.pyw"

    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 打包失败，退出码 $LASTEXITCODE" }
    Write-Host "打包完成：$root\dist\Trans\Trans.exe"
}
finally {
    Pop-Location
}
