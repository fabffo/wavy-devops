insert into tenant (id, code, nom, statut, base_dediee, cle_base_donnee, date_creation, date_modification)
values (100, 'DEMO_WAVY_LOCAL', 'Demo Wavy Local', 'ACTIF', false, null, now(), now())
on conflict (id) do update set code = excluded.code, nom = excluded.nom, statut = excluded.statut, date_modification = now();

insert into societe_interne (
    id, tenant_id, raison_sociale, nom_commercial, numero_siren, numero_tva_intracommunautaire,
    forme_juridique, adresse_ligne_1, code_postal, ville, pays, email, telephone, actif,
    date_creation, date_modification
) values (
    100, 100, 'Wavy Demo Services', 'Wavy Demo', '100200300', 'FR00100200300',
    'SAS', '10 rue de la Demo', '75001', 'Paris', 'France',
    'contact@demo.wavy.local', '0100000000', true, now(), now()
)
on conflict (id) do update set tenant_id = excluded.tenant_id, raison_sociale = excluded.raison_sociale, actif = true, date_modification = now();

insert into etablissement (
    id, tenant_id, societe_interne_id, numero_siret, adresse_ligne_1, code_postal,
    ville, pays, siege, actif, date_creation, date_modification
) values (
    100, 100, 100, '10020030000010', '10 rue de la Demo', '75001',
    'Paris', 'France', true, true, now(), now()
)
on conflict (id) do update set tenant_id = excluded.tenant_id, societe_interne_id = excluded.societe_interne_id, actif = true, date_modification = now();

insert into role (id, code, libelle) values
    (100, 'ADMIN_TENANT', 'Administrateur du tenant'),
    (101, 'GESTIONNAIRE', 'Gestionnaire')
on conflict (id) do update set code = excluded.code, libelle = excluded.libelle;

insert into utilisateur (
    id, tenant_id, nom, prenom, email, mot_de_passe_hash, actif,
    dernier_acces, date_creation, date_modification
) values
    (100, 100, 'Demo', 'Admin', 'admin.demo@wavy.local', 'motdepasse123', true, null, now(), now()),
    (101, 100, 'Demo', 'Gestionnaire', 'gestion.demo@wavy.local', 'motdepasse123', true, null, now(), now())
on conflict (id) do update set email = excluded.email, actif = true, date_modification = now();

insert into utilisateur_role (id, tenant_id, utilisateur_id, role_id, date_creation, date_modification)
values
    (100, 100, 100, 100, now(), now()),
    (101, 100, 100, 101, now(), now()),
    (102, 100, 101, 101, now(), now())
on conflict (id) do update set tenant_id = excluded.tenant_id, utilisateur_id = excluded.utilisateur_id, role_id = excluded.role_id, date_modification = now();

insert into utilisateur_societe (
    id, tenant_id, utilisateur_id, societe_interne_id, societe_principale,
    actif, date_creation, date_modification
) values
    (100, 100, 100, 100, true, true, now(), now()),
    (101, 100, 101, 100, true, true, now(), now())
on conflict (id) do update set actif = true, societe_principale = true, date_modification = now();

select setval(pg_get_serial_sequence('tenant', 'id'), greatest((select max(id) from tenant), 100), true);
select setval(pg_get_serial_sequence('societe_interne', 'id'), greatest((select max(id) from societe_interne), 100), true);
select setval(pg_get_serial_sequence('etablissement', 'id'), greatest((select max(id) from etablissement), 100), true);
select setval(pg_get_serial_sequence('role', 'id'), greatest((select max(id) from role), 101), true);
select setval(pg_get_serial_sequence('utilisateur', 'id'), greatest((select max(id) from utilisateur), 101), true);
select setval(pg_get_serial_sequence('utilisateur_role', 'id'), greatest((select max(id) from utilisateur_role), 102), true);
select setval(pg_get_serial_sequence('utilisateur_societe', 'id'), greatest((select max(id) from utilisateur_societe), 101), true);
