# Election-night runner for election-2026.tw, for Windows. Open PowerShell and paste ONE of these lines:
#
#   irm https://election-2026.tw/night/win.ps1 | iex                                  # set up, then check this computer
#   $env:TWN_MODE='rehearsal'; irm https://election-2026.tw/night/win.ps1 | iex       # practice run to a test site
#   $env:TWN_MODE='night'; irm https://election-2026.tw/night/win.ps1 | iex           # election night
#
# Each time it downloads the latest code into %USERPROFILE%\twn-night\code (results and settings in twn-night are
# kept), makes a private Python environment in twn-night\venv, and starts scripts\live\night.py.
function Start-TwnNight {
  $ErrorActionPreference = 'Stop'
  $ProgressPreference = 'SilentlyContinue'
  $Mode = if ($env:TWN_MODE) { $env:TWN_MODE } else { 'check' }
  $Dir = Join-Path $HOME 'twn-night'
  $Zip = if ($env:TWN_ZIP) { $env:TWN_ZIP } else { 'https://github.com/hopehhchen/twn-watch-party-2026/archive/refs/heads/main.zip' }
  function Stop-Twn($msg) { Write-Host ''; Write-Host "STOPPED: $msg" -ForegroundColor Red; Write-Host 'Please send Hope a photo of this window.' }

  Write-Host ''
  Write-Host "=== election-2026.tw night runner ($Mode) ==="

  # 1. Python 3.9+ (the python.org installer adds the 'py' launcher; 'python' may be a Microsoft Store shortcut)
  $py = $null
  foreach ($cand in @(@('py', '-3'), @('python'))) {
    if (Get-Command $cand[0] -ErrorAction SilentlyContinue) {
      try {
        $args0 = @($cand | Select-Object -Skip 1)
        $v = & $cand[0] @args0 -c "import sys; print(1 if sys.version_info >= (3, 9) else 0)" 2>$null
        if ("$v".Trim() -eq '1') { $py = $cand; break }
      } catch { }
    }
  }
  if (-not $py) { Stop-Twn 'Python is not installed yet. Install it from https://www.python.org/downloads/ (step 1 of the guide; tick "Add python.exe to PATH"), then paste the line again.'; return }
  $pyArgs = @($py | Select-Object -Skip 1)
  Write-Host ("Python: " + (& $py[0] @pyArgs --version 2>&1))

  # 2. Node.js (for the publishing tool)
  if (-not (Get-Command npx -ErrorAction SilentlyContinue)) { Stop-Twn 'Node.js is not installed yet. Install the LTS version from https://nodejs.org/ (step 2 of the guide), close this window, open a new PowerShell and paste the line again.'; return }
  Write-Host ("Node.js: " + (node --version))

  # 3. The code (fresh copy each time)
  New-Item -ItemType Directory -Force -Path $Dir | Out-Null
  Write-Host 'Downloading the program...'
  $zipFile = Join-Path $Dir 'code.zip'
  try { Invoke-WebRequest -Uri $Zip -OutFile $zipFile -UseBasicParsing } catch { Stop-Twn "Couldn't download the program. Is the internet working?"; return }
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $Dir 'code')
  Get-ChildItem $Dir -Directory -Filter 'twn-watch-party-2026-*' | Remove-Item -Recurse -Force
  Expand-Archive -Path $zipFile -DestinationPath $Dir -Force
  $unz = Get-ChildItem $Dir -Directory -Filter 'twn-watch-party-2026-*' | Select-Object -First 1
  Rename-Item $unz.FullName 'code'
  Remove-Item $zipFile

  # 4. A private Python environment with the packages the program needs
  $vpy = Join-Path $Dir 'venv\Scripts\python.exe'
  if (-not (Test-Path $vpy)) {
    Write-Host 'Setting up Python (first time only)...'
    & $py[0] @pyArgs -m venv (Join-Path $Dir 'venv')
    if (-not (Test-Path $vpy)) { Stop-Twn "Couldn't set up Python."; return }
  }
  & $vpy -m pip install -q --disable-pip-version-check openpyxl==3.1.5 xlrd==2.0.2 certifi numpy
  if ($LASTEXITCODE -ne 0) { Stop-Twn "Couldn't install the Python packages. Is the internet working?"; return }

  # 5. Go
  $env:PYTHONUTF8 = '1'
  $env:PYTHONIOENCODING = 'utf-8'
  Set-Location (Join-Path $Dir 'code')
  & $vpy -u scripts\live\night.py $Mode
}
Start-TwnNight
