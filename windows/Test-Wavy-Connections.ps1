# Tests Windows locaux, aucun processus SSH/Caddy ni connexion distante.
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\Wavy-Connections.ps1" -LibraryOnly
$script:count = 0
function Assert-Wavy($Condition, $Message) {
    if (!$Condition) { throw "ECHEC: $Message" }
    $script:count++
}
$tunnel = [pscustomobject]@{ Name='preprod'; Destination='wavyadmin@localhost'; SshPort=2223; LocalPort=24443; RemotePort=24443; HttpsUrl='https://preprod.wavyservices.fr' }
$args = Get-WavySshArguments $tunnel 'C:\fixture key\id_ed25519'
foreach ($expected in @('-N','-T','BatchMode=yes','StrictHostKeyChecking=yes','PasswordAuthentication=no','KbdInteractiveAuthentication=no','ExitOnForwardFailure=yes','ServerAliveInterval=15','ServerAliveCountMax=3','ConnectTimeout=10','127.0.0.1:24443:127.0.0.1:24443','C:\fixture key\id_ed25519')) {
    Assert-Wavy ($args -contains $expected) "Argument SSH $expected"
}
Assert-Wavy ((Quote-WavyArgument 'C:\avec espace\fichier') -eq '"C:\avec espace\fichier"') 'Chemins avec espaces'
function Invoke-WebRequest { [pscustomobject]@{ StatusCode=200 } }
Assert-Wavy (Test-WavyHttps $tunnel.HttpsUrl).Accessible 'HTTPS valide'
function Invoke-WebRequest { throw 'TLS non valide' }
Assert-Wavy (!(Test-WavyHttps $tunnel.HttpsUrl).Accessible) 'TLS refuse sans contournement'

$temporary = Join-Path $env:TEMP ([guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $temporary | Out-Null
$StateDirectory = $temporary
$script:starts = 0; $script:ticks = 0; $script:kills = 0
function Get-Process { return [pscustomobject]@{ Id=123; ProcessName='caddy' } }
function Get-WavyListener { if ($script:ticks -eq 0) { return [pscustomobject]@{ OwningProcess=456 } } }
function Start-WavyProcess {
    $script:starts++
    $process = [pscustomobject]@{ HasExited=$false }
    $process | Add-Member ScriptMethod Kill { $script:kills++; $this.HasExited=$true }
    $process | Add-Member ScriptMethod WaitForExit { return $true }
    $process | Add-Member ScriptMethod Dispose { }
    return $process
}
function Start-Sleep {
    $script:ticks++
    if ($script:ticks -eq 2) { $children['preprod'].HasExited = $true }
    if ($script:ticks -eq 3) { New-Item -ItemType File -Path (Join-Path $StateDirectory 'stop') | Out-Null }
}
try {
    Invoke-WavySupervisor ([pscustomobject]@{ Tunnels=@($tunnel); Caddy='fixture'; Caddyfile='fixture'; IdentityFile='fixture' }) -MutexName ('Local\WavyConnectionsTest-' + [guid]::NewGuid().ToString())
    Assert-Wavy ($script:starts -eq 2) 'Tunnel existant conserve puis reprise et reconnexion apres coupure'
    Assert-Wavy ($script:kills -eq 1) 'Arret du seul enfant vivant, Caddy et tunnel manuels preserves'
} finally { Remove-Item -LiteralPath $temporary -Recurse -Force }
Write-Output "$script:count tests Windows reussis. Aucun SSH/Caddy lance."
