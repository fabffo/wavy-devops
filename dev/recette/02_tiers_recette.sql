begin;

insert into tiers (
    id, tenant_id, societe_interne_id, type_tiers, nature_organisation,
    statut_tiers, raison_sociale, nom_commercial, nom, prenom, siren, siret,
    numero_tva_intracommunautaire, email, telephone, actif,
    date_creation, date_modification
) values
    (4, 3, 4, 'ORGANISATION', 'ENTREPRISE', 'ACTIF', 'Client Alpha Industrie SAS', 'Client Alpha Industrie SAS', null, null, '910000001', null, null, 'contact@alpha-industrie.fr', null, true, now(), now()),
    (5, 3, 4, 'ORGANISATION', 'ENTREPRISE', 'ACTIF', 'Client Beta Distribution SAS', 'Client Beta Distribution SAS', null, null, '910000002', null, null, 'contact@beta-distribution.fr', null, true, now(), now()),
    (6, 3, 4, 'ORGANISATION', 'ENTREPRISE', 'ACTIF', 'Fournitures Bureau Recette SAS', 'Fournitures Bureau Recette SAS', null, null, '910000003', null, null, 'contact@fournitures-recette.fr', null, true, now(), now()),
    (7, 3, 4, 'ORGANISATION', 'ENTREPRISE', 'ACTIF', 'ESN Delta Consulting SAS', 'ESN Delta Consulting SAS', null, null, '910000004', null, null, 'contact@delta-consulting.fr', null, true, now(), now()),
    (8, 3, 4, 'PERSONNE_PHYSIQUE', null, 'ACTIF', null, null, 'Claire', 'Martin', null, null, null, 'claire.martin@recette.fr', null, true, now(), now()),
    (9, 3, 4, 'PERSONNE_PHYSIQUE', null, 'ACTIF', null, null, 'Julien', 'Bernard', null, null, null, 'julien.bernard@recette.fr', null, true, now(), now()),
    (10, 3, 4, 'PERSONNE_PHYSIQUE', null, 'ACTIF', null, null, 'Sophie', 'Durand', null, null, null, 'sophie.durand@demo-services.fr', null, true, now(), now()),
    (11, 3, 4, 'PERSONNE_PHYSIQUE', null, 'ACTIF', null, null, 'Thomas', 'Moreau', null, null, null, 'thomas.moreau@demo-services.fr', null, true, now(), now()),
    (12, 3, 4, 'ORGANISATION', 'ENTREPRISE', 'ACTIF', 'Banque Recette Entreprises', 'Banque Recette Entreprises', null, null, '910000005', null, null, 'agence@banque-recette.fr', null, true, now(), now()),
    (13, 3, 4, 'ORGANISME_FISCAL', 'ENTREPRISE', 'ACTIF', 'URSSAF Recette', 'URSSAF Recette', null, null, '910000006', null, null, 'contact@urssaf-recette.fr', null, true, now(), now()),
    (14, 3, 5, 'ORGANISATION', 'ENTREPRISE', 'ACTIF', 'Client Immo Patrimoine SAS', 'Client Immo Patrimoine SAS', null, null, '910000007', null, null, 'contact@immo-patrimoine.fr', null, true, now(), now()),
    (15, 3, 5, 'ORGANISATION', 'ENTREPRISE', 'ACTIF', 'Maintenance Immo Recette SAS', 'Maintenance Immo Recette SAS', null, null, '910000008', null, null, 'contact@maintenance-immo.fr', null, true, now(), now()),
    (16, 3, 5, 'ORGANISATION', 'ENTREPRISE', 'ACTIF', 'Banque Immo Recette', 'Banque Immo Recette', null, null, '910000009', null, null, 'agence@banque-immo-recette.fr', null, true, now(), now()),
    (17, 3, 5, 'PERSONNE_PHYSIQUE', null, 'ACTIF', null, null, 'Camille', 'Leroy', null, null, null, 'camille.leroy@recette.fr', null, true, now(), now())
on conflict (id) do update set
    tenant_id = excluded.tenant_id,
    societe_interne_id = excluded.societe_interne_id,
    type_tiers = excluded.type_tiers,
    nature_organisation = excluded.nature_organisation,
    nature_personne = excluded.nature_personne,
    statut_tiers = excluded.statut_tiers,
    raison_sociale = excluded.raison_sociale,
    nom_commercial = excluded.nom_commercial,
    nom = excluded.nom,
    prenom = excluded.prenom,
    siren = excluded.siren,
    siret = excluded.siret,
    numero_tva_intracommunautaire = excluded.numero_tva_intracommunautaire,
    email = excluded.email,
    telephone = excluded.telephone,
    actif = excluded.actif,
    date_modification = now();

insert into tiers_roles (tiers_id, role_tiers) values
    (4, 'CLIENT'),
    (5, 'CLIENT'),
    (6, 'FOURNISSEUR_GENERAL'),
    (7, 'FOURNISSEUR_SERVICES'),
    (8, 'PRESTATAIRE'),
    (9, 'PRESTATAIRE'),
    (10, 'SALARIE'),
    (11, 'SALARIE'),
    (12, 'BANQUE'),
    (13, 'ORGANISME_FISCAL'),
    (14, 'CLIENT'),
    (15, 'FOURNISSEUR_GENERAL'),
    (16, 'BANQUE'),
    (17, 'PRESTATAIRE')
on conflict do nothing;

select setval(pg_get_serial_sequence('tiers', 'id'), greatest((select max(id) from tiers), 17), true);
select setval(pg_get_serial_sequence('tiers_roles', 'tiers_id'), greatest((select max(tiers_id) from tiers_roles), 17), true);

commit;
