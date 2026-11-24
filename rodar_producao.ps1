# Roda TRANSFORMER.py, BUMBLEBEE.py, IRONHIDE.py e ATUALIZA_FIPE.py usando o venv desta pasta.
# Mostra a saida na tela E grava em logs\ ao mesmo tempo (log geral + log de erro, se houver).
#
# IMPORTANTE: TRANSFORMER.py (via OPTIMUS PRIME.py / MEGATRON.py) usa pyautogui para
# simular teclado no seletor de certificado do Windows e no Chrome. Isso exige uma
# sessao de desktop ATIVA e DESBLOQUEADA no servidor - nao funciona como Windows
# Service nem com a sessao de RDP desconectada (tela travada).
# IRONHIDE.py nao tem essa restricao (so faz chamada de API).

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python    = Join-Path $ScriptDir "venv\Scripts\python.exe"
$LogDir    = Join-Path $ScriptDir "logs"

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

$Timestamp    = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile      = Join-Path $LogDir "execucao_$Timestamp.log"
$ErrorLogFile = Join-Path $LogDir "execucao_${Timestamp}_erros.log"

Set-Location $ScriptDir

function Escrever {
    param([string]$Linha, [string]$Arquivo)
    Write-Output $Linha
    $Linha | Out-File -FilePath $Arquivo -Append -Encoding utf8
}

function Rodar-Script {
    param([string]$NomeScript)

    Escrever "`n--- $NomeScript ---" $LogFile

    $totalErros = 0

    # -u desliga o buffer de saida do Python: sem isso, como a saida esta sendo
    # redirecionada (pipe), os prints so aparecem em blocos no final do processo.
    & $Python "-u" $NomeScript 2>&1 | ForEach-Object {
        if ($_ -is [System.Management.Automation.ErrorRecord]) {
            $linha = $_.ToString()
            $totalErros++
            Write-Output $linha
            $linha | Out-File -FilePath $ErrorLogFile -Append -Encoding utf8
            $linha | Out-File -FilePath $LogFile -Append -Encoding utf8
        } else {
            Write-Output $_
            $_ | Out-File -FilePath $LogFile -Append -Encoding utf8
        }
    }

    if ($totalErros -gt 0) {
        Escrever "$NomeScript terminou com ERRO ($totalErros linha(s) de erro)" $LogFile
    } else {
        Escrever "$NomeScript terminou sem erros" $LogFile
    }
}

Escrever "==============================================" $LogFile
Escrever "Inicio: $(Get-Date)" $LogFile

Rodar-Script "TRANSFORMER.py"
# BUMBLEBEE depois do TRANSFORMER (usa a MESMA DTA_EXEC da foto do dia) e antes do
# ATUALIZA_FIPE (que preenche a FIPE de quem esta na foto de hoje).
Rodar-Script "BUMBLEBEE.py"
Rodar-Script "IRONHIDE.py"
Rodar-Script "ATUALIZA_FIPE.py"

Escrever "Fim: $(Get-Date)" $LogFile

if ((Test-Path $ErrorLogFile) -and ((Get-Item $ErrorLogFile).Length -eq 0)) {
    Remove-Item $ErrorLogFile
}
