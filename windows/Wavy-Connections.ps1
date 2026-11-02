#requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('check','start','stop','diagnose','install','uninstall','supervise')]
    [string]$Action = 'check',
    [string]$ConfigPath = "$PSScriptRoot\connections.json",
    [switch]$LibraryOnly
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$TaskName = 'Wavy-Connections'
$StateDirectory = Join-Path $env:LOCALAPPDATA 'Wavy\Connections'

function Read-WavyConfig {
    $config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
    if (!(Test-Path -LiteralPath $config.Caddyfile -PathType Leaf)) { throw 'Caddyfile existant introuvable.' }
    if (!(Test-Path -LiteralPath $config.Caddy -PathType Leaf)) { throw 'Binaire Caddy introuvable.' }
    if (!(Test-Path -LiteralPath $config.IdentityFile -PathType Leaf)) { throw 'Cle SSH existante introuvable.' }
    $ports = @{}
    foreach ($tunnel in $config.Tunnels) {
        if ($tunnel.Name -notin @('recette','preprod') -or $ports.ContainsKey([int]$tunnel.LocalPort)) { throw 'Tunnel inconnu ou port local duplique.' }
        $ports[[int]$tunnel.LocalPort] = $true
        if ($tunnel.Destination -notmatch '^[a-zA-Z0-9_.-]+@[a-zA-Z0-9_.-]+$') { throw 'Destination SSH invalide.' }
        foreach ($port in @($tunnel.LocalPort, $tunnel.RemotePort, $tunnel.SshPort)) {
            if ([int]$port -lt 1 -or [int]$port -gt 65535) { throw 'Port invalide.' }
        }
        if ($tunnel.HttpsUrl -notmatch '^https://[a-zA-Z0-9.-]+/?$') { throw 'URL HTTPS invalide.' }
    }
    if ($config.Tunnels.Count -ne 2) { throw 'RECETTE et PREPROD sont requises.' }
    return $config
}
function Get-WavySshArguments($Tunnel, $IdentityFile) {
    # Aucun shell distant, mot de passe, acceptation implicite de cle hote ou bind public.
    return @('-N','-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
        '-o','PasswordAuthentication=no','-o','KbdInteractiveAuthentication=no',
        '-o','ExitOnForwardFailure=yes','-o','ServerAliveInterval=15',
        '-o','ServerAliveCountMax=3','-o','ConnectTimeout=10',
        '-o','IdentitiesOnly=yes','-i', $IdentityFile,
        '-p', [string]$Tunnel.SshPort, '-L', "127.0.0.1:$($Tunnel.LocalPort):127.0.0.1:$($Tunnel.RemotePort)", $Tunnel.Destination)
}
function Quote-WavyArgument([string]$Value) {
    if ($Value.Contains('"')) { throw 'Guillemet non autorise dans un chemin.' }
    return '"' + $Value + '"'
}
function Get-WavyListener([int]$Port) {
    return @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}
function Test-WavyHttps([string]$Url) {
    try {
        # Validation TLS Windows obligatoire, aucun contournement de certificat.
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 10 -MaximumRedirection 0
        return [pscustomobject]@{ Url=$Url; Accessible=($response.StatusCode -ge 200 -and $response.StatusCode -lt 400); Detail=[string]$response.StatusCode }
    } catch { return [pscustomobject]@{ Url=$Url; Accessible=$false; Detail=$_.Exception.Message } }
}
function Write-WavyStatus($Config) {
    foreach ($tunnel in $Config.Tunnels) {
        $listeners = @(Get-WavyListener $tunnel.LocalPort)
        $https = Test-WavyHttps $tunnel.HttpsUrl
        [pscustomobject]@{ Environment=$tunnel.Name; Port=$tunnel.LocalPort; Listening=($listeners.Count -gt 0); Https=$https.Accessible; Detail=$https.Detail }
    }
}
function Start-WavyProcess([string]$Binary, [string[]]$Arguments, [string]$Name) {
    $quoted = ($Arguments | ForEach-Object { Quote-WavyArgument $_ }) -join ' '
    return Start-Process -FilePath $Binary -ArgumentList $quoted -PassThru -WindowStyle Hidden -RedirectStandardError (Join-Path $StateDirectory "$Name.stderr.log") -RedirectStandardOutput (Join-Path $StateDirectory "$Name.stdout.log")
}
function Invoke-WavySupervisor($Config, [string]$MutexName = 'Local\WavyConnectionsSupervisor') {
    $mutex = New-Object System.Threading.Mutex($false, $MutexName)
    if (!$mutex.WaitOne(0)) { $mutex.Dispose(); return }
    $children = @{}
    $owned = @{}
    $stopFile = Join-Path $StateDirectory 'stop'
    Remove-Item -LiteralPath $stopFile -Force -ErrorAction SilentlyContinue
    try {
        while (!(Test-Path -LiteralPath $stopFile)) {
            # Un Caddy existant est conserve, meme si ses arguments sont inaccessibles.
            if (!@(Get-Process caddy -ErrorAction SilentlyContinue).Count) {
                $process = Start-WavyProcess $Config.Caddy @('run','--config',$Config.Caddyfile,'--adapter','caddyfile') 'caddy'
                $owned['caddy'] = $process
            }
            foreach ($tunnel in $Config.Tunnels) {
                $name = [string]$tunnel.Name
                if ($children.ContainsKey($name) -and !$children[$name].HasExited) { continue }
                $listeners = @(Get-WavyListener $tunnel.LocalPort)
                if ($listeners.Count) {
                    # Ne jamais tuer, doubler ou revendiquer un tunnel manuel existant.
                    # Apres sa disparition, le superviseur prend le relais.
                    continue
                }
                $process = Start-WavyProcess 'ssh.exe' (Get-WavySshArguments $tunnel $Config.IdentityFile) $name
                $children[$name] = $process
                $owned[$name] = $process
            }
            Start-Sleep -Seconds 5
        }
    } finally {
        foreach ($process in $owned.Values) {
            # Objets Process conserves : aucun PID issu d'un fichier, aucun processus manuel arrete.
            if (!$process.HasExited) { $process.Kill(); $process.WaitForExit(5000) | Out-Null }
            $process.Dispose()
        }
        $mutex.ReleaseMutex(); $mutex.Dispose()
    }
}
if ($LibraryOnly) { return }
$config = Read-WavyConfig
New-Item -ItemType Directory -Path $StateDirectory -Force | Out-Null
switch ($Action) {
    'check' {
        $status = @(Write-WavyStatus $config)
        $status
        if (@($status | Where-Object { !$_.Https }).Count) { exit 1 }
    }
    'diagnose' {
        Write-WavyStatus $config
        Get-Service ssh-agent | Select-Object Name,Status,StartType
        & ssh-add.exe -l
        Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue | Select-Object TaskName,State
        foreach ($tunnel in $config.Tunnels) {
            Get-WavyListener $tunnel.LocalPort | Select-Object LocalAddress,LocalPort,OwningProcess
            $log = Join-Path $StateDirectory "$($tunnel.Name).stderr.log"
            if (Test-Path -LiteralPath $log) { Get-Content -LiteralPath $log -Tail 8 }
        }
    }
    'supervise' { Invoke-WavySupervisor $config }
    'start' {
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if (!$task) { throw 'Executer install une fois pour cet utilisateur Windows.' }
        Start-ScheduledTask -TaskName $TaskName
    }
    'stop' {
        New-Item -ItemType File -Path (Join-Path $StateDirectory 'stop') -Force | Out-Null
        # Laisser le superviseur fermer uniquement les enfants dont il est proprietaire.
        Start-Sleep -Seconds 6
        Write-Output 'Arret demande. Caddy et tunnels manuels preexistants conserves.'
    }
    'install' {
        & $config.Caddy validate --config $config.Caddyfile --adapter caddyfile
        if ($LASTEXITCODE -ne 0) { throw 'Caddyfile invalide : aucune tache installee.' }
        # Copie locale Windows : ne depend pas du demarrage de WSL au logon.
        $installedScript = Join-Path $StateDirectory 'Wavy-Connections.ps1'
        $installedConfig = Join-Path $StateDirectory 'connections.json'
        $launcher = Join-Path $PSScriptRoot 'wavy-connections.cmd'
        $installedLauncher = Join-Path $StateDirectory 'wavy-connections.cmd'
        if ((Test-Path -LiteralPath $launcher) -and $launcher -ne $installedLauncher) { Copy-Item -LiteralPath $launcher -Destination $installedLauncher -Force }
        if ($PSCommandPath -ne $installedScript) { Copy-Item -LiteralPath $PSCommandPath -Destination $installedScript -Force }
        if ($ConfigPath -ne $installedConfig) { Copy-Item -LiteralPath $ConfigPath -Destination $installedConfig -Force }
        $powershell = Join-Path $PSHOME 'powershell.exe'
        $arguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File ' + (Quote-WavyArgument $installedScript) + ' -Action supervise -ConfigPath ' + (Quote-WavyArgument $installedConfig)
        $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        $taskAction = New-ScheduledTaskAction -Execute $powershell -Argument $arguments
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
        $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 99 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
        $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
        Register-ScheduledTask -TaskName $TaskName -Action $taskAction -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
        Write-Output 'Tache installee pour ouverture de session. Utiliser start pour demarrer maintenant.'
    }
    'uninstall' {
        & $PSCommandPath -Action stop -ConfigPath $ConfigPath
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    }
}
