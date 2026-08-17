insert into tiers (
    id, tenant_id, societe_interne_id, type_tiers, nature_organisation, statut_tiers,
    raison_sociale, nom_commercial, siren, siret, numero_tva_intracommunautaire,
    email, telephone, actif, date_creation, date_modification
) values
    (100, 100, 100, 'ORGANISATION', 'ENTREPRISE', 'ACTIF', 'Alpha Industrie SAS', 'Alpha Industrie', '910000001', '91000000100010', 'FR00910000001', 'contact@alpha.example', '0101010101', true, now(), now()),
    (101, 100, 100, 'ORGANISATION', 'ENTREPRISE', 'ACTIF', 'Beta Distribution SAS', 'Beta Distribution', '910000002', '91000000200020', 'FR00910000002', 'contact@beta.example', '0102020202', true, now(), now()),
    (102, 100, 100, 'ORGANISATION', 'ENTREPRISE', 'ACTIF', 'Gamma Services SARL', 'Gamma Services', '910000003', '91000000300030', 'FR00910000003', 'contact@gamma.example', '0103030303', true, now(), now()),
    (103, 100, 100, 'PERSONNE_PHYSIQUE', null, 'ACTIF', null, null, null, null, null, 'camille.candidat@example', '0104040404', true, now(), now()),
    (106, 100, 100, 'ORGANISATION', 'ENTREPRISE', 'ACTIF', 'OVH SAS', 'OVHcloud', '424761419', '42476141900045', 'FR22424761419', 'facturation@ovh.example', '0107070707', true, now(), now()),
    (107, 100, 100, 'ORGANISATION', 'ENTREPRISE', 'ACTIF', 'Microsoft France SAS', 'Microsoft 365', '327733184', '32773318400069', 'FR26327733184', 'billing@microsoft.example', '0108080808', true, now(), now()),
    (108, 100, 100, 'ORGANISATION', 'ENTREPRISE', 'ACTIF', 'Assurance Wavy Demo SA', 'Assurance Wavy', '555666777', '55566677700044', 'FR00555666777', 'contrats@assurance-wavy.example', '0109090909', true, now(), now()),
    (109, 100, 100, 'ORGANISATION', 'ENTREPRISE', 'ACTIF', 'Telecom Demo SAS', 'Telecom Demo', '666777888', '66677788800055', 'FR00666777888', 'factures@telecom-demo.example', '0110101010', true, now(), now()),
    (110, 100, 100, 'ORGANISATION', 'ENTREPRISE', 'ACTIF', 'Talent Recruit Demo SAS', 'Talent Recruit', '888999000', '88899900000066', 'FR00888999000', 'billing@talent-recruit.example', '0111111111', true, now(), now())
on conflict (id) do update set raison_sociale = excluded.raison_sociale, actif = true, date_modification = now();

insert into tiers_roles (tiers_id, role_tiers) values
    (100, 'CLIENT'),
    (101, 'CLIENT'),
    (102, 'FOURNISSEUR_SERVICES'),
    (103, 'CANDIDAT'),
    (106, 'FOURNISSEUR_GENERAL'),
    (107, 'FOURNISSEUR_GENERAL'),
    (108, 'FOURNISSEUR_GENERAL'),
    (109, 'FOURNISSEUR_GENERAL'),
    (110, 'FOURNISSEUR_GENERAL')
on conflict (tiers_id, role_tiers) do nothing;

insert into adresse_tiers (
    id, tiers_id, type_adresse, ligne1, code_postal, ville, pays,
    adresse_par_defaut, actif, date_creation, date_modification
) values
    (100, 100, 'FACTURATION', '1 avenue Alpha', '69001', 'Lyon', 'France', true, true, now(), now()),
    (101, 101, 'FACTURATION', '2 boulevard Beta', '33000', 'Bordeaux', 'France', true, true, now(), now()),
    (102, 102, 'PRINCIPALE', '3 rue Gamma', '44000', 'Nantes', 'France', true, true, now(), now()),
    (103, 106, 'PRINCIPALE', '2 rue Kellermann', '59100', 'Roubaix', 'France', true, true, now(), now()),
    (104, 107, 'PRINCIPALE', '37 quai du President Roosevelt', '92130', 'Issy-les-Moulineaux', 'France', true, true, now(), now()),
    (105, 108, 'PRINCIPALE', '8 avenue des Assurances', '75009', 'Paris', 'France', true, true, now(), now()),
    (106, 109, 'PRINCIPALE', '14 rue des Reseaux', '69003', 'Lyon', 'France', true, true, now(), now()),
    (107, 110, 'PRINCIPALE', '5 rue du Recrutement', '44000', 'Nantes', 'France', true, true, now(), now())
on conflict (id) do update set ligne1 = excluded.ligne1, actif = true, date_modification = now();

insert into contact_tiers (
    id, tiers_id, type_contact, civilite, nom, prenom, fonction, email,
    telephone, contact_par_defaut, actif, date_creation, date_modification
) values
    (100, 100, 'FACTURATION', 'MADAME', 'Martin', 'Alice', 'Comptable', 'facturation@alpha.example', '0101010102', true, true, now(), now()),
    (101, 101, 'FACTURATION', 'MONSIEUR', 'Durand', 'Bruno', 'Comptable', 'facturation@beta.example', '0102020203', true, true, now(), now()),
    (102, 102, 'COMMERCIAL', 'MADAME', 'Petit', 'Claire', 'Commerciale', 'commercial@gamma.example', '0103030304', true, true, now(), now())
on conflict (id) do update set email = excluded.email, actif = true, date_modification = now();

select setval(pg_get_serial_sequence('tiers', 'id'), greatest((select max(id) from tiers), 110), true);
select setval(pg_get_serial_sequence('adresse_tiers', 'id'), greatest((select max(id) from adresse_tiers), 107), true);
select setval(pg_get_serial_sequence('contact_tiers', 'id'), greatest((select max(id) from contact_tiers), 102), true);
