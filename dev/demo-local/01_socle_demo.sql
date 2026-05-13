begin;

insert into tenant (
    id, code, nom, statut, base_dediee, cle_base_donnee,
    date_creation, date_modification
) values (
    100, 'DEMO_WAVY_LOCAL', 'Wavy Demo Local', 'ACTIF', false, null,
    now(), now()
)
on conflict (id) do update set
    code = excluded.code,
    nom = excluded.nom,
    statut = excluded.statut,
    base_dediee = excluded.base_dediee,
    cle_base_donnee = excluded.cle_base_donnee,
    date_modification = now();

insert into societe_interne (
    id, tenant_id, raison_sociale, nom_commercial, numero_siren,
    numero_tva_intracommunautaire, forme_juridique, adresse_ligne_1,
    code_postal, ville, pays, email, telephone, actif,
    date_creation, date_modification
) values (
    100, 100, 'Wavy Demo Services', 'Wavy Demo Services', '982880312',
    'FR00982880312', 'SAS', '10 rue de la Demo',
    '75001', 'Paris', 'France', 'contact@wavy.local', '0100000000', true,
    now(), now()
)
on conflict (id) do update set
    tenant_id = excluded.tenant_id,
    raison_sociale = excluded.raison_sociale,
    nom_commercial = excluded.nom_commercial,
    numero_siren = excluded.numero_siren,
    numero_tva_intracommunautaire = excluded.numero_tva_intracommunautaire,
    forme_juridique = excluded.forme_juridique,
    adresse_ligne_1 = excluded.adresse_ligne_1,
    code_postal = excluded.code_postal,
    ville = excluded.ville,
    pays = excluded.pays,
    email = excluded.email,
    telephone = excluded.telephone,
    actif = excluded.actif,
    date_modification = now();

insert into utilisateur (
    id, tenant_id, email, nom, prenom, mot_de_passe_hash, actif,
    dernier_acces, date_creation, date_modification
) values (
    100, 100, 'demo@wavy.local', 'Demo', 'Fabrice', 'demo', true,
    null, now(), now()
)
on conflict (id) do update set
    tenant_id = excluded.tenant_id,
    email = excluded.email,
    nom = excluded.nom,
    prenom = excluded.prenom,
    mot_de_passe_hash = excluded.mot_de_passe_hash,
    actif = excluded.actif,
    date_modification = now();

insert into utilisateur_societe (
    id, tenant_id, utilisateur_id, societe_interne_id, societe_principale,
    actif, date_creation, date_modification
) values (
    100, 100, 100, 100, true,
    true, now(), now()
)
on conflict (id) do update set
    tenant_id = excluded.tenant_id,
    utilisateur_id = excluded.utilisateur_id,
    societe_interne_id = excluded.societe_interne_id,
    societe_principale = excluded.societe_principale,
    actif = excluded.actif,
    date_modification = now();

select setval(pg_get_serial_sequence('tenant', 'id'), greatest((select max(id) from tenant), 100), true);
select setval(pg_get_serial_sequence('societe_interne', 'id'), greatest((select max(id) from societe_interne), 100), true);
select setval(pg_get_serial_sequence('utilisateur', 'id'), greatest((select max(id) from utilisateur), 100), true);
select setval(pg_get_serial_sequence('utilisateur_societe', 'id'), greatest((select max(id) from utilisateur_societe), 100), true);

commit;
