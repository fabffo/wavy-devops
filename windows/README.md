# Connexions Windows Wavy

Le superviseur réutilise **le Caddyfile actif**, la clé SSH et les destinations existantes. Il ne lance que `caddy run` et des tunnels SSH `-N -T`, sans commande sur les VMs. Aucun service Docker ni réglage VM n'est modifié.

Depuis ce répertoire, dans PowerShell ou CMD :

```text
.\wavy-connections.cmd check
.\wavy-connections.cmd start
.\wavy-connections.cmd stop
.\wavy-connections.cmd diagnose
```

`check` vérifie les deux domaines avec la validation TLS Windows et renvoie 1 si l'un échoue. `diagnose` ajoute l'état du Planificateur, de l'agent SSH, des ports et les dernières erreurs SSH. Les journaux locaux sont dans `%LOCALAPPDATA%\Wavy\Connections`.

## Installation et démarrage

Sur MSI, `connections.json` est déjà préparé localement et ignoré par Git. Pour une autre installation, copier `connections.example.json` vers `connections.json`, puis renseigner les chemins du **Caddy existant** et de la **clé existante**. Ne jamais y ajouter de mot de passe, passphrase ou clé privée.

```text
.\wavy-connections.cmd install
.\wavy-connections.cmd start
```

L'installation valide le Caddyfile sans le modifier, copie les scripts/configuration dans `%LOCALAPPDATA%\Wavy\Connections` et crée la tâche `Wavy-Connections`, à l'ouverture de session de l'utilisateur courant, sans mot de passe stocké ni élévation. La copie locale Windows évite une dépendance à WSL au démarrage. Le lanceur est également disponible dans ce répertoire installé. Après modification des scripts, refaire `stop`, `install`, `start` pour utiliser la nouvelle copie.

Le paramètre PowerShell `ExecutionPolicy Bypass` est limité au processus exécutant ce script local revu. Aucune stratégie Windows persistante n'est modifiée.

`uninstall` arrête les enfants gérés et supprime la tâche ; les fichiers locaux restent disponibles pour diagnostic.

## Sécurité et reconnexion

- Clés d'hôte déjà connues obligatoires : `StrictHostKeyChecking=yes`. Une clé nouvelle ou modifiée n'est jamais acceptée automatiquement.
- Authentification par la clé existante, `BatchMode=yes`, mot de passe et interaction clavier désactivés. Une clé chiffrée doit être déverrouillée dans l'agent Windows par l'utilisateur. L'agent Windows était désactivé lors de la revue MSI : le superviseur ne modifie pas ce service système.
- Si l'agent doit être utilisé, son activation se fait depuis une console administrateur : `Set-Service ssh-agent -StartupType Automatic`, puis `Start-Service ssh-agent`. Dans la session utilisateur, `ssh-add "$env:USERPROFILE\.ssh\id_ed25519"` demande la passphrase de manière interactive ; aucune passphrase n'est enregistrée dans un script. Vérifier `ssh-add -l`, et les ACL privées de la clé existante.
- Les relais écoutent uniquement sur `127.0.0.1`. RECETTE : SSH localhost:2222 → port VM 24207, relais local 34443. PREPROD : SSH localhost:2223 → port VM 24443, relais local 24443.
- Keepalive SSH : 15 secondes, trois réponses manquées avant abandon, délai de connexion 10 secondes. Le superviseur retente après la fin du processus, toutes les cinq secondes.
- Une seule instance de superviseur par session Windows (mutex + politique IgnoreNew de la tâche). Caddy et les ports déjà occupés sont conservés ; ils ne sont jamais tués ni revendiqués. Après disparition d'un tunnel manuel, le superviseur peut prendre le relais.
- `stop` ferme uniquement les enfants créés par ce superviseur. Un Caddy/tunnel manuel préexistant reste actif. Un port occupé par un programme inattendu doit être diagnostiqué, jamais libéré automatiquement.

## État vérifié sur MSI

Caddyfile existant valide, inchangé ; tâche installée et démarrage/arrêt testés. RECETTE répond HTTPS 200 via son tunnel préexistant. PREPROD répond HTTPS 502 : aucun relais local 24443, et le point SSH existant localhost:2223 refuse la connexion. Ce refus ne prouve pas une panne ERP. Le superviseur reste capable de réessayer dès le retour du point SSH ; aucune VM n'a été démarrée ni reconfigurée pour contourner le refus.

La configuration et les gardes PREPROD du dépôt ont été vérifiées avant modification (46 tests), sans lecture de secrets ni reconfiguration de la VM. Aucun succès runtime PREPROD n'est attesté. Pour une clé chiffrée, le déverrouillage initial via l'agent reste également nécessaire.

Tests locaux sans réseau ni processus réel :

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Test-Wavy-Connections.ps1
```
