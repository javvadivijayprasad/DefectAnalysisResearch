<#
.SYNOPSIS
  Bootstrap script for Paper F rebuild: installs Defects4J and BugsInPy on Windows.

.DESCRIPTION
  Checks prerequisites (Git, Strawberry Perl, JDK 8/11, Python 3.7+), clones both
  corpora into E:\EB1A_Research\EB1_Master\06_Authorship\Research\PaperF_rebuild,
  runs Defects4J's init.sh through Git Bash, creates a Python venv for BugsInPy,
  and verifies both installs work end to end.

.NOTES
  Run from an ELEVATED PowerShell prompt the first time (choco installs need admin).
  Subsequent re-runs are idempotent and can be run non-elevated.
#>

param(
  [switch]$SkipPrereqCheck,
  [switch]$Force
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$BaseDir       = 'E:\EB1A_Research\EB1_Master\06_Authorship\Research\PaperF_rebuild'
$Defects4JDir  = Join-Path $BaseDir 'defects4j'
$BugsInPyDir   = Join-Path $BaseDir 'BugsInPy'
$VenvDir       = Join-Path $BaseDir 'bugsinpy-venv'
$LogFile       = Join-Path $BaseDir 'setup.log'

function Write-Step { param($msg) Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-OK   { param($msg) Write-Host "[OK]   $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Err  { param($msg) Write-Host "[ERR]  $msg" -ForegroundColor Red }

function Test-Cmd { param($cmd) [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

# --------------------------------------------------------------------------
# 0. Prepare base directory
# --------------------------------------------------------------------------
if (-not (Test-Path $BaseDir)) {
  New-Item -ItemType Directory -Path $BaseDir -Force | Out-Null
}
Start-Transcript -Path $LogFile -Append | Out-Null

Write-Step "Paper F rebuild setup starting"
Write-Host "  BaseDir      : $BaseDir"
Write-Host "  Defects4JDir : $Defects4JDir"
Write-Host "  BugsInPyDir  : $BugsInPyDir"
Write-Host "  VenvDir      : $VenvDir"

# --------------------------------------------------------------------------
# 1. Prerequisite check
# --------------------------------------------------------------------------
if (-not $SkipPrereqCheck) {
  Write-Step "Checking prerequisites"

  $missing = @()

  # Git
  if (Test-Cmd git)        { Write-OK "git found: $((git --version) -join ' ')" }
  else { Write-Err "git NOT found";        $missing += 'git' }

  # Git Bash (needed to run defects4j/init.sh)
  $gitBash = @(
    'C:\Program Files\Git\bin\bash.exe',
    'C:\Program Files (x86)\Git\bin\bash.exe',
    (Join-Path $env:LOCALAPPDATA 'Programs\Git\bin\bash.exe')
  ) | Where-Object { Test-Path $_ } | Select-Object -First 1

  if ($gitBash) { Write-OK "Git Bash found: $gitBash" }
  else { Write-Err "Git Bash NOT found (needed to run defects4j/init.sh)"; $missing += 'git-bash' }

  # Perl (Strawberry Perl on Windows)
  if (Test-Cmd perl)       { Write-OK "perl found: $((perl -v | Select-String 'This is perl') -join ' ')" }
  else { Write-Err "perl NOT found";       $missing += 'strawberryperl' }

  # cpanm (needed by defects4j init to install DBI, DBD::CSV, JSON, etc.)
  if (Test-Cmd cpanm)      { Write-OK "cpanm found" }
  else { Write-Warn "cpanm NOT found - defects4j init will fall back to cpan; install with: cpan App::cpanminus" }

  # JDK (Defects4J requires JDK 8; JDK 11 works for most projects)
  if (Test-Cmd java) {
    $javaVer = (cmd /c 'java -version 2>&1' | Select-Object -First 1)
    Write-OK "java found: $javaVer"
    if (-not $env:JAVA_HOME) {
      Write-Warn "JAVA_HOME is not set. Defects4J needs it. Set with:"
      Write-Warn '  setx JAVA_HOME "C:\Program Files\Eclipse Adoptium\jdk-8.0.xxx-hotspot"'
    }
  } else {
    Write-Err "java NOT found"; $missing += 'jdk8'
  }

  # Python 3.7+
  if (Test-Cmd python) {
    $pyVer = (cmd /c 'python --version 2>&1' | Select-Object -First 1)
    Write-OK "python found: $pyVer"
  } else {
    Write-Err "python NOT found"; $missing += 'python'
  }

  if ($missing.Count -gt 0) {
    Write-Host ""
    Write-Err "Missing prerequisites: $($missing -join ', ')"
    Write-Host ""
    Write-Host "Install commands (run in an ELEVATED PowerShell):" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  # 1. Install Chocolatey (if not present)"
    Write-Host "  Set-ExecutionPolicy Bypass -Scope Process -Force;"
    Write-Host "  [System.Net.ServicePointManager]::SecurityProtocol = 3072;"
    Write-Host "  iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))"
    Write-Host ""
    Write-Host "  # 2. Install prerequisites"
    Write-Host "  choco install -y git strawberryperl python temurin8"
    Write-Host "     (or:  choco install -y adoptopenjdk8   on older machines)"
    Write-Host ""
    Write-Host "  # 3. Install cpanm (via Strawberry Perl's cpan)"
    Write-Host "  cpan App::cpanminus"
    Write-Host ""
    Write-Host "  # 4. Set JAVA_HOME (adjust path to your JDK install)"
    Write-Host '  setx JAVA_HOME "C:\Program Files\Eclipse Adoptium\jdk-8.0.xxx-hotspot"'
    Write-Host ""
    Write-Host "Re-open PowerShell and re-run this script." -ForegroundColor Yellow
    Stop-Transcript | Out-Null
    exit 1
  }
} else {
  Write-Warn "Skipping prerequisite check (-SkipPrereqCheck)"
  $gitBash = 'C:\Program Files\Git\bin\bash.exe'
}

# --------------------------------------------------------------------------
# 2. Clone Defects4J
# --------------------------------------------------------------------------
Write-Step "Cloning Defects4J"

if ((Test-Path $Defects4JDir) -and (-not $Force)) {
  Write-OK "Defects4J already cloned at $Defects4JDir (skipping; pass -Force to re-clone)"
} else {
  if ($Force -and (Test-Path $Defects4JDir)) {
    Remove-Item -Recurse -Force $Defects4JDir
  }
  git clone https://github.com/rjust/defects4j.git $Defects4JDir
  Write-OK "Defects4J cloned"
}

# --------------------------------------------------------------------------
# 3. Run Defects4J init.sh via Git Bash
# --------------------------------------------------------------------------
Write-Step "Initialising Defects4J (running init.sh under Git Bash)"

if (-not (Test-Path $gitBash)) {
  Write-Err "Git Bash not found at $gitBash. .sh scripts cannot be run natively by PowerShell."
  Write-Err "Install Git for Windows from https://git-scm.com/download/win and re-run."
  Stop-Transcript | Out-Null
  exit 2
}

$initScript = Join-Path $Defects4JDir 'init.sh'
if (-not (Test-Path $initScript)) {
  Write-Err "init.sh not found at $initScript"
  Stop-Transcript | Out-Null
  exit 3
}

# Convert Windows path to Git-Bash-friendly path (E:\... -> /e/...)
$posixDefects4JDir = "/" + $Defects4JDir.Substring(0,1).ToLower() + ($Defects4JDir.Substring(2) -replace '\\', '/')
& $gitBash --login -c "cd '$posixDefects4JDir' && ./init.sh"
if ($LASTEXITCODE -ne 0) {
  Write-Err "defects4j init.sh exited with code $LASTEXITCODE"
  Write-Warn "Common Windows fixes:"
  Write-Warn "  - Perl CPAN prompts: run 'cpan App::cpanminus' first, then re-run"
  Write-Warn "  - SSL issues cloning subject projects: set GIT_SSL_NO_VERIFY=true temporarily"
  Write-Warn "  - Line-ending trouble in Perl modules: git config --global core.autocrlf false"
  Stop-Transcript | Out-Null
  exit 4
}
Write-OK "defects4j init.sh completed"

# --------------------------------------------------------------------------
# 4. Put defects4j on PATH for this session and verify
# --------------------------------------------------------------------------
Write-Step "Verifying Defects4J"

$d4jBin = Join-Path $Defects4JDir 'framework\bin'
$env:PATH = "$d4jBin;$env:PATH"

Write-Host "Running: defects4j info -p Lang"
& $gitBash --login -c "cd '$posixDefects4JDir' && ./framework/bin/defects4j info -p Lang" | Select-Object -First 20
if ($LASTEXITCODE -eq 0) {
  Write-OK "Defects4J responded (Lang project metadata printed)"
} else {
  Write-Warn "defects4j info -p Lang did not return cleanly (exit $LASTEXITCODE). Check log."
}

Write-Host ""
Write-Host "To make Defects4J available in future shells, add this to your PowerShell profile:" -ForegroundColor Yellow
Write-Host "  `$env:PATH = '$d4jBin;' + `$env:PATH"

# --------------------------------------------------------------------------
# 5. Clone BugsInPy
# --------------------------------------------------------------------------
Write-Step "Cloning BugsInPy"

if ((Test-Path $BugsInPyDir) -and (-not $Force)) {
  Write-OK "BugsInPy already cloned at $BugsInPyDir (skipping; pass -Force to re-clone)"
} else {
  if ($Force -and (Test-Path $BugsInPyDir)) {
    Remove-Item -Recurse -Force $BugsInPyDir
  }
  git clone https://github.com/soarsmu/BugsInPy.git $BugsInPyDir
  Write-OK "BugsInPy cloned"
}

# --------------------------------------------------------------------------
# 6. Create BugsInPy Python virtual environment
# --------------------------------------------------------------------------
Write-Step "Creating Python virtual environment for BugsInPy"

if ((Test-Path $VenvDir) -and (-not $Force)) {
  Write-OK "Venv already exists at $VenvDir (skipping)"
} else {
  if ($Force -and (Test-Path $VenvDir)) { Remove-Item -Recurse -Force $VenvDir }
  python -m venv $VenvDir
  Write-OK "Venv created"
}

$venvActivate = Join-Path $VenvDir 'Scripts\Activate.ps1'
. $venvActivate
python -m pip install --upgrade pip wheel setuptools | Out-Null

# BugsInPy dependencies (BugsInPy itself has no setup.py; it's a set of scripts).
# We install pytest + coverage which most subject projects need to reproduce a bug.
pip install pytest coverage virtualenv | Out-Null
Write-OK "Python venv ready with pytest + coverage + virtualenv"

# --------------------------------------------------------------------------
# 7. Put BugsInPy scripts on PATH and verify
# --------------------------------------------------------------------------
Write-Step "Verifying BugsInPy"

$bipBin = Join-Path $BugsInPyDir 'framework\bin'
$env:PATH = "$bipBin;$env:PATH"

# BugsInPy scripts are shell scripts; call via Git Bash.
$posixBipDir = "/" + $BugsInPyDir.Substring(0,1).ToLower() + ($BugsInPyDir.Substring(2) -replace '\\', '/')
& $gitBash --login -c "cd '$posixBipDir' && ./framework/bin/bugsinpy-info projects" | Select-Object -First 30
if ($LASTEXITCODE -eq 0) {
  Write-OK "BugsInPy responded (project list printed)"
} else {
  Write-Warn "bugsinpy-info projects did not return cleanly (exit $LASTEXITCODE). Check log."
}

# --------------------------------------------------------------------------
# 8. Final summary + next commands
# --------------------------------------------------------------------------
Write-Step "Setup complete"

Write-Host ""
Write-Host "PATHS" -ForegroundColor Cyan
Write-Host "  Defects4J : $Defects4JDir"
Write-Host "  BugsInPy  : $BugsInPyDir"
Write-Host "  Venv      : $VenvDir"
Write-Host "  Log       : $LogFile"
Write-Host ""
Write-Host "NEXT COMMANDS TO TRY (from Git Bash unless noted)" -ForegroundColor Cyan
Write-Host ""
Write-Host "  # Add both frameworks to PATH for this session (PowerShell)"
Write-Host "  `$env:PATH = '$d4jBin;$bipBin;' + `$env:PATH"
Write-Host ""
Write-Host "  # Check out Defects4J Lang bug #1 (buggy version) into a scratch dir"
Write-Host "  defects4j checkout -p Lang -v 1b -w /tmp/lang_1_buggy"
Write-Host "  cd /tmp/lang_1_buggy && defects4j compile && defects4j test"
Write-Host ""
Write-Host "  # Check out BugsInPy pandas bug #1 (buggy version)"
Write-Host "  bugsinpy-checkout -p pandas -v 0 -i 1 -w /tmp/pandas_1_buggy"
Write-Host "  cd /tmp/pandas_1_buggy && bugsinpy-compile && bugsinpy-test"
Write-Host ""
Write-Host "See SETUP_NOTES.md for full scale, disk requirements, and Windows quirks." -ForegroundColor Yellow

Stop-Transcript | Out-Null
