delete from ventilation_tva_facture_achat where facture_achat_id in (200, 201);
delete from ligne_facture_achat where facture_achat_id in (200, 201);
delete from facture_achat where id in (200, 201);

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
(200, 3, 4, 6, 7, null, 'ACHAT_EXPLOITATION', 'BROUILLON', 'MANUELLE', 'NON_PAYEE', 'PRESTA-REC-2026-001', 'ACH-2026-4-000001', '2026-01-10', '2026-01-10', '2026-01-11', '2026-02-10', 'ESN Delta Consulting SAS', 'Sous-traitance mission client', 'EUR', 'TVA_STANDARD', false, 'VIREMENT', 1000.00, 0.00, 200.00, 1200.00, 0.00, 1200.00, 'Societe Wavy Demo', 'FR', now(), now()),
(201, 3, 4, 6, null, null, 'FRAIS_GENERAUX', 'BROUILLON', 'MANUELLE', 'NON_PAYEE', 'OVH-REC-2026-001', 'ACH-2026-4-000002', '2026-01-15', '2026-01-15', '2026-01-16', '2026-02-15', 'OVH', 'Hébergement cloud', 'EUR', 'TVA_STANDARD', false, 'VIREMENT', 100.00, 0.00, 20.00, 120.00, 0.00, 120.00, 'Societe Wavy Demo', 'FR', now(), now());

insert into ligne_facture_achat (
    id, facture_achat_id, reference_contrat_id, libelle, quantite, unite, prix_unitaire_ht,
    remise_pourcentage, remise_montant, montant_ht_avant_remise, montant_remise,
    montant_ht, taux_tva, montant_tva, montant_ttc, ordre_ligne, date_creation, date_modification
) values
(200, 200, null, 'Sous-traitance mission client', 1, 'UNITE', 1000.00, 0, 0, 1000.00, 0.00, 1000.00, 20, 200.00, 1200.00, 1, now(), now()),
(201, 201, null, 'Hébergement cloud', 1, 'MOIS', 100.00, 0, 0, 100.00, 0.00, 100.00, 20, 20.00, 120.00, 1, now(), now());

insert into ventilation_tva_facture_achat (
    id, facture_achat_id, taux_tva, base_ht, montant_tva, date_creation, date_modification
) values
(200, 200, 20, 1000.00, 200.00, now(), now()),
(201, 201, 20, 100.00, 20.00, now(), now());

select setval(pg_get_serial_sequence('facture_achat', 'id'), greatest((select max(id) from facture_achat), 201), true);
select setval(pg_get_serial_sequence('ligne_facture_achat', 'id'), greatest((select max(id) from ligne_facture_achat), 201), true);
select setval(pg_get_serial_sequence('ventilation_tva_facture_achat', 'id'), greatest((select max(id) from ventilation_tva_facture_achat), 201), true);
