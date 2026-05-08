# Assemble the bundled runtime tree for Windows x64. Run on a Windows
# machine with PowerShell 5.1+ (or pwsh) and git. Audiveris 5.10.2's
# build.gradle requires Java 25, so this script downloads a Temurin 25
# JDK into a temp dir and points JAVA_HOME there for the gradle build —
# you don't need a system JDK preinstalled.
#
# Output layout (matches frontend/src-tauri/src/main.rs env wiring):
#
#   frontend/src-tauri/resources/
#     runtime/
#       jre/                     <- Temurin 25 JRE (jlink-trimmed)
#       audiveris/               <- Audiveris install (built locally)
#       tessdata/                <- Tesseract language packs
#     tesseract/
#       tesseract.exe            <- Tesseract binary (UB Mannheim build)
#
# Prerequisites:
#     winget install Git.Git
#     winget install UB-Mannheim.TesseractOCR
#
# Usage:
#     pwsh -File scripts/fetch_runtime_windows.ps1

[CmdletBinding()]
param(
    [string]$AudiverisRef = "5.10.2",
    [string]$JreFeature = "25"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"  # speeds up Invoke-WebRequest a lot

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$res = Join-Path $root "frontend/src-tauri/resources"
$work = Join-Path ([System.IO.Path]::GetTempPath()) ("rt_" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $work -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $res "runtime") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $res "tesseract") -Force | Out-Null

try {
    # ---------------------------------------------------------------------
    # 1. Trimmed JRE via jlink.
    # ---------------------------------------------------------------------
    $jdkUrl = "https://api.adoptium.net/v3/binary/latest/$JreFeature/ga/windows/x64/jdk/hotspot/normal/eclipse"
    $jdkZip = Join-Path $work "jdk.zip"
    Write-Host "[runtime] fetching latest Temurin JDK $JreFeature GA"
    Invoke-WebRequest -Uri $jdkUrl -OutFile $jdkZip -MaximumRedirection 5
    Expand-Archive -Path $jdkZip -DestinationPath (Join-Path $work "jdk") -Force
    $jdkHome = (Get-ChildItem -Path (Join-Path $work "jdk") -Directory | Select-Object -First 1).FullName
    if (-not (Test-Path (Join-Path $jdkHome "bin/jlink.exe"))) {
        throw "jlink.exe not found under $jdkHome"
    }

    Write-Host "[runtime] running jlink (JDK_HOME=$jdkHome)"
    $jreOut = Join-Path $res "runtime/jre"
    if (Test-Path $jreOut) { Remove-Item -Recurse -Force $jreOut }
    $jlinkArgs = @(
        "--module-path", (Join-Path $jdkHome "jmods"),
        "--add-modules", "java.base,java.desktop,java.logging,java.sql,java.xml,jdk.unsupported,jdk.crypto.ec,jdk.localedata",
        "--include-locales=en,ja",
        "--no-header-files",
        "--no-man-pages",
        "--strip-debug",
        "--compress=zip-6",
        "--output", $jreOut
    )
    & (Join-Path $jdkHome "bin/jlink.exe") @jlinkArgs

    # ---------------------------------------------------------------------
    # 2. Audiveris from source. gradlew installDist produces a portable
    #    install tree under build/install/audiveris-app/.
    # ---------------------------------------------------------------------
    $aud = Join-Path $work "audiveris"
    Write-Host "[runtime] cloning + building Audiveris @ $AudiverisRef"
    git clone --depth 1 --branch $AudiverisRef https://github.com/Audiveris/audiveris.git $aud

    Push-Location $aud
    try {
        $env:JAVA_HOME = $jdkHome
        & .\gradlew.bat --no-daemon installDist
        if ($LASTEXITCODE -ne 0) { throw "gradlew installDist failed: $LASTEXITCODE" }
    } finally {
        Pop-Location
    }

    $installDir = Get-ChildItem -Path (Join-Path $aud "build/install") -Directory | Select-Object -First 1
    if (-not $installDir -or -not (Test-Path (Join-Path $installDir.FullName "bin/Audiveris.bat"))) {
        throw "Audiveris install layout not found after gradlew installDist."
    }
    $audOut = Join-Path $res "runtime/audiveris"
    if (Test-Path $audOut) { Remove-Item -Recurse -Force $audOut }
    Copy-Item -Recurse -Path $installDir.FullName -Destination $audOut

    # ---------------------------------------------------------------------
    # 3. Tesseract: copy the UB Mannheim install (or whatever is on PATH).
    # ---------------------------------------------------------------------
    Write-Host "[runtime] copying tesseract"
    $tessExe = (Get-Command tesseract.exe -ErrorAction SilentlyContinue).Path
    if (-not $tessExe) {
        $candidate = "C:\Program Files\Tesseract-OCR\tesseract.exe"
        if (Test-Path $candidate) { $tessExe = $candidate }
    }
    if (-not $tessExe) {
        throw "tesseract.exe not found. Install via 'winget install UB-Mannheim.TesseractOCR'."
    }
    Copy-Item -Path $tessExe -Destination (Join-Path $res "tesseract/tesseract.exe") -Force

    $tessdataOut = Join-Path $res "runtime/tessdata"
    New-Item -ItemType Directory -Path $tessdataOut -Force | Out-Null
    $tessdataSrc = Join-Path (Split-Path -Parent $tessExe) "tessdata"
    foreach ($lang in @("eng", "ita")) {
        $f = Join-Path $tessdataSrc "$lang.traineddata"
        if (Test-Path $f) {
            Copy-Item -Path $f -Destination $tessdataOut -Force
        } else {
            Write-Warning "$lang.traineddata not found under $tessdataSrc"
        }
    }

    Write-Host "[runtime] done. Layout:"
    Get-ChildItem -Recurse -Directory -Depth 2 $res | Select-Object -ExpandProperty FullName
} finally {
    Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
}

# ---------------------------------------------------------------------------
# Notes on shipping a Windows bundle:
# * tesseract.exe from UB Mannheim depends on leptonica DLLs that live in
#   the same directory. If extending this script to a fully-portable copy,
#   include leptonica.dll alongside tesseract.exe and verify with
#   `Get-ChildItem "C:\Program Files\Tesseract-OCR\*.dll"`.
# * For SmartScreen, sign accompanist-server.exe (PyInstaller output) and
#   the Tauri-produced .msi/.exe with an EV or OV Authenticode certificate.
