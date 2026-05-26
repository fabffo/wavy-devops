insert into facture (
    id, tenant_id, societe_interne_id, utilisateur_createur_id, sens_facture, type_facture,
    nature_facture, categorie_operation, statut_facture, statut_electronique, format_electronique,
    tiers_id, contrat_id, numero_facture, date_emission, date_facture, date_prestation_ou_vente,
    date_echeance, libelle, devise, vendeur_nom, vendeur_pays, client_nom, client_siren,
    regime_tva, option_tva_sur_les_debits, total_ht, total_remise, total_tva, total_ttc,
    netapayer, montant_deja_paye, resteapayer, mode_paiement, indemnite_forfaitaire_recouvrement,
    date_creation, date_modification
) values
    (100, 100, 100, 100, 'VENTE', 'FACTURE_DOIT', 'SERVICE', 'PRESTATION_SERVICES', 'BROUILLON', 'NON_TRANSMISE', 'AUCUN', 100, 100, 'FA-2026-100-000001', '2026-05-12', '2026-05-12', '2026-05-12', '2026-06-11', 'Maintenance Alpha mai 2026', 'EUR', 'Wavy Demo Services', 'FR', 'Alpha Industrie SAS', '910000001', 'TVA_STANDARD', false, 1000.00, 0.00, 200.00, 1200.00, 1200.00, 0.00, 1200.00, 'VIREMENT', 40.00, now(), now()),
    (101, 100, 100, 101, 'VENTE', 'FACTURE_DOIT', 'SERVICE', 'PRESTATION_SERVICES', 'VALIDEE', 'NON_TRANSMISE', 'AUCUN', 101, 101, 'FA-2026-100-000002', '2026-05-12', '2026-05-12', '2026-05-12', '2026-06-11', 'Support Beta mai 2026', 'EUR', 'Wavy Demo Services', 'FR', 'Beta Distribution SAS', '910000002', 'TVA_STANDARD', false, 1000.00, 0.00, 200.00, 1200.00, 1200.00, 0.00, 1200.00, 'VIREMENT', 40.00, now(), now())
on conflict do nothing;

insert into ligne_facture (
    id, facture_id, reference_contrat_id, libelle, quantite, unite, prix_unitaire_ht,
    remise_pourcentage, remise_montant, montant_ht_avant_remise, montant_remise, montant_ht,
    taux_tva, montant_tva, montant_ttc, ordre_ligne, date_creation, date_modification
) values
    (100, 100, 100, 'Forfait maintenance mensuelle', 1.0000, 'FORFAIT', 1000.00, 0.0000, 0.00, 1000.00, 0.00, 1000.00, 20.0000, 200.00, 1200.00, 1, now(), now()),
    (101, 101, 101, 'Support Beta - 2 journees', 2.0000, 'JOUR', 500.00, 0.0000, 0.00, 1000.00, 0.00, 1000.00, 20.0000, 200.00, 1200.00, 1, now(), now())
on conflict do nothing;

insert into ventilation_tva_facture (
    id, facture_id, taux_tva, base_ht, montant_tva, date_creation, date_modification
) values
    (100, 100, 20.0000, 1000.00, 200.00, now(), now()),
    (101, 101, 20.0000, 1000.00, 200.00, now(), now())
on conflict do nothing;

alter table facture alter column id restart with 102;
alter table ligne_facture alter column id restart with 102;
alter table ventilation_tva_facture alter column id restart with 102;
