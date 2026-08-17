# Diagnostic Socle > Compteurs

Date : 2026-07-02

Objet : diagnostic factuel de l'erreur constatee sur le front Socle :

```text
GET http://localhost:24200/api/socle/compteurs
404 Not Found
```

Ce compte rendu remplace integralement le contenu precedent de ce fichier.

## 1\. Controleur Compteurs

Fichier trouve :

```text
/home/ffo/projets/wavy-socle-api/src/main/java/fr/wavy/socle\\\_multitenant/controleur/CompteurControleur.java
```

Package :

```java
package fr.wavy.socle\\\_multitenant.controleur;
```

Mapping exact :

```java
@RestController
@RequestMapping("/api/socle/compteurs")
public class CompteurControleur
```

Mappings GET exacts :

```java
@GetMapping("/ping")
@GetMapping({"", "/"})
@GetMapping("/{id}")
```

Conclusion : le controleur existe et expose bien :

```text
/api/socle/compteurs
/api/socle/compteurs/
/api/socle/compteurs/ping
```

## 2\. Scan Spring

Application Spring Boot :

```text
/home/ffo/projets/wavy-socle-api/src/main/java/fr/wavy/socle\\\_multitenant/SocleMultitenantApplication.java
```

Package racine :

```java
package fr.wavy.socle\\\_multitenant;
```

Package du controleur :

```java
package fr.wavy.socle\\\_multitenant.controleur;
```

Conclusion : le controleur est bien sous le package racine de l'application. Il est donc dans le scan Spring.

Log observe dans le conteneur :

```text
CompteurController charge
```

## 3\. Securite Spring

Fichier :

```text
/home/ffo/projets/wavy-socle-api/src/main/java/fr/wavy/socle\\\_multitenant/configuration/SecuriteConfiguration.java
```

Profil local :

```java
.anyRequest().permitAll()
```

Profil secure / production :

```java
.requestMatchers("/api/\\\*\\\*").authenticated()
```

Conclusion : `/api/socle/compteurs/\\\*\\\*` n'est pas bloque par une regle specifique. Un probleme de securite produirait plutot `401` ou `403`, pas le `404` observe.

## 4\. Port API Socle

Configuration trouvee :

```text
/home/ffo/projets/wavy-socle-api/src/main/resources/application.properties: server.port=8080
/home/ffo/projets/wavy-socle-api/src/main/resources/application-local.properties: server.port=8080
```

Exposition Docker recette :

```text
localhost:28080 -> wavy-socle-api-recette:8080
```

## 5\. Tests directs API Socle

URL directe testee sans headers :

```text
GET http://localhost:28080/api/socle/compteurs
HTTP 400
```

Reponse :

```json
{
  "erreur": "CONTEXTE\\\_INVALIDE",
  "message": "Aucun contexte courant n'a ete charge pour cette requete",
  "statut": 400
}
```

URL directe ping :

```text
GET http://localhost:28080/api/socle/compteurs/ping
HTTP 200
Body: compteurs-ok
```

URL directe avec contexte valide :

```text
GET http://localhost:28080/api/socle/compteurs
Headers:
  X-Tenant-Id: 1
  X-Utilisateur-Id: 1
  X-Societe-Courante-Id: 1
HTTP 200
```

La reponse contient le compteur :

```text
FACTURES / FACTURE\\\_VENTE
prochainNumero = FAC-2026-000001
```

URL directe avec contexte obsolete :

```text
GET http://localhost:28080/api/socle/compteurs
Headers:
  X-Tenant-Id: 100
  X-Utilisateur-Id: 100
  X-Societe-Courante-Id: 100
HTTP 404
```

Reponse :

```json
{
  "erreur": "RESSOURCE\\\_NON\\\_TROUVEE",
  "message": "Utilisateur introuvable dans le tenant courant : 100",
  "statut": 404
}
```

## 6\. Proxy / Front

Nginx reel du conteneur `wavy-socle-front-recette` :

```nginx
location /api/socle/ {
  proxy\\\_pass http://wavy-socle-api-recette:8080/api/socle/;
}

location /api/ {
  proxy\\\_pass http://wavy-gateway-recette:8088/api/;
}
```

Conclusion proxy :

```text
/api/socle/ -> wavy-socle-api-recette:8080
/api/       -> wavy-gateway-recette:8088
```

Port front recette :

```text
localhost:24200 -> wavy-socle-front-recette:80
```

Conteneurs observes :

```text
wavy-socle-api-recette     Up   0.0.0.0:28080->8080
wavy-socle-front-recette   Up   0.0.0.0:24200->80
wavy-gateway-recette       Up   0.0.0.0:28088->8088
```

## 7\. Tests via proxy 24200

URL proxy testee sans headers :

```text
GET http://localhost:24200/api/socle/compteurs
HTTP 400
```

Reponse :

```json
{
  "erreur": "CONTEXTE\\\_INVALIDE",
  "message": "Aucun contexte courant n'a ete charge pour cette requete",
  "statut": 400
}
```

URL proxy ping :

```text
GET http://localhost:24200/api/socle/compteurs/ping
HTTP 200
Body: compteurs-ok
```

URL proxy avec contexte valide :

```text
GET http://localhost:24200/api/socle/compteurs
Headers:
  X-Tenant-Id: 1
  X-Utilisateur-Id: 1
  X-Societe-Courante-Id: 1
HTTP 200
```

URL proxy avec contexte obsolete :

```text
GET http://localhost:24200/api/socle/compteurs
Headers:
  X-Tenant-Id: 100
  X-Utilisateur-Id: 100
  X-Societe-Courante-Id: 100
HTTP 404
```

Reponse :

```json
{
  "erreur": "RESSOURCE\\\_NON\\\_TROUVEE",
  "message": "Utilisateur introuvable dans le tenant courant : 100",
  "statut": 404
}
```

## 8\. Conclusion

Cause A : le controleur n'existe pas.

Resultat : faux.

Cause B : le controleur existe mais n'est pas scanne.

Resultat : faux.

Cause C : le mapping n'est pas `/api/socle/compteurs`.

Resultat : faux.

Cause D : l'API directe fonctionne mais le proxy `24200` route mal.

Resultat : faux. Le proxy route bien `/api/socle/` vers `wavy-socle-api-recette:8080`.

Cause E : l'image Docker lancee ne contient pas le nouveau code.

Resultat : faux. Le endpoint `/api/socle/compteurs/ping` repond `200` et le log `CompteurController charge` est present.

Cause F : autre cause demontree.

Resultat : vrai.

Le `404` est reproduit uniquement lorsque la requete contient le contexte obsolete :

```text
X-Tenant-Id: 100
X-Utilisateur-Id: 100
X-Societe-Courante-Id: 100
```

Ce `404` ne signifie pas que la route `/api/socle/compteurs` est absente. Il signifie que le backend cherche l'utilisateur `100` dans le tenant `100` et ne le trouve pas.

## 9\. Correction minimale proposee

Ne pas modifier le backend pour masquer cette erreur.

Correction minimale cote front Socle :

* ne plus envoyer le contexte par defaut `100/100/100` sur les appels applicatifs ;
* forcer l'ecran `/compteurs` a synchroniser le contexte depuis `/api/profil` avant d'appeler `/api/socle/compteurs` ;
* si le profil retourne `tenantId=1`, `utilisateurId=1`, `societeCouranteId=1`, envoyer ces valeurs dans les headers ;
* en cas d'impossibilite de recuperer le profil, afficher une erreur de session/contexte au lieu d'appeler la liste avec `100/100/100`.

## 10\. Criteres constates

URL directe API Socle testee :

```text
http://localhost:28080/api/socle/compteurs
```

Code HTTP direct sans headers :

```text
400
```

Code HTTP direct avec contexte valide `1/1/1` :

```text
200
```

URL proxy testee :

```text
http://localhost:24200/api/socle/compteurs
```

Code HTTP proxy sans headers :

```text
400
```

Code HTTP proxy avec contexte valide `1/1/1` :

```text
200
```

Code HTTP proxy avec contexte obsolete `100/100/100` :

```text
404
```

Fichier exact du controleur :

```text
/home/ffo/projets/wavy-socle-api/src/main/java/fr/wavy/socle\\\_multitenant/controleur/CompteurControleur.java
```

Mapping exact :

```java
@RequestMapping("/api/socle/compteurs")
@GetMapping({"", "/"})
```

