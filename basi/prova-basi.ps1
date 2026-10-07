# Prova della Parte 0 su Windows, con Windows PowerShell 5.1: le lezioni B2-B8
# di Minuta.
#
# Esegue i comandi delle lezioni B2-B8 cosi come li scrive il lettore e ne
# scrive il verbale. Il libro stampa gli output presi da questo verbale.
#
#   powershell -ExecutionPolicy Bypass -File basi\prova-basi.ps1 VERBALE
#
# Lavora nella cartella personale dell'utente: va eseguito su una macchina
# di prova, mai sul proprio computer.
param([Parameter(Mandatory = $true)] [string] $Verbale)

$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$utf8 = New-Object System.Text.UTF8Encoding $false
$basi = $PSScriptRoot
$casa = $HOME

# Le modifiche che il lettore fa con il Blocco note: file in UTF-8 con
# righe terminate da CR LF. Nel verbale non compaiono.
function Scrivi-File {
    param([string] $Percorso)
    $p = Join-Path (Get-Location).Path $Percorso
    [IO.File]::WriteAllText($p, (($args -join "`r`n") + "`r`n"), $utf8)
}
function Aggiungi-Righe {
    param([string] $Percorso)
    $p = Join-Path (Get-Location).Path $Percorso
    [IO.File]::AppendAllText($p, (($args -join "`r`n") + "`r`n"), $utf8)
}
function Sostituisci {
    param([string] $Percorso, [string] $Vecchio, [string] $Nuovo)
    $p = Join-Path (Get-Location).Path $Percorso
    $testo = [IO.File]::ReadAllText($p, $utf8)
    [IO.File]::WriteAllText($p, $testo.Replace($Vecchio, $Nuovo), $utf8)
    # Come dopo un salvataggio a mano: Python non riusa la vecchia
    # versione compilata.
    Remove-Item -Recurse -Force __pycache__ -ErrorAction SilentlyContinue
}

# Il punto di partenza della lezione B2: la cartella creata nella lezione
# B1 con Esplora file, con dentro il file LEGGIMI.md.
Remove-Item -Recurse -Force "$casa\minuta", "$casa\.materiale" `
    -ErrorAction SilentlyContinue
New-Item -ItemType Directory "$casa\minuta\quaderno" | Out-Null
New-Item -ItemType Directory "$casa\.materiale" | Out-Null
$leggimi = [IO.File]::ReadAllText("$basi\LEGGIMI.md", $utf8)
$leggimi = $leggimi.Replace("`r`n", "`n").Replace("`n", "`r`n")
[IO.File]::WriteAllText("$casa\minuta\quaderno\LEGGIMI.md", `
    $leggimi, $utf8)
Copy-Item -Recurse "$basi\conti", "$basi\sql", "$basi\documenti" "$casa\.materiale\"

# curl mostra la barra di avanzamento solo quando l'output non va sullo
# schermo: qui la si toglie, per avere lo stesso output del lettore.
$env:CURL_HOME = Join-Path $env:TEMP 'curl-prova'
New-Item -ItemType Directory -Force $env:CURL_HOME | Out-Null
foreach ($nome in '.curlrc', '_curlrc') {
    [IO.File]::WriteAllText((Join-Path $env:CURL_HOME $nome), "--no-progress-meter`n", $utf8)
}

# Gli output larghi al massimo 79 colonne, come il codice del libro.
$env:COLUMNS = '79'
# Python scrive in UTF-8 anche quando l'output non va sullo schermo, come
# farebbe nella finestra del lettore.
$env:PYTHONUTF8 = '1'
# Git parte senza la configurazione personale della macchina di prova,
# come su un computer dove non e' mai stato configurato.
$env:GIT_CONFIG_GLOBAL = Join-Path $env:TEMP 'gitconfig-prova'
Remove-Item -Force $env:GIT_CONFIG_GLOBAL -ErrorAction SilentlyContinue

# I programmi esterni passano da cmd, che unisce output ed errori come li
# vedrebbe il lettore; i comandi di PowerShell restano in PowerShell.
$nativi = '^(git|py|python|sqlite3|curl\.exe|openssl|\.\\\.venv\\Scripts\\python\.exe|\.\.\\conti\\\.venv\\Scripts\\python\.exe|& "C:\\Program Files\\Git\\usr\\bin\\openssl\.exe")(\s|$)'
# Le sessioni girano senza le variabili con cui la CI si annuncia: pytest,
# quando le trova, non accorcia i messaggi, e sul computer del lettore li
# accorcia.
Remove-Item Env:CI, Env:BUILD_NUMBER -ErrorAction SilentlyContinue
$verbaleTesto = New-Object System.Text.StringBuilder

function Scrivi([string] $Testo) { [void]$verbaleTesto.AppendLine($Testo) }

function Sessione([string] $Nome) {
    Scrivi "=== sessione $Nome - Windows PowerShell $($PSVersionTable.PSVersion)"
    Set-Location $casa
    $file = "$basi\sessioni\windows\$Nome.txt"
    foreach ($riga in [IO.File]::ReadAllLines($file, $utf8)) {
        if ($riga -match '^### \[') { Scrivi $riga; continue }
        if ($riga.Trim() -eq '') { continue }
        $nascosta = $riga -match '^(Scrivi-File|Aggiungi-Righe|Sostituisci|Copy-Item ~\\\.materiale)'
        if (-not $nascosta) { Scrivi "PS $((Get-Location).Path)> $riga" }
        if ($riga -match $nativi) {
            # L'operatore & di PowerShell, per cmd, non serve.
            $comando = $riga -replace '^& ', ''
            $testo = cmd /c "$comando 2>&1" | Out-String -Width 200
        }
        else {
            # Un blocco di script, e non Invoke-Expression, perche' gli
            # errori citino il comando del lettore e non questo programma.
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

Sessione 'b2'
Sessione 'b3'
Sessione 'b4'
Sessione 'b5'

# Lezione B6: il server gira in un secondo terminale, nella cartella del
# quaderno. Il suo registro chiude la sessione.
$registro = Join-Path $env:TEMP 'server-b6.txt'
$server = Start-Process -FilePath 'py' `
    -ArgumentList '-3.13', '-m', 'http.server', '8000', '--bind', '127.0.0.1' `
    -WorkingDirectory "$casa\minuta\quaderno" `
    -RedirectStandardError $registro -PassThru -NoNewWindow
for ($i = 0; $i -lt 50; $i++) {
    try {
        Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8000/' | Out-Null
        break
    }
    catch { Start-Sleep -Milliseconds 200 }
}
Sessione 'b6'
Stop-Process -Id $server.Id -Force
Start-Sleep -Seconds 1
Scrivi '### [esito:b6-server]'
Get-Content $registro | Where-Object { $_ -notmatch '"GET / HTTP' } |
    ForEach-Object { Scrivi $_ }
Scrivi '### [/esito:b6-server]'
Scrivi ''

Sessione 'b7'
Sessione 'b8'
Scrivi '== Fine'

[IO.File]::WriteAllText($Verbale, $verbaleTesto.ToString(), $utf8)
