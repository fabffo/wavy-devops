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

with roles_recette (
    id,
    code,
    libelle
) as (
    values
        (1, 'ADMIN_TENANT', 'Administrateur du tenant'),
        (2, 'GESTIONNAIRE', 'Gestionnaire'),
        (3, 'LECTURE_SEULE', 'Lecture seule'),
        (4, 'NOTE_DE_FRAIS', 'Utilisateur notes de frais'),
        (5, 'SUPER_NOTE_DE_FRAIS', 'Administrateur notes de frais')
)
update role r
set
    code = rr.code,
    libelle = rr.libelle
from roles_recette rr
where r.id = rr.id
and (
    r.code = rr.code
    or not exists (
        select 1
        from role r_code
        where r_code.code = rr.code
        and r_code.id <> r.id
    )
);

with roles_recette (
    id,
    code,
    libelle
) as (
    values
        (1, 'ADMIN_TENANT', 'Administrateur du tenant'),
        (2, 'GESTIONNAIRE', 'Gestionnaire'),
        (3, 'LECTURE_SEULE', 'Lecture seule'),
        (4, 'NOTE_DE_FRAIS', 'Utilisateur notes de frais'),
        (5, 'SUPER_NOTE_DE_FRAIS', 'Administrateur notes de frais')
)
update role r
set libelle = rr.libelle
from roles_recette rr
where r.code = rr.code;

insert into role (
    id,
    code,
    libelle
)
select
    rr.id,
    rr.code,
    rr.libelle
from (
    values
        (1, 'ADMIN_TENANT', 'Administrateur du tenant'),
        (2, 'GESTIONNAIRE', 'Gestionnaire'),
        (3, 'LECTURE_SEULE', 'Lecture seule'),
        (4, 'NOTE_DE_FRAIS', 'Utilisateur notes de frais'),
        (5, 'SUPER_NOTE_DE_FRAIS', 'Administrateur notes de frais')
) as rr (
    id,
    code,
    libelle
)
where not exists (
    select 1
    from role r
    where r.id = rr.id
    or r.code = rr.code
);

select setval(
    pg_get_serial_sequence('role', 'id'),
    coalesce((select max(id) from role), 0) + 1,
    false
);

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
),
(
    6,
    3,
    2,
    (select id from role where code = 'SUPER_NOTE_DE_FRAIS'),
    now(),
    now()
),
(
    7,
    3,
    6,
    (select id from role where code = 'NOTE_DE_FRAIS'),
    now(),
    now()
),
(
    8,
    3,
    7,
    (select id from role where code = 'NOTE_DE_FRAIS'),
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

create table if not exists parametre_tenant (
    id bigserial primary key,
    tenant_id bigint not null references tenant(id),
    categorie varchar(80) not null,
    code varchar(120) not null,
    valeur varchar(255) not null,
    libelle varchar(255) not null,
    taux numeric(7, 2),
    ordre_affichage integer not null default 0,
    actif boolean not null default true,
    date_creation timestamp not null default now(),
    date_modification timestamp not null default now()
);

alter table parametre_tenant add column if not exists categorie varchar(80);
alter table parametre_tenant add column if not exists taux numeric(7, 2);
alter table parametre_tenant add column if not exists ordre_affichage integer not null default 0;
alter table parametre_tenant alter column valeur type varchar(255);
alter table parametre_tenant alter column code type varchar(120);
update parametre_tenant set categorie = code where categorie is null;
alter table parametre_tenant alter column categorie set not null;

create unique index if not exists uk_parametre_tenant_categorie_code
    on parametre_tenant (tenant_id, categorie, code);

alter table parametre_tenant drop constraint if exists uk_parametre_tenant_code_valeur;
drop index if exists uk_parametre_tenant_code_valeur;

insert into parametre_tenant (
    tenant_id, categorie, code, valeur, libelle, taux, ordre_affichage, actif, date_creation, date_modification
)
select t.id, v.categorie, v.code, v.valeur, v.libelle, v.taux, v.ordre_affichage, true, now(), now()
from tenant t
cross join (
    values
    ('TYPE_TIERS', 'ORGANISATION', 'ORGANISATION', 'Organisation', null::numeric, 10),
    ('TYPE_TIERS', 'PERSONNE_PHYSIQUE', 'PERSONNE_PHYSIQUE', 'Personne physique', null::numeric, 20),
    ('NATURE_ORGANISATION', 'ENTREPRISE', 'ENTREPRISE', 'Entreprise', null::numeric, 10),
    ('NATURE_ORGANISATION', 'ASSOCIATION', 'ASSOCIATION', 'Association', null::numeric, 20),
    ('NATURE_ORGANISATION', 'ADMINISTRATION', 'ADMINISTRATION', 'Administration', null::numeric, 30),
    ('NATURE_ORGANISATION', 'AUTRE', 'AUTRE', 'Autre', null::numeric, 40),
    ('ACTIVITE', 'CONSEIL_IT', 'CONSEIL_IT', 'Conseil IT', null::numeric, 10),
    ('ACTIVITE', 'RECRUTEMENT', 'RECRUTEMENT', 'Recrutement', null::numeric, 20),
    ('ACTIVITE', 'FORMATION', 'FORMATION', 'Formation', null::numeric, 30),
    ('ACTIVITE', 'PRESTATION_SERVICES', 'PRESTATION_SERVICES', 'Prestation de services', null::numeric, 40),
    ('ACTIVITE', 'INDUSTRIE', 'INDUSTRIE', 'Industrie', null::numeric, 50),
    ('ACTIVITE', 'BANQUE', 'BANQUE', 'Banque', null::numeric, 60),
    ('ACTIVITE', 'ASSURANCE', 'ASSURANCE', 'Assurance', null::numeric, 70),
    ('TVA', 'TVA_20', 'TVA_20', 'TVA 20 %', 20.00, 10),
    ('TVA', 'TVA_10', 'TVA_10', 'TVA 10 %', 10.00, 20),
    ('TVA', 'TVA_55', 'TVA_55', 'TVA 5,5 %', 5.50, 30),
    ('TVA', 'TVA_0', 'TVA_0', 'TVA 0 %', 0.00, 40),
    ('TVA', 'EXONERE', 'EXONERE', 'Exonéré', 0.00, 50),
    ('TVA', 'INTRACOMMUNAUTAIRE', 'INTRACOMMUNAUTAIRE', 'Intracommunautaire', 0.00, 60),
    ('CONDITIONS_PAIEMENT', 'COMPTANT', 'COMPTANT', 'Comptant', null::numeric, 10),
    ('CONDITIONS_PAIEMENT', '30_JOURS', '30_JOURS', '30 jours', null::numeric, 20),
    ('CONDITIONS_PAIEMENT', '45_JOURS', '45_JOURS', '45 jours', null::numeric, 30),
    ('CONDITIONS_PAIEMENT', '60_JOURS', '60_JOURS', '60 jours', null::numeric, 40),
    ('FONCTION_PERSONNE', 'ADMINISTRATIF', 'ADMINISTRATIF', 'Administratif', null::numeric, 10),
    ('FONCTION_PERSONNE', 'DIRECTEUR', 'DIRECTEUR', 'Directeur', null::numeric, 20),
    ('FONCTION_PERSONNE', 'CONSULTANT', 'CONSULTANT', 'Consultant', null::numeric, 30),
    ('FONCTION_PERSONNE', 'COMMERCIAL', 'COMMERCIAL', 'Commercial', null::numeric, 40),
    ('FONCTION_PERSONNE', 'RH', 'RH', 'RH', null::numeric, 50),
    ('FONCTION_PERSONNE', 'COMPTABLE', 'COMPTABLE', 'Comptable', null::numeric, 60),
    ('FONCTION_PERSONNE', 'GESTIONNAIRE', 'GESTIONNAIRE', 'Gestionnaire', null::numeric, 70),
    ('FONCTION_PERSONNE', 'AUTRE', 'AUTRE', 'Autre', null::numeric, 80)
) as v(categorie, code, valeur, libelle, taux, ordre_affichage)
where not exists (
    select 1
    from parametre_tenant p
    where p.tenant_id = t.id
      and p.categorie = v.categorie
      and p.code = v.code
);

select setval(pg_get_serial_sequence('tenant', 'id'), greatest((select max(id) from tenant), 3), true);
select setval(pg_get_serial_sequence('societe_interne', 'id'), greatest((select max(id) from societe_interne), 5), true);
select setval(pg_get_serial_sequence('etablissement', 'id'), greatest((select max(id) from etablissement), 5), true);
select setval(pg_get_serial_sequence('role', 'id'), greatest((select max(id) from role), 5), true);
select setval(pg_get_serial_sequence('utilisateur', 'id'), greatest((select max(id) from utilisateur), 7), true);
select setval(pg_get_serial_sequence('utilisateur_role', 'id'), greatest((select max(id) from utilisateur_role), 8), true);
select setval(pg_get_serial_sequence('utilisateur_societe', 'id'), greatest((select max(id) from utilisateur_societe), 5), true);
select setval(pg_get_serial_sequence('parametre_tenant', 'id'), greatest((select max(id) from parametre_tenant), 1), true);

commit;
