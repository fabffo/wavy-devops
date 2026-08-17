begin;

delete from alias_marchand where tiers_id between 100 and 122;
delete from tiers_roles where tiers_id between 100 and 122;
delete from contact_tiers where id between 100 and 122 or tiers_id between 100 and 122;
delete from adresse_tiers where id between 100 and 122 or tiers_id between 100 and 122;
delete from tiers_fonction where tiers_id between 100 and 122;
delete from tiers_rattachement where tiers_source_id between 100 and 122 or tiers_cible_id between 100 and 122;
delete from tiers where id between 100 and 122;

insert into tiers (
    id, tenant_id, societe_interne_id, type_tiers, nature_organisation, nature_personne,
    statut_tiers, raison_sociale, nom_commercial, nom, prenom, siren, siret,
    numero_tva_intracommunautaire, email, telephone, actif,
    date_creation, date_modification
) values
    (100, 100, 100, 'ORGANISATION', 'ENTREPRISE', null,
     'ACTIF', 'Client Demo SAS', 'Client Demo', null, null, '111222333', '11122233300011',
     'FR00111222333', 'client.demo@example.com', '0101010101', true,
     now(), now()),
    (101, 100, 100, 'ORGANISATION', 'ENTREPRISE', null,
     'ACTIF', 'Prestataire Demo SAS', 'Prestataire Demo', null, null, '444555666', '44455566600022',
     'FR00444555666', 'prestataire.demo@example.com', '0102020202', true,
     now(), now()),
    (102, 100, 100, 'PERSONNE_PHYSIQUE', null, 'SALARIE_INTERNE',
     'ACTIF', null, null, 'Dupont', 'Jean', null, null,
     null, 'jean.dupont@example.com', '0103030303', true,
     now(), now()),
    (103, 100, 100, 'PERSONNE_PHYSIQUE', null, 'SALARIE_INTERNE',
     'ACTIF', null, null, 'Martin', 'Claire', null, null,
     null, 'claire.martin@example.com', '0104040404', true,
     now(), now()),
    (104, 100, 100, 'PERSONNE_PHYSIQUE', null, 'PARTICULIER',
     'ACTIF', null, null, 'Morel', 'Camille', null, null,
     null, 'camille.morel@example.com', '0105050505', true,
     now(), now()),
    (105, 100, 100, 'ORGANISATION', 'ENTREPRISE', null,
     'ACTIF', 'Fournisseur General Demo SARL', 'Fournisseur General Demo', null, null, '777888999', '77788899900033',
     'FR00777888999', 'fournisseur.general@example.com', '0106060606', true,
     now(), now()),
    (106, 100, 100, 'ORGANISATION', 'ENTREPRISE', null,
     'ACTIF', 'OVH SAS', 'OVHcloud', null, null, '424761419', '42476141900045',
     'FR22424761419', 'facturation@ovh.example', '0107070707', true,
     now(), now()),
    (107, 100, 100, 'ORGANISATION', 'ENTREPRISE', null,
     'ACTIF', 'Microsoft France SAS', 'Microsoft 365', null, null, '327733184', '32773318400069',
     'FR26327733184', 'billing@microsoft.example', '0108080808', true,
     now(), now()),
    (108, 100, 100, 'ORGANISATION', 'ENTREPRISE', null,
     'ACTIF', 'Assurance Wavy Demo SA', 'Assurance Wavy', null, null, '555666777', '55566677700044',
     'FR00555666777', 'contrats@assurance-wavy.example', '0109090909', true,
     now(), now()),
    (109, 100, 100, 'ORGANISATION', 'ENTREPRISE', null,
     'ACTIF', 'Telecom Demo SAS', 'Telecom Demo', null, null, '666777888', '66677788800055',
     'FR00666777888', 'factures@telecom-demo.example', '0110101010', true,
     now(), now()),
    (110, 100, 100, 'ORGANISATION', 'ENTREPRISE', null,
     'ACTIF', 'Talent Recruit Demo SAS', 'Talent Recruit', null, null, '888999000', '88899900000066',
     'FR00888999000', 'billing@talent-recruit.example', '0111111111', true,
     now(), now());

insert into tiers (
    id, tenant_id, societe_interne_id, type_tiers, nature_organisation, nature_personne,
    statut_tiers, raison_sociale, nom_commercial, enseigne, categorie_marchand,
    statut_validation_marchand, nom_normalise, nom, prenom, siren, siret,
    numero_tva_intracommunautaire, email, telephone, actif,
    date_creation, date_modification
) values
    (111, 100, 100, 'ORGANISATION', 'ENTREPRISE', null, 'ACTIF', 'SNCF VOYAGEURS SA', 'SNCF VOYAGEURS', 'SNCF', 'TRAIN', 'VALIDE', 'SNCF VOYAGEURS', null, null, '519037584', '51903758400019', 'FR60519037584', 'contact@sncf.example', '0130808080', true, now(), now()),
    (112, 100, 100, 'ORGANISATION', 'ENTREPRISE', null, 'ACTIF', 'RATP', 'RATP', 'RATP', 'TRANSPORT_PUBLIC', 'VALIDE', 'RATP', null, null, '775663438', '77566343801906', 'FR81775663438', 'contact@ratp.example', '0140037000', true, now(), now()),
    (113, 100, 100, 'ORGANISATION', 'ENTREPRISE', null, 'ACTIF', 'Uber France SAS', 'UBER', 'UBER', 'TAXI_VTC', 'VALIDE', 'UBER', null, null, '539454942', '53945494200034', 'FR12539454942', 'support@uber.example', '0184880000', true, now(), now()),
    (114, 100, 100, 'ORGANISATION', 'ENTREPRISE', null, 'ACTIF', 'G7 SAS', 'TAXI G7', 'G7', 'TAXI_VTC', 'VALIDE', 'TAXI G7', null, null, '324379866', '32437986600048', 'FR40324379866', 'contact@g7.example', '0147394739', true, now(), now()),
    (115, 100, 100, 'ORGANISATION', 'ENTREPRISE', null, 'ACTIF', 'Accor Invest', 'IBIS', 'IBIS', 'HOTEL', 'VALIDE', 'IBIS', null, null, '420685637', '42068563700011', 'FR03420685637', 'contact@ibis.example', '0145303030', true, now(), now()),
    (116, 100, 100, 'ORGANISATION', 'ENTREPRISE', null, 'ACTIF', 'Accor Hotels', 'NOVOTEL', 'NOVOTEL', 'HOTEL', 'VALIDE', 'NOVOTEL', null, null, '602036444', '60203644400010', 'FR21602036444', 'contact@novotel.example', '0145304040', true, now(), now()),
    (117, 100, 100, 'ORGANISATION', 'ENTREPRISE', null, 'ACTIF', 'Brioche Doree SAS', 'BRIOCHE DOREE', 'BRIOCHE DOREE', 'REPAS_RAPIDE', 'VALIDE', 'BRIOCHE DOREE', null, null, '318906591', '31890659100051', 'FR53318906591', 'contact@briochedoree.example', '0299000000', true, now(), now()),
    (118, 100, 100, 'ORGANISATION', 'ENTREPRISE', null, 'ACTIF', 'Flunch SAS', 'FLUNCH', 'FLUNCH', 'RESTAURANT', 'VALIDE', 'FLUNCH', null, null, '320772510', '32077251000027', 'FR42320772510', 'contact@flunch.example', '0320000000', true, now(), now()),
    (119, 100, 100, 'ORGANISATION', 'ENTREPRISE', null, 'ACTIF', 'Buffalo Grill SAS', 'BUFFALO GRILL', 'BUFFALO GRILL', 'RESTAURANT', 'VALIDE', 'BUFFALO GRILL', null, null, '318906443', '31890644300018', 'FR11318906443', 'contact@buffalo.example', '0145000000', true, now(), now()),
    (120, 100, 100, 'ORGANISATION', 'ENTREPRISE', null, 'ACTIF', 'TotalEnergies Marketing France', 'TOTALENERGIES', 'TOTALENERGIES', 'CARBURANT', 'VALIDE', 'TOTALENERGIES', null, null, '531680445', '53168044500024', 'FR95531680445', 'contact@totalenergies.example', '0147414141', true, now(), now()),
    (121, 100, 100, 'ORGANISATION', 'ENTREPRISE', null, 'ACTIF', 'Indigo Infra France', 'INDIGO', 'INDIGO', 'PARKING', 'VALIDE', 'INDIGO', null, null, '642020887', '64202088700075', 'FR36642020887', 'contact@indigo.example', '0142060000', true, now(), now()),
    (122, 100, 100, 'ORGANISATION', 'ENTREPRISE', null, 'ACTIF', 'VINCI Autoroutes', 'VINCI AUTOROUTES', 'VINCI AUTOROUTES', 'PEAGE', 'VALIDE', 'VINCI AUTOROUTES', null, null, '512377060', '51237706000048', 'FR09512377060', 'contact@vinci-autoroutes.example', '0188888888', true, now(), now());

insert into tiers_roles (tiers_id, role_tiers) values
    (100, 'CLIENT'),
    (101, 'PRESTATAIRE'),
    (102, 'SALARIE'),
    (103, 'SALARIE'),
    (104, 'CANDIDAT'),
    (105, 'FOURNISSEUR_GENERAL'),
    (106, 'FOURNISSEUR_GENERAL'),
    (107, 'FOURNISSEUR_GENERAL'),
    (108, 'FOURNISSEUR_GENERAL'),
    (109, 'FOURNISSEUR_GENERAL'),
    (110, 'FOURNISSEUR_GENERAL'),
    (111, 'MARCHAND'),
    (111, 'FOURNISSEUR_GENERAL'),
    (112, 'MARCHAND'),
    (113, 'MARCHAND'),
    (114, 'MARCHAND'),
    (115, 'MARCHAND'),
    (116, 'MARCHAND'),
    (117, 'MARCHAND'),
    (118, 'MARCHAND'),
    (119, 'MARCHAND'),
    (120, 'MARCHAND'),
    (121, 'MARCHAND'),
    (122, 'MARCHAND');

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
     now(), now()),
    (102, 105, 'PRINCIPALE', '40 rue du Fournisseur Demo', null, null, '75004',
     'Paris', null, 'France', true, true,
     now(), now()),
    (103, 106, 'PRINCIPALE', '2 rue Kellermann', null, null, '59100',
     'Roubaix', null, 'France', true, true,
     now(), now()),
    (104, 107, 'PRINCIPALE', '37 quai du President Roosevelt', null, null, '92130',
     'Issy-les-Moulineaux', null, 'France', true, true,
     now(), now()),
    (105, 108, 'PRINCIPALE', '8 avenue des Assurances', null, null, '75009',
     'Paris', null, 'France', true, true,
     now(), now()),
    (106, 109, 'PRINCIPALE', '14 rue des Reseaux', null, null, '69003',
     'Lyon', null, 'France', true, true,
     now(), now()),
    (107, 110, 'PRINCIPALE', '5 rue du Recrutement', null, null, '44000',
     'Nantes', null, 'France', true, true,
     now(), now()),
    (108, 111, 'PRINCIPALE', '2 place aux Etoiles', null, null, '93210',
     'Saint-Denis', null, 'France', true, true,
     now(), now()),
    (109, 112, 'PRINCIPALE', '54 quai de la Rapee', null, null, '75012',
     'Paris', null, 'France', true, true,
     now(), now()),
    (110, 113, 'PRINCIPALE', '3 rue du Transport', null, null, '75009',
     'Paris', null, 'France', true, true,
     now(), now()),
    (111, 114, 'PRINCIPALE', '22 rue Henri Barbusse', null, null, '92110',
     'Clichy', null, 'France', true, true,
     now(), now()),
    (112, 115, 'PRINCIPALE', '82 rue Henri Farman', null, null, '92130',
     'Issy-les-Moulineaux', null, 'France', true, true,
     now(), now()),
    (113, 116, 'PRINCIPALE', '82 rue Henri Farman', null, null, '92130',
     'Issy-les-Moulineaux', null, 'France', true, true,
     now(), now()),
    (114, 117, 'PRINCIPALE', '105 avenue Henri Freville', null, null, '35200',
     'Rennes', null, 'France', true, true,
     now(), now()),
    (115, 118, 'PRINCIPALE', '4 rue de l Espoir', null, null, '59260',
     'Lezennes', null, 'France', true, true,
     now(), now()),
    (116, 119, 'PRINCIPALE', '9 boulevard du General Leclerc', null, null, '92110',
     'Clichy', null, 'France', true, true,
     now(), now()),
    (117, 120, 'PRINCIPALE', '562 avenue du Parc de l Ile', null, null, '92000',
     'Nanterre', null, 'France', true, true,
     now(), now()),
    (118, 121, 'PRINCIPALE', '1 place des Degres', null, null, '92800',
     'Puteaux', null, 'France', true, true,
     now(), now()),
    (119, 122, 'PRINCIPALE', '1973 boulevard de la Defense', null, null, '92000',
     'Nanterre', null, 'France', true, true,
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

insert into alias_marchand (
    id, tenant_id, tiers_id, alias, alias_normalise, source, actif,
    date_creation, date_modification
) values
    (100, 100, 111, 'SNCF CONNECT', 'SNCF CONNECT', 'MANUEL', true, now(), now()),
    (101, 100, 111, 'OUI SNCF', 'OUI SNCF', 'MANUEL', true, now(), now()),
    (102, 100, 111, 'TGV INOUI', 'TGV INOUI', 'MANUEL', true, now(), now()),
    (103, 100, 112, 'RATP', 'RATP', 'MANUEL', true, now(), now()),
    (104, 100, 113, 'UBER TRIP', 'UBER TRIP', 'MANUEL', true, now(), now()),
    (105, 100, 114, 'G7', 'G7', 'MANUEL', true, now(), now()),
    (106, 100, 115, 'IBIS BUDGET', 'IBIS BUDGET', 'MANUEL', true, now(), now()),
    (107, 100, 115, 'ACCOR HOTELS', 'ACCOR HOTELS', 'MANUEL', true, now(), now()),
    (108, 100, 116, 'NOVOTEL HOTELS', 'NOVOTEL HOTELS', 'MANUEL', true, now(), now()),
    (109, 100, 117, 'BRIOCHE DOREE', 'BRIOCHE DOREE', 'MANUEL', true, now(), now()),
    (110, 100, 120, 'TOTAL ACCESS', 'TOTAL ACCESS', 'MANUEL', true, now(), now()),
    (111, 100, 121, 'INDIGO PARK', 'INDIGO PARK', 'MANUEL', true, now(), now()),
    (112, 100, 122, 'ASF VINCI', 'ASF VINCI', 'MANUEL', true, now(), now());

select setval(pg_get_serial_sequence('tiers', 'id'), greatest((select max(id) from tiers), 122), true);
select setval(pg_get_serial_sequence('adresse_tiers', 'id'), greatest((select max(id) from adresse_tiers), 119), true);
select setval(pg_get_serial_sequence('contact_tiers', 'id'), greatest((select max(id) from contact_tiers), 101), true);
select setval(pg_get_serial_sequence('alias_marchand', 'id'), greatest((select max(id) from alias_marchand), 112), true);

commit;
