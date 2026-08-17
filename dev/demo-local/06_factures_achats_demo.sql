begin;

delete from rapprochement_budget_reel where id between 300 and 304;
delete from budget_echeance where id between 300 and 304 or budget_operation_id between 300 and 304 or budget_scenario_id = 300;
delete from budget_operation where id between 300 and 304 or budget_scenario_id = 300;
delete from budget_scenario where id = 300;

delete from ligne_abonnement_achat where id between 300 and 304 or abonnement_achat_id between 300 and 304;
delete from abonnement_achat where id between 300 and 304;

delete from ventilation_tva_facture_achat where facture_achat_id in (200, 201) or facture_achat_id between 300 and 304;
delete from ligne_facture_achat where facture_achat_id in (200, 201) or facture_achat_id between 300 and 304;
delete from facture_achat where id in (200, 201) or id between 300 and 304;

insert into facture_achat (
    id, tenant_id, societe_interne_id, utilisateur_createur_id,
    tiers_id, contrat_id,
    categorie_achat, statut_facture_achat, origine_facture_achat, statut_paiement,
    numero_facture_fournisseur, numero_interne_achat,
    date_facture, date_emission, date_reception, date_echeance,
    fournisseur_nom, libelle, devise, regime_tva, option_tva_sur_les_debits, mode_paiement,
    total_ht, total_remise, total_tva, total_ttc, montant_deja_paye, reste_a_payer,
    acheteur_nom, acheteur_pays, date_creation, date_modification
) values
(200, 100, 100, 100, 101, null, 'ACHAT_EXPLOITATION', 'BROUILLON', 'MANUELLE', 'NON_PAYEE', 'PRESTA-2026-001', 'ACH-2026-100-000001', '2026-01-10', '2026-01-10', '2026-01-11', '2026-02-10', 'Prestataire Demo SAS', 'Sous-traitance mission client', 'EUR', 'TVA_STANDARD', false, 'VIREMENT', 1000.00, 0.00, 200.00, 1200.00, 0.00, 1200.00, 'Societe Wavy Demo', 'FR', now(), now()),
(201, 100, 100, 100, null, null, 'FRAIS_GENERAUX', 'BROUILLON', 'MANUELLE', 'NON_PAYEE', 'OVH-2026-001', 'ACH-2026-100-000002', '2026-01-15', '2026-01-15', '2026-01-16', '2026-02-15', 'OVH', 'Hebergement cloud', 'EUR', 'TVA_STANDARD', false, 'VIREMENT', 100.00, 0.00, 20.00, 120.00, 0.00, 120.00, 'Societe Wavy Demo', 'FR', now(), now()),
(300, 100, 100, 100, 106, null, 'FRAIS_GENERAUX', 'VALIDEE', 'EXTRACTION_IA', 'NON_PAYEE', 'OVH-2026-05-REAL', 'ACH-2026-100-000300', '2026-05-06', '2026-05-06', '2026-05-07', '2026-05-21', 'OVHcloud', 'Facture reelle OVH - 05/2026', 'EUR', 'TVA_STANDARD', false, 'VIREMENT', 100.00, 0.00, 20.00, 120.00, 0.00, 120.00, 'Societe Wavy Demo', 'FR', now(), now()),
(301, 100, 100, 100, 107, null, 'FRAIS_GENERAUX', 'VALIDEE', 'EXTRACTION_IA', 'NON_PAYEE', 'MS365-2026-05-REAL', 'ACH-2026-100-000301', '2026-05-08', '2026-05-08', '2026-05-09', '2026-05-23', 'Microsoft France SAS', 'Facture reelle Microsoft 365 - 05/2026', 'EUR', 'TVA_STANDARD', false, 'VIREMENT', 87.50, 0.00, 17.50, 105.00, 0.00, 105.00, 'Societe Wavy Demo', 'FR', now(), now()),
(302, 100, 100, 100, 109, null, 'FRAIS_GENERAUX', 'VALIDEE', 'EXTRACTION_IA', 'NON_PAYEE', 'TEL-2026-05-REAL', 'ACH-2026-100-000302', '2026-05-12', '2026-05-12', '2026-05-13', '2026-05-27', 'Telecom Demo SAS', 'Facture reelle telephonie - 05/2026', 'EUR', 'TVA_STANDARD', false, 'VIREMENT', 50.00, 0.00, 10.00, 60.00, 0.00, 60.00, 'Societe Wavy Demo', 'FR', now(), now());

insert into ligne_facture_achat (
    id, facture_achat_id, reference_contrat_id, libelle, quantite, unite, prix_unitaire_ht,
    remise_pourcentage, remise_montant, montant_ht_avant_remise, montant_remise,
    montant_ht, taux_tva, montant_tva, montant_ttc, ordre_ligne, date_creation, date_modification
) values
(200, 200, null, 'Sous-traitance mission client', 1, 'UNITE', 1000.00, 0, 0, 1000.00, 0.00, 1000.00, 20, 200.00, 1200.00, 1, now(), now()),
(201, 201, null, 'Hebergement cloud', 1, 'MOIS', 100.00, 0, 0, 100.00, 0.00, 100.00, 20, 20.00, 120.00, 1, now(), now()),
(300, 300, null, 'Hebergement cloud OVH reel', 1, 'MOIS', 100.00, 0, 0, 100.00, 0.00, 100.00, 20, 20.00, 120.00, 1, now(), now()),
(301, 301, null, 'Licence Microsoft 365 reelle', 1, 'MOIS', 87.50, 0, 0, 87.50, 0.00, 87.50, 20, 17.50, 105.00, 1, now(), now()),
(302, 302, null, 'Forfait telephonie reel', 1, 'MOIS', 50.00, 0, 0, 50.00, 0.00, 50.00, 20, 10.00, 60.00, 1, now(), now());

insert into ventilation_tva_facture_achat (
    id, facture_achat_id, taux_tva, base_ht, montant_tva, date_creation, date_modification
) values
(200, 200, 20, 1000.00, 200.00, now(), now()),
(201, 201, 20, 100.00, 20.00, now(), now()),
(300, 300, 20, 100.00, 20.00, now(), now()),
(301, 301, 20, 87.50, 17.50, now(), now()),
(302, 302, 20, 50.00, 10.00, now(), now());

insert into abonnement_achat (
    id, tenant_id, societe_interne_id, utilisateur_createur_id, tiers_id, contrat_id,
    libelle, description, categorie_achat, devise, regime_tva, mode_paiement, conditions_reglement,
    periodicite, type_montant, montant_ht, taux_tva, montant_tva, montant_ttc,
    jour_facturation, jour_echeance, date_debut, date_fin, actif, commentaire,
    date_creation, date_modification
) values
(300, 100, 100, 100, 106, null, 'Abonnement OVH mensuel', 'Source de budget mensuel OVH.', 'FRAIS_GENERAUX', 'EUR', 'TVA_STANDARD', 'VIREMENT', 'Paiement a reception', 'MENSUEL', 'FIXE', 100.00, 20.0000, 20.00, 120.00, 5, 20, '2026-01-01', null, true, 'Budgetise, pas facture estimee.', now(), now()),
(301, 100, 100, 100, 107, null, 'Licence Microsoft 365', 'Source de budget mensuel Microsoft 365.', 'FRAIS_GENERAUX', 'EUR', 'TVA_STANDARD', 'VIREMENT', 'Paiement a reception', 'MENSUEL', 'FIXE', 83.33, 20.0000, 16.67, 100.00, 5, 20, '2026-01-01', null, true, 'Budgetise avec ecart reel en mai.', now(), now()),
(302, 100, 100, 100, 108, null, 'Assurance annuelle responsabilite civile', 'Source de budget annuel assurance.', 'FRAIS_GENERAUX', 'EUR', 'TVA_STANDARD', 'VIREMENT', 'Paiement a reception', 'ANNUEL', 'FIXE', 1000.00, 20.0000, 200.00, 1200.00, 10, 30, '2026-01-01', null, true, 'Budget annuel sans facture recue.', now(), now()),
(303, 100, 100, 100, 109, null, 'Telephonie mobile', 'Source de budget mensuel telephonie.', 'FRAIS_GENERAUX', 'EUR', 'TVA_STANDARD', 'VIREMENT', 'Paiement a reception', 'MENSUEL', 'FIXE', 50.00, 20.0000, 10.00, 60.00, 5, 20, '2026-01-01', null, true, 'Facture reelle rapprochable au budget.', now(), now());

insert into ligne_abonnement_achat (
    id, abonnement_achat_id, libelle, description, quantite, unite, prix_unitaire_ht,
    taux_tva, montant_ht, montant_tva, montant_ttc, ordre_ligne, variable,
    date_creation, date_modification
) values
(300, 300, 'Hebergement cloud OVH', null, 1, 'MOIS', 100.00, 20.0000, 100.00, 20.00, 120.00, 1, false, now(), now()),
(301, 301, 'Licence Microsoft 365 Business', null, 1, 'MOIS', 83.33, 20.0000, 83.33, 16.67, 100.00, 1, false, now(), now()),
(302, 302, 'Assurance responsabilite civile', null, 1, 'UNITE', 1000.00, 20.0000, 1000.00, 200.00, 1200.00, 1, false, now(), now()),
(303, 303, 'Forfait telephonie mobile', null, 1, 'MOIS', 50.00, 20.0000, 50.00, 10.00, 60.00, 1, false, now(), now());

insert into budget_scenario (
    id, tenant_id, societe_interne_id, libelle, annee, version, statut,
    date_debut, date_fin, actif, commentaire, utilisateur_createur_id, date_creation, date_modification
) values
(300, 100, 100, 'Budget exploitation 2026', 2026, 1, 'VALIDE', '2026-01-01', '2026-12-31', true, 'Scenario demo issu de la refonte budget/reel.', 100, now(), now());

insert into budget_operation (
    id, budget_scenario_id, tenant_id, societe_interne_id, sens, type_operation, categorie,
    libelle, description, tiers_id, abonnement_achat_id, periodicite, date_debut, date_fin,
    montant_ht, montant_tva, montant_ttc, devise, mode_calcul, actif, commentaire,
    utilisateur_createur_id, date_creation, date_modification
) values
(300, 300, 100, 100, 'ACHAT', 'ABONNEMENT', 'FRAIS_GENERAUX', 'Budget OVH mensuel', 'Prevision issue de l abonnement OVH.', 106, 300, 'MENSUELLE', '2026-01-01', null, 100.00, 20.00, 120.00, 'EUR', 'MONTANT_FIXE', true, null, 100, now(), now()),
(301, 300, 100, 100, 'ACHAT', 'ABONNEMENT', 'FRAIS_GENERAUX', 'Budget Microsoft 365', 'Prevision issue de l abonnement Microsoft 365.', 107, 301, 'MENSUELLE', '2026-01-01', null, 83.33, 16.67, 100.00, 'EUR', 'MONTANT_FIXE', true, null, 100, now(), now()),
(302, 300, 100, 100, 'ACHAT', 'ASSURANCE', 'FRAIS_GENERAUX', 'Budget assurance annuelle', 'Prevision annuelle assurance.', 108, 302, 'ANNUELLE', '2026-01-10', null, 1000.00, 200.00, 1200.00, 'EUR', 'MONTANT_FIXE', true, null, 100, now(), now()),
(303, 300, 100, 100, 'ACHAT', 'ABONNEMENT', 'FRAIS_GENERAUX', 'Budget telephonie', 'Prevision issue de l abonnement telephonie.', 109, 303, 'MENSUELLE', '2026-01-01', null, 50.00, 10.00, 60.00, 'EUR', 'MONTANT_FIXE', true, null, 100, now(), now());

insert into budget_echeance (
    id, budget_operation_id, budget_scenario_id, tenant_id, societe_interne_id,
    periode_annee, periode_mois, date_prevue,
    montant_ht_prevu, montant_tva_prevu, montant_ttc_prevu,
    devise, statut, source_generation, utilisateur_createur_id, date_creation, date_modification
) values
(300, 300, 300, 100, 100, 2026, 5, '2026-05-05', 100.00, 20.00, 120.00, 'EUR', 'REALISEE', 'ABONNEMENT', 100, now(), now()),
(301, 301, 300, 100, 100, 2026, 5, '2026-05-05', 83.33, 16.67, 100.00, 'EUR', 'REALISEE', 'ABONNEMENT', 100, now(), now()),
(302, 302, 300, 100, 100, 2026, 1, '2026-01-10', 1000.00, 200.00, 1200.00, 'EUR', 'PREVUE', 'ABONNEMENT', 100, now(), now()),
(303, 303, 300, 100, 100, 2026, 5, '2026-05-05', 50.00, 10.00, 60.00, 'EUR', 'REALISEE', 'ABONNEMENT', 100, now(), now());

insert into rapprochement_budget_reel (
    id, tenant_id, societe_interne_id, budget_echeance_id, type_element_reel, element_reel_id,
    statut, type_rapprochement, score, montant_prevu_ht, montant_reel_ht,
    montant_prevu_tva, montant_reel_tva, montant_prevu_ttc, montant_reel_ttc,
    ecart_ht, ecart_tva, ecart_ttc, ecart_pourcentage, ecart_date_jours,
    commentaire, utilisateur_rapprochement_id, utilisateur_confirmation_id,
    date_rapprochement, date_confirmation, date_creation, date_modification
) values
(300, 100, 100, 300, 'FACTURE_ACHAT', 300, 'RAPPROCHE', 'AUTOMATIQUE', 100, 100.00, 100.00, 20.00, 20.00, 120.00, 120.00, 0.00, 0.00, 0.00, 0.00, 1, 'OVH rapproche sans ecart.', 100, 100, now(), now(), now(), now()),
(301, 100, 100, 301, 'FACTURE_ACHAT', 301, 'RAPPROCHE_AVEC_ECART', 'AUTOMATIQUE', 92, 83.33, 87.50, 16.67, 17.50, 100.00, 105.00, 4.17, 0.83, 5.00, 5.00, 3, 'Microsoft rapproche avec ecart TTC de 5 EUR.', 100, null, now(), null, now(), now()),
(302, 100, 100, 303, 'FACTURE_ACHAT', 302, 'RAPPROCHE', 'AUTOMATIQUE', 98, 50.00, 50.00, 10.00, 10.00, 60.00, 60.00, 0.00, 0.00, 0.00, 0.00, 7, 'Telephonie rapprochee au budget.', 100, 100, now(), now(), now(), now());

select setval(pg_get_serial_sequence('abonnement_achat', 'id'), greatest((select max(id) from abonnement_achat), 303), true);
select setval(pg_get_serial_sequence('ligne_abonnement_achat', 'id'), greatest((select max(id) from ligne_abonnement_achat), 303), true);
select setval(pg_get_serial_sequence('budget_scenario', 'id'), greatest((select max(id) from budget_scenario), 300), true);
select setval(pg_get_serial_sequence('budget_operation', 'id'), greatest((select max(id) from budget_operation), 303), true);
select setval(pg_get_serial_sequence('budget_echeance', 'id'), greatest((select max(id) from budget_echeance), 303), true);
select setval(pg_get_serial_sequence('rapprochement_budget_reel', 'id'), greatest((select max(id) from rapprochement_budget_reel), 302), true);
select setval(pg_get_serial_sequence('facture_achat', 'id'), greatest((select max(id) from facture_achat), 302), true);
select setval(pg_get_serial_sequence('ligne_facture_achat', 'id'), greatest((select max(id) from ligne_facture_achat), 302), true);
select setval(pg_get_serial_sequence('ventilation_tva_facture_achat', 'id'), greatest((select max(id) from ventilation_tva_facture_achat), 302), true);

commit;
