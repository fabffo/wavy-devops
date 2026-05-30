begin;

delete from ventilation_tva_facture where id in (100, 101) or facture_id in (100, 101);
delete from ligne_facture where id in (100, 101) or facture_id in (100, 101);
delete from facture where id in (100, 101);

insert into facture (
    id, tenant_id, societe_interne_id, utilisateur_createur_id, tiers_id,
    contrat_id, numero_facture, libelle, type_facture, sens_facture,
    nature_facture, categorie_operation, statut_facture, statut_electronique,
    format_electronique, regime_tva, mode_paiement, devise,
    date_facture, date_emission, date_echeance, date_prestation_ou_vente,
    total_ht, total_tva, total_ttc, total_remise, montant_deja_paye,
    netapayer, resteapayer, option_tva_sur_les_debits,
    vendeur_nom, vendeur_siren, vendeur_siret, vendeur_adresse_ligne1,
    vendeur_code_postal, vendeur_ville, vendeur_pays, vendeur_email_contact,
    client_nom, client_siren, client_siret, client_adresse_facturation_ligne1,
    client_code_postal, client_ville, client_pays, client_email_contact,
    conditions_reglement, indemnite_forfaitaire_recouvrement, taux_penalites_retard,
    date_creation, date_modification
) values
(
    100, 100, 100, 100, 100,
    100, 'FAC-DEMO-2026-001', 'Facture demo client', 'FACTURE_DOIT', 'VENTE',
    'SERVICE', 'PRESTATION_SERVICES', 'VALIDEE', 'NON_TRANSMISE',
    'AUCUN', 'TVA_STANDARD', 'VIREMENT', 'EUR',
    '2026-05-13', '2026-05-13', '2026-06-12', '2026-05-13',
    1000.00, 200.00, 1200.00, 0.00, 0.00,
    1200.00, 1200.00, false,
    'Wavy Demo Services', '982880312', '98288031200011', '10 rue de la Demo',
    '75001', 'Paris', 'France', 'contact@wavy.local',
    'Client Demo SAS', '111222333', '11122233300011', '20 avenue du Client Demo',
    '75002', 'Paris', 'France', 'client.demo@example.com',
    'Paiement a 30 jours', 40.00, 0.00,
    now(), now()
),
(
    101, 100, 100, 100, 100,
    null, 'FAC-DEMO-2026-002', 'Facture demo hors contrat', 'FACTURE_DOIT', 'VENTE',
    'SERVICE', 'PRESTATION_SERVICES', 'BROUILLON', 'NON_TRANSMISE',
    'AUCUN', 'TVA_STANDARD', 'VIREMENT', 'EUR',
    '2026-05-14', '2026-05-14', '2026-06-13', '2026-05-14',
    300.00, 60.00, 360.00, 0.00, 0.00,
    360.00, 360.00, false,
    'Wavy Demo Services', '982880312', '98288031200011', '10 rue de la Demo',
    '75001', 'Paris', 'France', 'contact@wavy.local',
    'Client Demo SAS', '111222333', '11122233300011', '20 avenue du Client Demo',
    '75002', 'Paris', 'France', 'client.demo@example.com',
    'Paiement a 30 jours', 40.00, 0.00,
    now(), now()
);

insert into ligne_facture (
    id, facture_id, reference_contrat_id, libelle, description, quantite,
    unite, prix_unitaire_ht, remise_pourcentage, remise_montant,
    montant_ht_avant_remise, montant_remise, montant_ht, taux_tva,
    montant_tva, montant_ttc, ordre_ligne, date_creation, date_modification
) values
(
    100, 100, 100, 'Prestation journaliere', null, 2.0000,
    'JOUR', 500.00, 0.0000, 0.00,
    1000.00, 0.00, 1000.00, 20.0000,
    200.00, 1200.00, 1, now(), now()
),
(
    101, 101, null, 'Prestation libre hors contrat', null, 3.0000,
    'JOUR', 100.00, 0.0000, 0.00,
    300.00, 0.00, 300.00, 20.0000,
    60.00, 360.00, 1, now(), now()
);

insert into ventilation_tva_facture (
    id, facture_id, taux_tva, base_ht, montant_tva,
    date_creation, date_modification
) values
(
    100, 100, 20.0000, 1000.00, 200.00,
    now(), now()
),
(
    101, 101, 20.0000, 300.00, 60.00,
    now(), now()
);

select setval(pg_get_serial_sequence('facture', 'id'), greatest((select max(id) from facture), 101), true);
select setval(pg_get_serial_sequence('ligne_facture', 'id'), greatest((select max(id) from ligne_facture), 101), true);
select setval(pg_get_serial_sequence('ventilation_tva_facture', 'id'), greatest((select max(id) from ventilation_tva_facture), 101), true);

commit;
