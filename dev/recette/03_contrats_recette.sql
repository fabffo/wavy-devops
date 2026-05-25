begin;

insert into contrat (
    id, tenant_id, societe_interne_id, tiers_contractant_id, type_contrat,
    statut_contrat, numero_contrat, libelle, description, date_debut,
    date_fin, date_creation, date_modification
) values
(
    4,
    3,
    4,
    4,
    'CLIENT',
    'ACTIF',
    'CTR-REC-2026-001',
    'Contrat Alpha',
    'Contrat Alpha pour le client Alpha Industrie SAS',
    '2026-05-01',
    null,
    now(),
    now()
),
(
    5,
    3,
    4,
    5,
    'CLIENT',
    'ACTIF',
    'CTR-REC-2026-002',
    'Contrat Beta',
    'Contrat Beta pour le client Beta Distribution SAS',
    '2026-05-01',
    null,
    now(),
    now()
)
on conflict (id) do update set
    tenant_id = excluded.tenant_id,
    societe_interne_id = excluded.societe_interne_id,
    tiers_contractant_id = excluded.tiers_contractant_id,
    type_contrat = excluded.type_contrat,
    statut_contrat = excluded.statut_contrat,
    numero_contrat = excluded.numero_contrat,
    libelle = excluded.libelle,
    description = excluded.description,
    date_debut = excluded.date_debut,
    date_fin = excluded.date_fin,
    date_modification = now();

insert into reference_contrat (
    id, contrat_id, libelle, prix_unitaire_ht, taux_tva, tiers_affilie_id,
    actif, date_creation, date_modification
) values
(
    4,
    4,
    'Prestation journalière',
    500.00,
    20.0,
    null,
    true,
    now(),
    now()
),
(
    5,
    5,
    'Prestation journalière',
    500.00,
    20.0,
    null,
    true,
    now(),
    now()
)
on conflict (id) do update set
    contrat_id = excluded.contrat_id,
    libelle = excluded.libelle,
    prix_unitaire_ht = excluded.prix_unitaire_ht,
    taux_tva = excluded.taux_tva,
    tiers_affilie_id = excluded.tiers_affilie_id,
    actif = excluded.actif,
    date_modification = now();

select setval(pg_get_serial_sequence('contrat', 'id'), greatest((select max(id) from contrat), 5), true);
select setval(pg_get_serial_sequence('reference_contrat', 'id'), greatest((select max(id) from reference_contrat), 5), true);

commit;
