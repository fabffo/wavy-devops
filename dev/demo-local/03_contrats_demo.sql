begin;

delete from piece_jointe_contrat where contrat_id = 100;
delete from reference_contrat where id = 100 or contrat_id = 100;
delete from contrat where id = 100;

insert into contrat (
    id, tenant_id, societe_interne_id, tiers_contractant_id, type_contrat,
    statut_contrat, numero_contrat, libelle, description, date_debut,
    date_fin, date_creation, date_modification
) values (
    100, 100, 100, 100, 'CLIENT',
    'ACTIF', 'CTR-DEMO-2026-001', 'Contrat demo client',
    'Contrat demo client pour validation locale Wavy', '2026-01-01',
    null, now(), now()
);

insert into reference_contrat (
    id, contrat_id, libelle, prix_unitaire_ht, taux_tva, tiers_affilie_id,
    actif, date_creation, date_modification
) values (
    100, 100, 'Prestation journaliere', 500.00, 20.0, null,
    true, now(), now()
);

select setval(pg_get_serial_sequence('contrat', 'id'), greatest((select max(id) from contrat), 100), true);
select setval(pg_get_serial_sequence('reference_contrat', 'id'), greatest((select max(id) from reference_contrat), 100), true);

commit;
