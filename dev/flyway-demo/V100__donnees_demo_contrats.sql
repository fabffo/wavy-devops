insert into contrat (
    id, tenant_id, societe_interne_id, tiers_contractant_id, type_contrat,
    statut_contrat, numero_contrat, libelle, description, date_debut,
    date_fin, date_creation, date_modification
) values
    (100, 100, 100, 100, 'CLIENT', 'ACTIF', 'CTR-DEMO-ALPHA-001', 'Maintenance Alpha', 'Contrat de maintenance mensuelle Alpha', '2026-01-01', '2026-12-31', now(), now()),
    (101, 100, 100, 101, 'CLIENT', 'ACTIF', 'CTR-DEMO-BETA-001', 'Support Beta', 'Contrat de support Beta', '2026-01-01', null, now(), now())
on conflict (id) do update set libelle = excluded.libelle, statut_contrat = excluded.statut_contrat, date_modification = now();

insert into reference_contrat (
    id, contrat_id, libelle, prix_unitaire_ht, taux_tva, tiers_affilie_id,
    actif, date_creation, date_modification
) values
    (100, 100, 'Forfait maintenance mensuelle', 1000.00, 20.0, 100, true, now(), now()),
    (101, 101, 'Journee de support', 500.00, 20.0, 101, true, now(), now())
on conflict (id) do update set libelle = excluded.libelle, prix_unitaire_ht = excluded.prix_unitaire_ht, actif = true, date_modification = now();

select setval(pg_get_serial_sequence('contrat', 'id'), greatest((select max(id) from contrat), 101), true);
select setval(pg_get_serial_sequence('reference_contrat', 'id'), greatest((select max(id) from reference_contrat), 101), true);
