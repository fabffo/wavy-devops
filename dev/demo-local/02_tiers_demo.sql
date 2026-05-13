begin;

delete from tiers_roles where tiers_id in (100, 101);
delete from contact_tiers where id in (100, 101) or tiers_id in (100, 101);
delete from adresse_tiers where id in (100, 101) or tiers_id in (100, 101);
delete from tiers_fonction where tiers_id in (100, 101);
delete from tiers_rattachement where tiers_source_id in (100, 101) or tiers_cible_id in (100, 101);
delete from tiers where id in (100, 101);

insert into tiers (
    id, tenant_id, societe_interne_id, type_tiers, nature_organisation,
    statut_tiers, raison_sociale, nom_commercial, siren, siret,
    numero_tva_intracommunautaire, email, telephone, actif,
    date_creation, date_modification
) values
    (100, 100, 100, 'ORGANISATION', 'ENTREPRISE',
     'ACTIF', 'Client Demo SAS', 'Client Demo', '111222333', '11122233300011',
     'FR00111222333', 'client.demo@example.com', '0101010101', true,
     now(), now()),
    (101, 100, 100, 'ORGANISATION', 'ENTREPRISE',
     'ACTIF', 'Prestataire Demo SAS', 'Prestataire Demo', '444555666', '44455566600022',
     'FR00444555666', 'prestataire.demo@example.com', '0102020202', true,
     now(), now());

insert into tiers_roles (tiers_id, role_tiers) values
    (100, 'CLIENT'),
    (101, 'PRESTATAIRE');

insert into adresse_tiers (
    id, tiers_id, type_adresse, ligne1, ligne2, ligne3, code_postal,
    ville, region, pays, adresse_par_defaut, actif,
    date_creation, date_modification
) values
    (100, 100, 'FACTURATION', '20 avenue du Client Demo', null, null, '75002',
     'Paris', null, 'France', true, true,
     now(), now()),
    (101, 101, 'PRINCIPALE', '30 rue du Prestataire Demo', null, null, '75003',
     'Paris', null, 'France', true, true,
     now(), now());

insert into contact_tiers (
    id, tiers_id, type_contact, civilite, nom, prenom, fonction,
    email, telephone, mobile, contact_par_defaut, actif,
    date_creation, date_modification
) values
    (100, 100, 'FACTURATION', 'MONSIEUR', 'Client', 'Camille', 'Responsable facturation',
     'client.demo@example.com', '0101010101', null, true, true,
     now(), now()),
    (101, 101, 'COMMERCIAL', 'MADAME', 'Prestataire', 'Alex', 'Responsable commercial',
     'prestataire.demo@example.com', '0102020202', null, true, true,
     now(), now());

select setval(pg_get_serial_sequence('tiers', 'id'), greatest((select max(id) from tiers), 101), true);
select setval(pg_get_serial_sequence('adresse_tiers', 'id'), greatest((select max(id) from adresse_tiers), 101), true);
select setval(pg_get_serial_sequence('contact_tiers', 'id'), greatest((select max(id) from contact_tiers), 101), true);

commit;
