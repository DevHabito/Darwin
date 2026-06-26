[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$logPath = Join-Path $projectDir "darwin_home\voice_repair_v49_35.log"

function Write-Step {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $line
    Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8
}

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Path -LiteralPath (Split-Path -Parent $logPath))) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $logPath) -Force | Out-Null
}

if (-not (Test-IsAdministrator)) {
    Write-Host "Solicitando permissao de administrador para instalar o reconhecimento de voz..."
    $arguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", ('"{0}"' -f $MyInvocation.MyCommand.Path)
    )
    Start-Process -FilePath "powershell.exe" -ArgumentList $arguments -Verb RunAs
    exit
}

Clear-Host
Write-Host "DARWIN v49.35 - REPARO DO RECONHECIMENTO DE VOZ" -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host ""
Write-Step "Inicio do reparo elevado."

$capabilities = @(
    "Language.Basic~~~pt-BR~0.0.1.0",
    "Language.Speech~~~pt-BR~0.0.1.0",
    "Language.TextToSpeech~~~pt-BR~0.0.1.0"
)

$restartNeeded = $false
$failed = @()
foreach ($capabilityName in $capabilities) {
    try {
        $capability = Get-WindowsCapability -Online -Name $capabilityName
        if ($capability.State -eq "Installed") {
            Write-Step "$capabilityName ja esta instalado."
            continue
        }

        Write-Step "Instalando $capabilityName. Isto pode levar alguns minutos."
        $result = Add-WindowsCapability -Online -Name $capabilityName
        if ($result.RestartNeeded) {
            $restartNeeded = $true
        }
        $after = Get-WindowsCapability -Online -Name $capabilityName
        if ($after.State -ne "Installed") {
            throw "O Windows retornou estado $($after.State)."
        }
        Write-Step "$capabilityName instalado."
    }
    catch {
        $failed += $capabilityName
        Write-Step "FALHA em $capabilityName`: $($_.Exception.Message)"
    }
}

try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    [Windows.Media.SpeechRecognition.SpeechRecognizer, Windows.Media.SpeechRecognition, ContentType=WindowsRuntime] | Out-Null
    [Windows.Globalization.Language, Windows.Globalization, ContentType=WindowsRuntime] | Out-Null
    $supported = @([Windows.Media.SpeechRecognition.SpeechRecognizer]::SupportedTopicLanguages)
    $ptBrSupported = @($supported | Where-Object { $_.LanguageTag -eq "pt-BR" }).Count -gt 0
    if ($ptBrSupported) {
        $language = New-Object Windows.Globalization.Language("pt-BR")
        $recognizer = New-Object Windows.Media.SpeechRecognition.SpeechRecognizer($language)
        $recognizer.Dispose()
        Write-Step "Reconhecedor moderno WinRT pt-BR encontrado."
    }
}
catch {
    $ptBrSupported = $false
    Write-Step "FALHA ao testar o reconhecedor WinRT: $($_.Exception.Message)"
}

$privacy = Get-ItemProperty -Path "HKCU:\Software\Microsoft\Speech_OneCore\Settings\OnlineSpeechPrivacy" -ErrorAction SilentlyContinue
$microphone = Get-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone" -ErrorAction SilentlyContinue
$privacyReady = $privacy.HasAccepted -eq 1
$microphoneReady = $microphone.Value -eq "Allow"
$ptBrReady = $ptBrSupported -and $privacyReady -and $microphoneReady

if (-not $privacyReady) {
    Write-Step "Consentimento de fala online ausente."
    Start-Process "ms-settings:privacy-speech"
}
if (-not $microphoneReady) {
    Write-Step "Permissao de microfone ausente."
    Start-Process "ms-settings:privacy-microphone"
}

if ($ptBrReady) {
    Write-Host ""
    Write-Host "SUCESSO: o reconhecedor pt-BR esta disponivel." -ForegroundColor Green
    Write-Step "Reconhecedor pt-BR pronto."

    $startupDir = [Environment]::GetFolderPath("Startup")
    $launcher = Join-Path $projectDir "Abrir_Darwin_Acordar_Com_Voz.bat"
    $linkPath = Join-Path $startupDir "Darwin Wake Guardian.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($linkPath)
    $shortcut.TargetPath = $launcher
    $shortcut.WorkingDirectory = $projectDir
    $shortcut.WindowStyle = 7
    $shortcut.Description = "Darwin Wake Guardian v49.34"
    $shortcut.Save()
    Write-Step "Inicializacao automatica ativada em $linkPath."
}
else {
    Write-Host ""
    Write-Host "O reconhecedor moderno ainda nao esta totalmente liberado." -ForegroundColor Yellow
    Write-Host "Ative fala online e microfone nas telas que foram abertas, depois rode este reparo novamente." -ForegroundColor Yellow
    Write-Step "WinRT pt-BR=$ptBrSupported; fala online=$privacyReady; microfone=$microphoneReady."
}

if ($failed.Count -gt 0) {
    Write-Host ""
    Write-Host "Alguns pacotes falharam. Verifique internet e Windows Update:" -ForegroundColor Red
    $failed | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
    Write-Step "Pacotes com falha: $($failed -join ', ')."
}

if ($restartNeeded) {
    Write-Host ""
    Write-Host "O Windows informou que precisa reiniciar." -ForegroundColor Yellow
    Write-Step "Reinicio solicitado pelo Windows."
}

Write-Host ""
Write-Host "Relatorio: $logPath"
Write-Host "Depois deste reparo, feche guardioes antigos e abra Darwin novamente."
Write-Host ""
Read-Host "Pressione ENTER para fechar"
