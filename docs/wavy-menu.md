# Menu interactif Wavy

Lancer `./wavy` sans argument ouvre le menu existant, désormais raccordé au moteur local permanent. Les syntaxes CLI explicites conservent leur aiguillage et leurs protections.

```text
WAVY | Menu principal
1 RECETTE locale MSI
2 RECETTE distante VM
3 PREPROD VM
4 Aide / commandes historiques
0 / q Quitter

WAVY | RECETTE locale MSI
https://recettelocal.wavyservices.fr
1 Démarrer                     6 Logs bornés
2 Arrêter                      7 Tests
3 Redémarrer                   8 Build des fronts + démarrer
4 Statuts Docker réels         9 Sauvegarde BDD (documents exclus)
5 Santé conteneurs + HTTPS     10 Restauration [indisponible]
```

Sélection : Entrée, `0`, `tous` ou `all` pour l’ensemble ; `2 4`, `tiers factures` ou `tiers,pwa` pour une sélection multiple. Les doublons sont retirés et les valeurs inconnues refusées. Les modules disponibles sont Socle, Tiers, Contrats, Factures, Trésorerie et PWA.

Navigation : `b` revient à l’étape précédente, `m` revient au menu principal et `q` quitte. Une fin d’entrée quitte proprement. Une erreur de commande conserve le menu et affiche son code de sortie. Les sous-commandes non interactives n’absorbent pas les saisies destinées au menu.

## Actions locales

Le menu appelle `./wavy local up|down|restart|status|logs|test`. Avant démarrage, arrêt, redémarrage et build, il affiche le `--dry-run` réel : ensemble requis, arrêts prévus et dépendances partagées conservées. L’utilisateur confirme avec `oui` ; toute autre réponse annule. Le moteur existant réévalue ensuite les dépendances à l’exécution et conserve les volumes/documents. Aucun nettoyage Docker n’est proposé dans le menu.

Les statuts proviennent de Docker, avec son état exact et son éventuelle santé. Une santé absente reste « non définie », y compris pour PWA : elle n’est pas transformée en « healthy ». L’action Santé utilise les tests locaux existants, incluant HTTPS. Les logs sont bornés (50 lignes par défaut, maximum 1000), avec le masquage existant des secrets.

Les tests proposent santé/HTTPS, Chrome ERP/PWA ou captures responsive. Les deux parcours navigateur nécessitent PWA sélectionné (ou tous), déjà opérationnel, et une confirmation avant ouverture. Aucun test métier n’est ajouté au menu.

Le build disponible reconstruit les **six fronts**, puis applique/démarre les modules sélectionnés et leurs dépendances. Il est annoncé comme tel ; aucun build API ni push implicite.

La sauvegarde réutilise `./wavy backup recette` après validation du contexte local. C’est une sauvegarde des cinq bases uniquement : documents exclus, sans snapshot distribué garanti pendant les écritures, sans arrêt automatique. Sa confirmation présente ce périmètre. Elle n’a pas été exécutée pendant la qualification du menu.

La restauration n’est pas proposée : la commande historique RECETTE est protégée pendant le cycle permanent et ne couvre pas les justificatifs. Le menu ne contourne pas cette protection et ne prétend pas fournir une restauration complète.

## Limites distantes et compatibilité

Les URL configurées sont `https://recette.wavyservices.fr` et `https://preprod.wavyservices.fr`. Leur état reste explicitement **non interrogé**. Les scripts historiques utilisent le Docker de la machine courante ; aucun transport SSH/VirtualBox n’est implémenté dans cette CLI. Les actions VM sont donc affichées indisponibles depuis MSI, sans appeler le Docker local à leur place.

L’action distante disponible est la préparation **locale** des plans via `./wavy promotion-plan recette|preprod`. Elle ne contacte aucune VM et ne déploie rien. Les mécanismes de déploiement, sauvegarde et restauration existants sur les hôtes cibles restent inchangés.

Attention aux deux syntaxes : `./wavy start local` conserve son sens historique SOURCE ; `./wavy local up` utilise la RECETTE HTTPS MSI. Le menu sélectionne toujours cette seconde syntaxe pour l’exploitation locale quotidienne.

## Qualification

- 17 tests de menu réussis : sélection, confirmations, annulation, aperçus, erreurs, navigation, logs, tests et absence d’opérations VM.
- 50 appels historiques comparés à l’ancien aiguillage, avec outils simulés isolés, codes de retour et sorties identiques. Les actions destructives ne sont pas exécutées réellement.
- 25 tests du moteur local réussis.
- Essais en terminal PTY réel : statuts Tiers/PWA, aperçu d’arrêt PWA annulé, navigation VM sans accès distant, plan PREPROD local et santé PWA/HTTPS (14 contrôles réussis).

**GO pour le menu et les capacités locales affichées. NO-GO pour le pilotage direct des VMs depuis MSI : transport absent.** La restauration locale reste indisponible. Aucun service Wavy n’a été arrêté, aucun volume ni donnée supprimé, aucun accès VM, commit ou push effectué.
