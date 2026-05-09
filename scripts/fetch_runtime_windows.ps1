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
#       tessdata/                <- Tesseract language packs (eng, ita)
#       tesseract/
#         bin/
#           tesseract.exe        <- UB Mannheim build
#           *.dll                <- libtesseract / libleptonica / runtime DLLs
#       poppler/
#         bin/
#           pdftoppm.exe, pdfinfo.exe, ...
#           *.dll                <- transitive deps shipped by oschwartz10612
#
# Every binary tree above is fully self-contained — Windows resolves
# DLLs from the .exe's own directory first, so co-locating the DLLs
# alongside each .exe is enough. The end user does not need Tesseract
# or Poppler on their PATH.
#
# Prerequisites on the build machine:
#     winget install Git.Git
#     winget install UB-Mannheim.TesseractOCR
#
# Usage:
#     pwsh -File scripts/fetch_runtime_windows.ps1

[CmdletBinding()]
param(
    [string]$AudiverisRef = "5.10.2",
    [string]$JreFeature = "25",
    # Pin the poppler-windows release. Override only when bumping. The
    # default tracks oschwartz10612/poppler-windows; that project ships
    # MSYS2 mingw64 builds with all DLLs co-located under Library/bin/.
    [string]$PopplerRelease = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"  # speeds up Invoke-WebRequest a lot

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$res = Join-Path $root "frontend/src-tauri/resources"
$work = Join-Path ([System.IO.Path]::GetTempPath()) ("rt_" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $work -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $res "runtime") -Force | Out-Null

# Old layout: a flat resources/tesseract/tesseract.exe sat next to
# runtime/. The new self-contained layout puts everything under
# runtime/tesseract/bin/, so wipe the legacy directory to avoid
# shipping stale DLLs alongside the new tree.
$legacyTess = Join-Path $res "tesseract"
if (Test-Path $legacyTess) {
    Remove-Item -Recurse -Force $legacyTess
}

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
        "--add-modules", "java.base,java.desktop,java.logging,java.management,java.naming,java.prefs,java.scripting,java.security.jgss,java.sql,java.xml,jdk.crypto.ec,jdk.localedata,jdk.unsupported,jdk.zipfs",
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
    # 3. Tesseract: bundle the UB Mannheim install (tesseract.exe + every
    #    sibling DLL). UB Mannheim ships a self-contained build where
    #    libtesseract*.dll, libleptonica*.dll, libstdc++-6.dll, libgcc*,
    #    libpng/libtiff/libjpeg/libwebp/etc. all live next to the .exe.
    #    Co-locating them under runtime/tesseract/bin/ is enough — Windows
    #    resolves DLLs from the .exe's directory first.
    # ---------------------------------------------------------------------
    Write-Host "[runtime] bundling tesseract"
    $tessExe = (Get-Command tesseract.exe -ErrorAction SilentlyContinue).Path
    if (-not $tessExe) {
        $candidate = "C:\Program Files\Tesseract-OCR\tesseract.exe"
        if (Test-Path $candidate) { $tessExe = $candidate }
    }
    if (-not $tessExe) {
        throw "tesseract.exe not found. Install via 'winget install UB-Mannheim.TesseractOCR'."
    }
    $tessSrcDir = Split-Path -Parent $tessExe

    $tessBinOut = Join-Path $res "runtime/tesseract/bin"
    if (Test-Path (Join-Path $res "runtime/tesseract")) {
        Remove-Item -Recurse -Force (Join-Path $res "runtime/tesseract")
    }
    New-Item -ItemType Directory -Force -Path $tessBinOut | Out-Null
    # Top-level files only (skip the tessdata/ subdir; that lands at
    # runtime/tessdata/ below).
    Get-ChildItem -Path $tessSrcDir -File | Copy-Item -Destination $tessBinOut -Force
    Write-Host ("[runtime] tesseract: {0} files in {1}" -f (Get-ChildItem $tessBinOut -File).Count, $tessBinOut)

    $tessdataOut = Join-Path $res "runtime/tessdata"
    if (Test-Path $tessdataOut) { Remove-Item -Recurse -Force $tessdataOut }
    New-Item -ItemType Directory -Path $tessdataOut -Force | Out-Null
    $tessdataSrc = Join-Path $tessSrcDir "tessdata"
    foreach ($lang in @("eng", "ita")) {
        $f = Join-Path $tessdataSrc "$lang.traineddata"
        if (Test-Path $f) {
            Copy-Item -Path $f -Destination $tessdataOut -Force
        } else {
            Write-Warning "$lang.traineddata not found under $tessdataSrc"
        }
    }

    # ---------------------------------------------------------------------
    # 4. Poppler: download a release of oschwartz10612/poppler-windows
    #    and extract its Library/bin/ tree (which contains pdftoppm.exe,
    #    pdfinfo.exe, pdftocairo.exe, pdfseparate.exe, pdfunite.exe and
    #    every required DLL) into runtime/poppler/bin/.
    # ---------------------------------------------------------------------
    Write-Host "[runtime] bundling poppler"
    if (-not $PopplerRelease) {
        $relApi = Invoke-RestMethod "https://api.github.com/repos/oschwartz10612/poppler-windows/releases/latest"
        $asset = $relApi.assets | Where-Object { $_.name -like "Release-*.zip" } | Select-Object -First 1
        if (-not $asset) {
            throw "could not locate Release-*.zip asset on poppler-windows latest release"
        }
        $popplerUrl = $asset.browser_download_url
        Write-Host ("[runtime] poppler release: {0}" -f $relApi.tag_name)
    } else {
        $popplerUrl = "https://github.com/oschwartz10612/poppler-windows/releases/download/$PopplerRelease/Release-$($PopplerRelease.TrimStart('v')).zip"
    }
    $popZip = Join-Path $work "poppler.zip"
    $popExtract = Join-Path $work "poppler"
    Invoke-WebRequest -Uri $popplerUrl -OutFile $popZip -MaximumRedirection 5
    Expand-Archive -Path $popZip -DestinationPath $popExtract -Force

    # The release zip extracts to either <root>/Library/bin/ or
    # <root>/poppler-<ver>/Library/bin/ depending on the version. Find
    # whichever contains pdftoppm.exe.
    $popBinSrc = Get-ChildItem -Path $popExtract -Recurse -Filter "pdftoppm.exe" -File `
        | Select-Object -First 1 `
        | ForEach-Object { Split-Path -Parent $_.FullName }
    if (-not $popBinSrc) {
        throw "pdftoppm.exe not found inside poppler release zip ($popplerUrl)"
    }

    $popBinOut = Join-Path $res "runtime/poppler/bin"
    if (Test-Path (Join-Path $res "runtime/poppler")) {
        Remove-Item -Recurse -Force (Join-Path $res "runtime/poppler")
    }
    New-Item -ItemType Directory -Force -Path $popBinOut | Out-Null
    Get-ChildItem -Path $popBinSrc -File | Copy-Item -Destination $popBinOut -Force
    Write-Host ("[runtime] poppler: {0} files in {1}" -f (Get-ChildItem $popBinOut -File).Count, $popBinOut)

    Write-Host "[runtime] done. Layout:"
    Get-ChildItem -Recurse -Directory -Depth 2 $res | Select-Object -ExpandProperty FullName
} finally {
    Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
}

# ---------------------------------------------------------------------------
# Notes on shipping a Windows bundle:
# * Every binary tree under runtime/ is fully self-contained:
#     - runtime/jre        : jlink-built, JVM-internal DLLs only
#     - runtime/audiveris  : loads the bundled JRE explicitly
#     - runtime/tesseract  : tesseract.exe + every UB Mannheim DLL
#     - runtime/poppler    : pdftoppm.exe & friends + every DLL from
#                             oschwartz10612/poppler-windows
#   So the produced installer does not depend on Tesseract/Poppler being
#   on the end user's machine.
# * For SmartScreen, sign accompanist-server.exe (PyInstaller output) and
#   the Tauri-produced .msi/.exe with an EV or OV Authenticode certificate.
#   Without signing, end users will see SmartScreen warnings on first
#   launch and may need to click "More info" → "Run anyway".
