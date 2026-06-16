begin;

insert into tenant (
    id, code, nom, statut, base_dediee, cle_base_donnee,
    date_creation, date_modification
) values (
    100, 'DEMO_WAVY_LOCAL', 'Wavy Demo Local', 'ACTIF', false, null,
    now(), now()
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
    code_postal, ville, pays, email, telephone, actif,
    date_creation, date_modification
) values (
    100, 100, 'Wavy Demo Services', 'Wavy Demo Services', '982880312',
    'FR00982880312', 'SAS', '10 rue de la Demo',
    '75001', 'Paris', 'France', 'contact@wavy.local', '0100000000', true,
    now(), now()
)
on conflict (id) do update set
    tenant_id = excluded.tenant_id,
    raison_sociale = excluded.raison_sociale,
    nom_commercial = excluded.nom_commercial,
    numero_siren = excluded.numero_siren,
    numero_tva_intracommunautaire = excluded.numero_tva_intracommunautaire,
    forme_juridique = excluded.forme_juridique,
    adresse_ligne_1 = excluded.adresse_ligne_1,
    code_postal = excluded.code_postal,
    ville = excluded.ville,
    pays = excluded.pays,
    email = excluded.email,
    telephone = excluded.telephone,
    actif = excluded.actif,
    date_modification = now();

insert into utilisateur (
    id, tenant_id, email, nom, prenom, mot_de_passe_hash, actif,
    dernier_acces, date_creation, date_modification
) values (
    100, 100, 'demo@wavy.local', 'Demo', 'Fabrice', 'demo', true,
    null, now(), now()
)
on conflict (id) do update set
    tenant_id = excluded.tenant_id,
    email = excluded.email,
    nom = excluded.nom,
    prenom = excluded.prenom,
    mot_de_passe_hash = excluded.mot_de_passe_hash,
    actif = excluded.actif,
    date_modification = now();

insert into utilisateur_societe (
    id, tenant_id, utilisateur_id, societe_interne_id, societe_principale,
    actif, date_creation, date_modification
) values (
    100, 100, 100, 100, true,
    true, now(), now()
)
on conflict (id) do update set
    tenant_id = excluded.tenant_id,
    utilisateur_id = excluded.utilisateur_id,
    societe_interne_id = excluded.societe_interne_id,
    societe_principale = excluded.societe_principale,
    actif = excluded.actif,
    date_modification = now();


insert into role (id, code, libelle)
values
  (100, 'ADMIN_PLATEFORME', 'Administrateur plateforme'),
  (101, 'ADMIN_TENANT', 'Administrateur tenant')
on conflict (code) do update
set libelle = excluded.libelle;

insert into utilisateur_role (
  id,
  date_creation,
  date_modification,
  tenant_id,
  utilisateur_id,
  role_id
)
select
  100,
  now(),
  now(),
  100,
  u.id,
  r.id
from utilisateur u
join role r on r.code = 'ADMIN_PLATEFORME'
where u.email = 'demo@wavy.local'
on conflict (tenant_id, utilisateur_id, role_id) do nothing;

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


select setval(pg_get_serial_sequence('tenant', 'id'), greatest((select max(id) from tenant), 100), true);
select setval(pg_get_serial_sequence('societe_interne', 'id'), greatest((select max(id) from societe_interne), 100), true);
select setval(pg_get_serial_sequence('utilisateur', 'id'), greatest((select max(id) from utilisateur), 100), true);
select setval(pg_get_serial_sequence('utilisateur_societe', 'id'), greatest((select max(id) from utilisateur_societe), 100), true);
select setval(pg_get_serial_sequence('parametre_tenant', 'id'), greatest((select max(id) from parametre_tenant), 1), true);

commit;
