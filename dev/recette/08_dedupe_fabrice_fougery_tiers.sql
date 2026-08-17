-- Recette - fusion du doublon tiers Fabrice Fougery
-- Tiers conserve : 42 / fabrice.fougery@wavyservices.fr
-- Tiers supprime : 18 / fabrice.fougery@yopmail.com
-- Executer chaque section sur la base indiquee.

-- Base wavy_socle_db
BEGIN;
UPDATE utilisateur_tiers SET tiers_id = 42, date_modification = now() WHERE tiers_id = 18;
DO $$
DECLARE v_count integer;
BEGIN
  SELECT count(*) INTO v_count FROM utilisateur_tiers WHERE tiers_id = 18;
  IF v_count <> 0 THEN RAISE EXCEPTION 'References restantes socle.utilisateur_tiers: %', v_count; END IF;
END $$;
COMMIT;

-- Base wavy_contrats_db
BEGIN;
UPDATE contrat SET tiers_contractant_id = 42, date_modification = now() WHERE tiers_contractant_id = 18;
UPDATE reference_contrat SET tiers_affilie_id = 42, date_modification = now() WHERE tiers_affilie_id = 18;
DO $$
DECLARE v_count integer;
BEGIN
  SELECT count(*) INTO v_count FROM contrat WHERE tiers_contractant_id = 18;
  IF v_count <> 0 THEN RAISE EXCEPTION 'References restantes contrats.contrat: %', v_count; END IF;
  SELECT count(*) INTO v_count FROM reference_contrat WHERE tiers_affilie_id = 18;
  IF v_count <> 0 THEN RAISE EXCEPTION 'References restantes contrats.reference_contrat: %', v_count; END IF;
END $$;
COMMIT;

-- Base wavy_factures_db
BEGIN;
UPDATE abonnement_achat SET tiers_id = 42, date_modification = now() WHERE tiers_id = 18;
UPDATE audit_suppression_facture_achat SET fournisseur_id = 42 WHERE fournisseur_id = 18;
UPDATE budget_operation SET tiers_id = 42, date_modification = now() WHERE tiers_id = 18;
UPDATE budget_operation SET tiers_affilie_id = 42, date_modification = now() WHERE tiers_affilie_id = 18;
UPDATE compte_carte_entreprise SET porteur_tiers_id = 42 WHERE porteur_tiers_id = 18;
UPDATE devis_vente SET tiers_id = 42, date_modification = now() WHERE tiers_id = 18;
UPDATE facture SET tiers_id = 42, date_modification = now() WHERE tiers_id = 18;
UPDATE facture_achat SET tiers_id = 42, date_modification = now() WHERE tiers_id = 18;
UPDATE facture_achat SET marchand_tiers_id = 42, date_modification = now() WHERE marchand_tiers_id = 18;
UPDATE facture_achat SET porteur_carte_tiers_id = 42, date_modification = now() WHERE porteur_carte_tiers_id = 18;
UPDATE ligne_facture_achat SET tiers_affilie_id = 42 WHERE tiers_affilie_id = 18;
UPDATE ligne_note_frais SET marchand_tiers_id = 42 WHERE marchand_tiers_id = 18;
UPDATE note_frais SET beneficiaire_tiers_id = 42, date_modification = now() WHERE beneficiaire_tiers_id = 18;
UPDATE note_frais SET fournisseur_tiers_id = 42, date_modification = now() WHERE fournisseur_tiers_id = 18;
UPDATE note_frais SET marchand_tiers_id = 42, date_modification = now() WHERE marchand_tiers_id = 18;
UPDATE note_frais SET salarie_tiers_id = 42, date_modification = now() WHERE salarie_tiers_id = 18;
UPDATE regle_rapprochement_fournisseur SET tiers_id = 42, date_modification = now() WHERE tiers_id = 18;
UPDATE salaire SET salarie_tiers_id = 42, date_modification = now() WHERE salarie_tiers_id = 18;
DO $$
DECLARE v_count integer;
BEGIN
  SELECT count(*) INTO v_count FROM abonnement_achat WHERE tiers_id = 18;
  IF v_count <> 0 THEN RAISE EXCEPTION 'References restantes factures.abonnement_achat: %', v_count; END IF;
  SELECT count(*) INTO v_count FROM audit_suppression_facture_achat WHERE fournisseur_id = 18;
  IF v_count <> 0 THEN RAISE EXCEPTION 'References restantes factures.audit_suppression_facture_achat: %', v_count; END IF;
  SELECT count(*) INTO v_count FROM budget_operation WHERE tiers_id = 18 OR tiers_affilie_id = 18;
  IF v_count <> 0 THEN RAISE EXCEPTION 'References restantes factures.budget_operation: %', v_count; END IF;
  SELECT count(*) INTO v_count FROM compte_carte_entreprise WHERE porteur_tiers_id = 18;
  IF v_count <> 0 THEN RAISE EXCEPTION 'References restantes factures.compte_carte_entreprise: %', v_count; END IF;
  SELECT count(*) INTO v_count FROM devis_vente WHERE tiers_id = 18;
  IF v_count <> 0 THEN RAISE EXCEPTION 'References restantes factures.devis_vente: %', v_count; END IF;
  SELECT count(*) INTO v_count FROM facture WHERE tiers_id = 18;
  IF v_count <> 0 THEN RAISE EXCEPTION 'References restantes factures.facture: %', v_count; END IF;
  SELECT count(*) INTO v_count FROM facture_achat WHERE tiers_id = 18 OR marchand_tiers_id = 18 OR porteur_carte_tiers_id = 18;
  IF v_count <> 0 THEN RAISE EXCEPTION 'References restantes factures.facture_achat: %', v_count; END IF;
  SELECT count(*) INTO v_count FROM ligne_facture_achat WHERE tiers_affilie_id = 18;
  IF v_count <> 0 THEN RAISE EXCEPTION 'References restantes factures.ligne_facture_achat: %', v_count; END IF;
  SELECT count(*) INTO v_count FROM ligne_note_frais WHERE marchand_tiers_id = 18;
  IF v_count <> 0 THEN RAISE EXCEPTION 'References restantes factures.ligne_note_frais: %', v_count; END IF;
  SELECT count(*) INTO v_count FROM note_frais WHERE beneficiaire_tiers_id = 18 OR fournisseur_tiers_id = 18 OR marchand_tiers_id = 18 OR salarie_tiers_id = 18;
  IF v_count <> 0 THEN RAISE EXCEPTION 'References restantes factures.note_frais: %', v_count; END IF;
  SELECT count(*) INTO v_count FROM regle_rapprochement_fournisseur WHERE tiers_id = 18;
  IF v_count <> 0 THEN RAISE EXCEPTION 'References restantes factures.regle_rapprochement_fournisseur: %', v_count; END IF;
  SELECT count(*) INTO v_count FROM salaire WHERE salarie_tiers_id = 18;
  IF v_count <> 0 THEN RAISE EXCEPTION 'References restantes factures.salaire: %', v_count; END IF;
END $$;
COMMIT;

-- Base wavy_tresorerie_db
BEGIN;
UPDATE operation_bancaire SET tiers_id = 42, date_modification = now() WHERE tiers_id = 18;
UPDATE regle_rapprochement_bancaire SET tiers_id = 42, date_modification = now() WHERE tiers_id = 18;
DO $$
DECLARE v_count integer;
BEGIN
  SELECT count(*) INTO v_count FROM operation_bancaire WHERE tiers_id = 18;
  IF v_count <> 0 THEN RAISE EXCEPTION 'References restantes tresorerie.operation_bancaire: %', v_count; END IF;
  SELECT count(*) INTO v_count FROM regle_rapprochement_bancaire WHERE tiers_id = 18;
  IF v_count <> 0 THEN RAISE EXCEPTION 'References restantes tresorerie.regle_rapprochement_bancaire: %', v_count; END IF;
END $$;
COMMIT;

-- Base wavy_tiers_db
BEGIN;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM tiers WHERE id = 42 AND lower(email) = 'fabrice.fougery@wavyservices.fr') THEN
    RAISE EXCEPTION 'Tiers conserve introuvable ou inattendu: 42';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM tiers WHERE id = 18 AND lower(email) <> 'fabrice.fougery@wavyservices.fr') THEN
    RAISE EXCEPTION 'Tiers a supprimer introuvable ou inattendu: 18';
  END IF;
END $$;
UPDATE adresse_tiers SET tiers_id = 42, date_modification = now() WHERE tiers_id = 18;
UPDATE alias_marchand SET tiers_id = 42, date_modification = now() WHERE tiers_id = 18;
UPDATE contact_tiers SET tiers_id = 42, date_modification = now() WHERE tiers_id = 18;
UPDATE tiers_fonction SET tiers_id = 42, date_modification = now() WHERE tiers_id = 18;
UPDATE tiers_rattachement SET tiers_source_id = 42, date_modification = now() WHERE tiers_source_id = 18;
UPDATE tiers_rattachement SET tiers_cible_id = 42, date_modification = now() WHERE tiers_cible_id = 18;
INSERT INTO tiers_roles (tiers_id, role_tiers)
SELECT 42, role_tiers FROM tiers_roles old_roles
WHERE old_roles.tiers_id = 18
  AND NOT EXISTS (
    SELECT 1 FROM tiers_roles keep_roles
    WHERE keep_roles.tiers_id = 42 AND keep_roles.role_tiers = old_roles.role_tiers
  );
DELETE FROM tiers_roles WHERE tiers_id = 18;
DO $$
DECLARE v_count integer;
BEGIN
  SELECT count(*) INTO v_count FROM adresse_tiers WHERE tiers_id = 18;
  IF v_count <> 0 THEN RAISE EXCEPTION 'References restantes tiers.adresse_tiers: %', v_count; END IF;
  SELECT count(*) INTO v_count FROM alias_marchand WHERE tiers_id = 18;
  IF v_count <> 0 THEN RAISE EXCEPTION 'References restantes tiers.alias_marchand: %', v_count; END IF;
  SELECT count(*) INTO v_count FROM contact_tiers WHERE tiers_id = 18;
  IF v_count <> 0 THEN RAISE EXCEPTION 'References restantes tiers.contact_tiers: %', v_count; END IF;
  SELECT count(*) INTO v_count FROM tiers_fonction WHERE tiers_id = 18;
  IF v_count <> 0 THEN RAISE EXCEPTION 'References restantes tiers.tiers_fonction: %', v_count; END IF;
  SELECT count(*) INTO v_count FROM tiers_rattachement WHERE tiers_source_id = 18 OR tiers_cible_id = 18;
  IF v_count <> 0 THEN RAISE EXCEPTION 'References restantes tiers.tiers_rattachement: %', v_count; END IF;
  SELECT count(*) INTO v_count FROM tiers_roles WHERE tiers_id = 18;
  IF v_count <> 0 THEN RAISE EXCEPTION 'References restantes tiers.tiers_roles: %', v_count; END IF;
END $$;
DELETE FROM tiers WHERE id = 18;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM tiers WHERE id = 18) THEN
    RAISE EXCEPTION 'Le tiers 18 existe encore apres suppression';
  END IF;
END $$;
COMMIT;
