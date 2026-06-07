begin;

insert into parametre_ligne_salaire (
    tenant_id, societe_interne_id, code_ligne, libelle, type_ligne, sens,
    ordre_affichage, obligatoire, actif, date_creation, date_modification
)
select 100, null, 'BRUT', 'Brut', 'BRUT', 'PLUS', 10, true, true, now(), now()
where not exists (
    select 1 from parametre_ligne_salaire
    where tenant_id = 100 and societe_interne_id is null and code_ligne = 'BRUT'
);

insert into parametre_ligne_salaire (
    tenant_id, societe_interne_id, code_ligne, libelle, type_ligne, sens,
    ordre_affichage, obligatoire, actif, date_creation, date_modification
)
select 100, null, 'CHARGES_SALARIALES', 'Charges salariales', 'CHARGE_SALARIALE', 'MOINS', 20, true, true, now(), now()
where not exists (
    select 1 from parametre_ligne_salaire
    where tenant_id = 100 and societe_interne_id is null and code_ligne = 'CHARGES_SALARIALES'
);

insert into parametre_ligne_salaire (
    tenant_id, societe_interne_id, code_ligne, libelle, type_ligne, sens,
    ordre_affichage, obligatoire, actif, date_creation, date_modification
)
select 100, null, 'CHARGES_PATRONNALES', 'Charges patronales', 'CHARGE_PATRONALE', 'PLUS', 30, true, true, now(), now()
where not exists (
    select 1 from parametre_ligne_salaire
    where tenant_id = 100 and societe_interne_id is null and code_ligne = 'CHARGES_PATRONNALES'
);

insert into parametre_ligne_salaire (
    tenant_id, societe_interne_id, code_ligne, libelle, type_ligne, sens,
    ordre_affichage, obligatoire, actif, date_creation, date_modification
)
select 100, null, 'NET_A_PAYER_AVANT_IMPOT', 'Net a payer avant impot', 'NET', 'NEUTRE', 40, true, true, now(), now()
where not exists (
    select 1 from parametre_ligne_salaire
    where tenant_id = 100 and societe_interne_id is null and code_ligne = 'NET_A_PAYER_AVANT_IMPOT'
);

insert into parametre_ligne_salaire (
    tenant_id, societe_interne_id, code_ligne, libelle, type_ligne, sens,
    ordre_affichage, obligatoire, actif, date_creation, date_modification
)
select 100, null, 'NET_A_PAYER', 'Net a payer', 'NET', 'NEUTRE', 50, true, true, now(), now()
where not exists (
    select 1 from parametre_ligne_salaire
    where tenant_id = 100 and societe_interne_id is null and code_ligne = 'NET_A_PAYER'
);

delete from ligne_salaire where salaire_id in (300, 301);
delete from salaire where id in (300, 301);

insert into salaire (
    id, tenant_id, societe_interne_id, utilisateur_createur_id,
    salarie_tiers_id, salarie_nom, salarie_prenom, matricule,
    periode_mois, periode_annee, date_saisie, date_validation, date_annulation,
    statut_salaire, devise, commentaire,
    total_brut, total_charges_salariales, total_charges_patronales,
    net_a_payer_avant_impot, net_a_payer, cout_total_employeur,
    date_creation, date_modification
) values
    (300, 100, 100, 100,
     102, 'Dupont', 'Jean', 'SAL-001',
     1, 2026, current_date, null, null,
     'BROUILLON', 'EUR', 'Salaire de demo en brouillon',
     3000.00, 700.00, 1200.00,
     2300.00, 2200.00, 4200.00,
     now(), now()),
    (301, 100, 100, 100,
     103, 'Martin', 'Claire', 'SAL-002',
     12, 2025, current_date, now(), null,
     'VALIDE', 'EUR', 'Salaire de demo valide',
     3200.00, 760.00, 1280.00,
     2440.00, 2350.00, 4480.00,
     now(), now());

insert into ligne_salaire (
    id, salaire_id, code_ligne, libelle, type_ligne, sens,
    montant, ordre_ligne, obligatoire, commentaire, date_creation, date_modification
) values
    (3000, 300, 'BRUT', 'Brut', 'BRUT', 'PLUS', 3000.00, 10, true, null, now(), now()),
    (3001, 300, 'CHARGES_SALARIALES', 'Charges salariales', 'CHARGE_SALARIALE', 'MOINS', 700.00, 20, true, null, now(), now()),
    (3002, 300, 'CHARGES_PATRONNALES', 'Charges patronales', 'CHARGE_PATRONALE', 'PLUS', 1200.00, 30, true, null, now(), now()),
    (3003, 300, 'NET_A_PAYER_AVANT_IMPOT', 'Net a payer avant impot', 'NET', 'NEUTRE', 2300.00, 40, true, null, now(), now()),
    (3004, 300, 'NET_A_PAYER', 'Net a payer', 'NET', 'NEUTRE', 2200.00, 50, true, null, now(), now()),
    (3005, 301, 'BRUT', 'Brut', 'BRUT', 'PLUS', 3200.00, 10, true, null, now(), now()),
    (3006, 301, 'CHARGES_SALARIALES', 'Charges salariales', 'CHARGE_SALARIALE', 'MOINS', 760.00, 20, true, null, now(), now()),
    (3007, 301, 'CHARGES_PATRONNALES', 'Charges patronales', 'CHARGE_PATRONALE', 'PLUS', 1280.00, 30, true, null, now(), now()),
    (3008, 301, 'NET_A_PAYER_AVANT_IMPOT', 'Net a payer avant impot', 'NET', 'NEUTRE', 2440.00, 40, true, null, now(), now()),
    (3009, 301, 'NET_A_PAYER', 'Net a payer', 'NET', 'NEUTRE', 2350.00, 50, true, null, now(), now());

select setval(pg_get_serial_sequence('salaire', 'id'), greatest((select max(id) from salaire), 301), true);
select setval(pg_get_serial_sequence('ligne_salaire', 'id'), greatest((select max(id) from ligne_salaire), 3009), true);

commit;
