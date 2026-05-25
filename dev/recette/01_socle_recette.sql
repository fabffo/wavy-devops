begin;

insert into tenant (
    id, code, nom, statut, base_dediee, cle_base_donnee,
    date_creation, date_modification
) values
(
    1,
    'GROUPE_WAVY',
    'Groupe Wavy',
    'ACTIF',
    false,
    null,
    now(),
    now()
),
(
    2,
    'GROUPE_DEMO',
    'Groupe Demo',
    'ACTIF',
    false,
    null,
    now(),
    now()
),
(
    3,
    'DEMO_RECETTE',
    'Groupe Démo Recette',
    'ACTIF',
    false,
    null,
    now(),
    now()
)
on conflict (id) do update set
    code = excluded.code,
    nom = excluded.nom,
    statut = excluded.statut,
    base_dediee = excluded.base_dediee,
    cle_base_donnee = excluded.cle_base_donnee,
    date_modification = now();

insert into societe_interne (
    id, tenant_id, raison_sociale, nom_commercial, numero_siren,
    numero_tva_intracommunautaire, forme_juridique, adresse_ligne_1,
    adresse_ligne_2, code_postal, ville, pays, email, telephone, actif,
    date_creation, date_modification
) values
(
    1,
    1,
    'Wavy Services',
    'Wavy Services',
    '982880312',
    'FR00982880312',
    'SASU',
    '8 rue Raymond Marcheron',
    null,
    '92170',
    'Vanves',
    'France',
    'contact@wavyservices.fr',
    '0102030405',
    true,
    now(),
    now()
),
(
    2,
    1,
    'Wavy Holding',
    'Wavy Holding',
    '930194709',
    null,
    'SASU',
    '8 rue Raymond Marcheron',
    null,
    '92170',
    'Vanves',
    'France',
    null,
    null,
    true,
    now(),
    now()
),
(
    3,
    2,
    'Demo Services',
    'Demo Services',
    '111222333',
    null,
    'SASU',
    '10 rue de la Demo',
    null,
    '75001',
    'Paris',
    'France',
    'contact@demo.wavy.fr',
    null,
    true,
    now(),
    now()
),
(
    4,
    3,
    'Démo Services SAS',
    'Démo Services SAS',
    '900000001',
    null,
    'SAS',
    '12 boulevard de la Recette',
    null,
    '75010',
    'Paris',
    'France',
    'contact@demo-recette.fr',
    null,
    true,
    now(),
    now()
),
(
    5,
    3,
    'Démo Immobilier SAS',
    'Démo Immobilier SAS',
    '900000002',
    null,
    'SAS',
    '14 avenue du Patrimoine',
    null,
    '75011',
    'Paris',
    'France',
    'contact@immobilier-recette.fr',
    null,
    true,
    now(),
    now()
)
on conflict (id) do update set
    tenant_id = excluded.tenant_id,
    raison_sociale = excluded.raison_sociale,
    nom_commercial = excluded.nom_commercial,
    numero_siren = excluded.numero_siren,
    numero_tva_intracommunautaire = excluded.numero_tva_intracommunautaire,
    forme_juridique = excluded.forme_juridique,
    adresse_ligne_1 = excluded.adresse_ligne_1,
    adresse_ligne_2 = excluded.adresse_ligne_2,
    code_postal = excluded.code_postal,
    ville = excluded.ville,
    pays = excluded.pays,
    email = excluded.email,
    telephone = excluded.telephone,
    actif = excluded.actif,
    date_modification = now();

insert into etablissement (
    id, tenant_id, societe_interne_id, numero_siret,
    adresse_ligne_1, adresse_ligne_2, code_postal, ville,
    pays, siege, actif, date_creation, date_modification
) values
(
    1,
    1,
    1,
    '98288031200011',
    '8 rue Raymond Marcheron',
    null,
    '92170',
    'Vanves',
    'France',
    true,
    true,
    now(),
    now()
),
(
    2,
    1,
    2,
    '93019470900018',
    '8 rue Raymond Marcheron',
    null,
    '92170',
    'Vanves',
    'France',
    true,
    true,
    now(),
    now()
),
(
    3,
    2,
    3,
    '11122233300010',
    '10 rue de la Demo',
    null,
    '75001',
    'Paris',
    'France',
    true,
    true,
    now(),
    now()
),
(
    4,
    3,
    4,
    '90000000100016',
    '12 boulevard de la Recette',
    null,
    '75010',
    'Paris',
    'France',
    true,
    true,
    now(),
    now()
),
(
    5,
    3,
    5,
    '90000000200024',
    '14 avenue du Patrimoine',
    null,
    '75011',
    'Paris',
    'France',
    true,
    true,
    now(),
    now()
)
on conflict (id) do update set
    tenant_id = excluded.tenant_id,
    societe_interne_id = excluded.societe_interne_id,
    numero_siret = excluded.numero_siret,
    adresse_ligne_1 = excluded.adresse_ligne_1,
    adresse_ligne_2 = excluded.adresse_ligne_2,
    code_postal = excluded.code_postal,
    ville = excluded.ville,
    pays = excluded.pays,
    siege = excluded.siege,
    actif = excluded.actif,
    date_modification = now();

insert into role (
    id, code, libelle
) values
(
    1,
    'ADMIN_TENANT',
    'Administrateur du tenant'
),
(
    2,
    'GESTIONNAIRE',
    'Gestionnaire'
),
(
    3,
    'LECTURE_SEULE',
    'Lecture seule'
)
on conflict (id) do update set
    code = excluded.code,
    libelle = excluded.libelle;

insert into role (
    code,
    libelle
)
select
    'ADMIN_PLATEFORME',
    'Administrateur plateforme'
where not exists (
    select 1
    from role
    where code = 'ADMIN_PLATEFORME'
);

update role
set libelle = 'Administrateur plateforme'
where code = 'ADMIN_PLATEFORME';

insert into utilisateur (
    id, tenant_id, nom, prenom, email, mot_de_passe_hash, actif,
    dernier_acces, date_creation, date_modification
) values
(
    1,
    1,
    'Admin',
    'Recette',
    'adminrecette@wavy.fr',
    'motdepasse123',
    true,
    null,
    now(),
    now()
),
(
    2,
    3,
    'Admin',
    'Groupe Demo',
    'admin.groupe-demo@recette.fr',
    'motdepasse123',
    true,
    null,
    now(),
    now()
),
(
    6,
    3,
    'Gestionnaire',
    'Services',
    'gestionnaire.services@recette.fr',
    'motdepasse123',
    true,
    null,
    now(),
    now()
),
(
    7,
    3,
    'Gestionnaire',
    'Immobilier',
    'gestionnaire.immobilier@recette.fr',
    'motdepasse123',
    true,
    null,
    now(),
    now()
)
on conflict (id) do update set
    tenant_id = excluded.tenant_id,
    nom = excluded.nom,
    prenom = excluded.prenom,
    email = excluded.email,
    mot_de_passe_hash = excluded.mot_de_passe_hash,
    actif = excluded.actif,
    dernier_acces = excluded.dernier_acces,
    date_modification = now();

insert into utilisateur_role (
    id, tenant_id, utilisateur_id, role_id, date_creation, date_modification
) values
(
    1,
    1,
    1,
    (select id from role where code = 'ADMIN_PLATEFORME'),
    now(),
    now()
),
(
    2,
    3,
    2,
    (select id from role where code = 'ADMIN_TENANT'),
    now(),
    now()
),
(
    3,
    3,
    2,
    (select id from role where code = 'GESTIONNAIRE'),
    now(),
    now()
),
(
    4,
    3,
    6,
    (select id from role where code = 'GESTIONNAIRE'),
    now(),
    now()
),
(
    5,
    3,
    7,
    (select id from role where code = 'GESTIONNAIRE'),
    now(),
    now()
)
on conflict (id) do update set
    tenant_id = excluded.tenant_id,
    utilisateur_id = excluded.utilisateur_id,
    role_id = excluded.role_id,
    date_modification = now();

insert into utilisateur_societe (
    id, tenant_id, utilisateur_id, societe_interne_id, societe_principale,
    actif, date_creation, date_modification
) values
(
    1,
    1,
    1,
    1,
    true,
    true,
    now(),
    now()
),
(
    2,
    3,
    2,
    4,
    true,
    true,
    now(),
    now()
),
(
    3,
    3,
    2,
    5,
    false,
    true,
    now(),
    now()
),
(
    4,
    3,
    6,
    4,
    true,
    true,
    now(),
    now()
),
(
    5,
    3,
    7,
    5,
    true,
    true,
    now(),
    now()
)
on conflict (id) do update set
    tenant_id = excluded.tenant_id,
    utilisateur_id = excluded.utilisateur_id,
    societe_interne_id = excluded.societe_interne_id,
    societe_principale = excluded.societe_principale,
    actif = excluded.actif,
    date_modification = now();

select setval(pg_get_serial_sequence('tenant', 'id'), greatest((select max(id) from tenant), 3), true);
select setval(pg_get_serial_sequence('societe_interne', 'id'), greatest((select max(id) from societe_interne), 5), true);
select setval(pg_get_serial_sequence('etablissement', 'id'), greatest((select max(id) from etablissement), 5), true);
select setval(pg_get_serial_sequence('role', 'id'), greatest((select max(id) from role), 3), true);
select setval(pg_get_serial_sequence('utilisateur', 'id'), greatest((select max(id) from utilisateur), 7), true);
select setval(pg_get_serial_sequence('utilisateur_role', 'id'), greatest((select max(id) from utilisateur_role), 5), true);
select setval(pg_get_serial_sequence('utilisateur_societe', 'id'), greatest((select max(id) from utilisateur_societe), 5), true);

commit;
