# Prova della Parte III su Windows, con Windows PowerShell 5.1: i comandi del
# lettore.
#
# Esegue il primo avvio di Minuta (lezione 15) cosi come lo scrive il lettore
# e ne scrive il verbale. Il libro stampa gli output presi da questo verbale.
#
#   powershell -ExecutionPolicy Bypass -File percorso\prova-minuta.ps1 VERBALE
#
# Lavora nella cartella personale dell'utente: va eseguito su una macchina
# di prova, mai sul proprio computer. Il laboratorio e' quello dell'ultimo
# commit, come lo trova chi lo scarica.
param([Parameter(Mandatory = $true)] [string] $Verbale)

$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$utf8 = New-Object System.Text.UTF8Encoding $false
$percorso = $PSScriptRoot
$lab = Split-Path -Parent $percorso
$casa = $HOME

# La creazione degli utenti, con le passphrase lette dai file di prova: il
# lettore le scrive quando il programma le chiede. Nel verbale non compare.
function Crea-Utenti {
    $py = '.\.venv\Scripts\python.exe'
    $persone = @(
        @('sarti', 'avvocato', 'Elena Sarti'),
        @('dini', 'avvocato', 'Marco Dini'),
        @('righi', 'avvocato', 'Paola Righi'),
        @('valli', 'avvocato', 'Stefano Valli'),
        @('irene', 'praticante', 'Irene'),
        @('rosa', 'segreteria', 'Rosa')
    )
    foreach ($p in $persone) {
        Get-Content "$casa\.materiale\$($p[0]).txt" |
            & $py -m app.manage crea-utente $p[0] --ruolo $p[1] `
                --nome $p[2] --passphrase-stdin | Out-Null
    }
}

# Il punto di partenza della lezione 15: la cartella minuta della Parte 0,
# con dentro il laboratorio, un repository Git con un'etichetta per ogni
# versione di Minuta. Ogni lezione passa alla sua versione con git switch;
# quella a cui si sta ancora lavorando prende l'etichetta dall'ultimo
# commit. Le passphrase di prova stanno in file a parte.
Remove-Item -Recurse -Force "$casa\minuta\laboratorio", "$casa\.materiale" `
    -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force "$casa\minuta" | Out-Null
New-Item -ItemType Directory "$casa\.materiale" | Out-Null
$clone = "$casa\minuta\laboratorio"
git clone -q $lab $clone
$versioni = Get-Content "$percorso\sessioni\windows\*.txt" |
    Select-String '^git switch --detach (v[0-9.]+)$' |
    ForEach-Object { $_.Matches[0].Groups[1].Value } | Sort-Object -Unique
foreach ($versione in $versioni) {
    git -C $clone rev-parse -q --verify "refs/tags/$versione" | Out-Null
    if ($LASTEXITCODE -ne 0) { git -C $clone tag $versione HEAD }
}
foreach ($nome in 'sarti', 'dini', 'righi', 'valli', 'irene', 'rosa') {
    [IO.File]::WriteAllText("$casa\.materiale\$nome.txt", `
        "passphrase di prova per $nome`n", $utf8)
}

# curl mostra la barra di avanzamento solo quando l'output non va sullo
# schermo: qui la si toglie, per avere lo stesso output del lettore.
$env:CURL_HOME = Join-Path $env:TEMP 'curl-prova'
New-Item -ItemType Directory -Force $env:CURL_HOME | Out-Null
foreach ($nome in '.curlrc', '_curlrc') {
    [IO.File]::WriteAllText((Join-Path $env:CURL_HOME $nome), `
        "--no-progress-meter`n", $utf8)
}
# Gli output larghi al massimo 79 colonne, come il codice del libro.
$env:COLUMNS = '79'
$env:PYTHONUTF8 = '1'
# La prova non usa mai una chiave vera.
Remove-Item Env:OPENAI_API_KEY, Env:MINUTA_API_KEY, Env:ANTHROPIC_API_KEY `
    -ErrorAction SilentlyContinue

# I programmi esterni passano da cmd, che unisce output ed errori come li
# vedrebbe il lettore; i comandi di PowerShell restano in PowerShell.
$nativi = '^(py|git|curl\.exe|\.\\\.venv\\Scripts\\python\.exe)(\s|$)'
# Le sessioni girano senza le variabili con cui la CI si annuncia: pytest,
# quando le trova, non accorcia i messaggi, e sul computer del lettore li
# accorcia.
Remove-Item Env:CI, Env:BUILD_NUMBER -ErrorAction SilentlyContinue
$verbaleTesto = New-Object System.Text.StringBuilder

function Scrivi([string] $Testo) { [void]$verbaleTesto.AppendLine($Testo) }

function Sessione([string] $Nome) {
    Scrivi "=== sessione $Nome - Windows PowerShell $($PSVersionTable.PSVersion)"
    Set-Location $casa
    $file = "$percorso\sessioni\windows\$Nome.txt"
    foreach ($riga in [IO.File]::ReadAllLines($file, $utf8)) {
        if ($riga -match '^### \[') { Scrivi $riga; continue }
        if ($riga.Trim() -eq '') { continue }
        $nascosta = $riga -match '^Crea-Utenti$'
        if (-not $nascosta) { Scrivi "PS $((Get-Location).Path)> $riga" }
        if ($riga -match $nativi) {
            $testo = cmd /c "$riga 2>&1" | Out-String -Width 200
        }
        else {
            try {
                $blocco = [ScriptBlock]::Create($riga)
                $testo = . $blocco 2>&1 | Out-String -Width 79
            }
            catch {
                $testo = $_ | Out-String -Width 79
            }
        }
        if (-not $nascosta -and $testo.Trim() -ne '') {
            Scrivi ($testo -replace '(\r?\n)+$', '')
        }
    }
    Scrivi ''
}

Scrivi '== Sistema'
Scrivi ([Environment]::OSVersion.VersionString)
Scrivi ((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))
Scrivi ''

Sessione 'l15'

# Lezione 15: Minuta gira in un secondo terminale. Uvicorn scrive il suo
# registro sull'uscita degli errori.
$registro = Join-Path $env:TEMP 'server-l15.txt'
$server = Start-Process -FilePath "$casa\minuta\laboratorio\.venv\Scripts\python.exe" `
    -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000' `
    -WorkingDirectory "$casa\minuta\laboratorio" `
    -RedirectStandardError $registro -PassThru -NoNewWindow
for ($i = 0; $i -lt 100; $i++) {
    try {
        Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8000/salute' | Out-Null
        break
    }
    catch { Start-Sleep -Milliseconds 200 }
}
Sessione 'l15b'
Stop-Process -Id $server.Id -Force
Start-Sleep -Seconds 1
Scrivi '### [esito:l15b-server]'
Get-Content $registro | ForEach-Object { Scrivi $_ }
Scrivi '### [/esito:l15b-server]'
Scrivi ''
Scrivi '== Fine'

[IO.File]::WriteAllText($Verbale, $verbaleTesto.ToString(), $utf8)
