$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

Push-Location $Root
try {
    uv sync --group build
    uv run --group build python tools\create_windows_icon.py
    uv run --group build pyinstaller --noconfirm --clean --onefile --windowed `
        --name Snipaster `
        --icon assets\snipaster.ico `
        --add-data "assets\snipaster-icon.svg;assets" `
        snipaster.py

    $Candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    )
    $Iscc = $Candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $Iscc) {
        throw "Inno Setup 6 is required. Install it with: winget install JRSoftware.InnoSetup"
    }
    & $Iscc windows\Snipaster.iss
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup compilation failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
