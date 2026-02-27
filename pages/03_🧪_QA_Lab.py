"""
PAGE 3 — QA Lab v3
Centre de validation des données extraites (Triage)
et Gestionnaire des Règles (RuleMatrix).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
from datetime import datetime

from core.models import SessionLocal, OffreRetail, RuleMatrix, ProduitReference
from sqlalchemy import case

st.set_page_config(
    page_title="QA Lab | STAFF v3",
    page_icon="🧪",
    layout="wide",
)

st.title("🧪 QA Lab — Contrôle Qualité & Matrice")
st.caption("Validez les anomalies d'extraction et gérez les règles de stacking global.")

tab_triage, tab_matrice = st.tabs([
    "🚦 Centre de Triage",
    "📜 Matrice des Promos",
])

with tab_triage:
    st.subheader("🚦 File d'attente QA")

    db = SessionLocal()
    try:
        sort_logic = case(
            (OffreRetail.qa_status == 'ERROR', 1),
            (OffreRetail.qa_status == 'FLAGGED', 2),
            (OffreRetail.qa_status == 'PENDING', 3),
            else_=4
        )

        offres_qa = db.query(OffreRetail, ProduitReference).join(
            ProduitReference, OffreRetail.ean == ProduitReference.ean, isouter=True
        ).filter(
            OffreRetail.qa_status.in_(['ERROR', 'FLAGGED', 'PENDING']),
            OffreRetail.is_active == True
        ).order_by(sort_logic, OffreRetail.timestamp.desc()).all()

        if not offres_qa:
            st.success("🎉 File d'attente vide. Tout est validé !")
        else:
            c_err, c_flag, c_pend = st.columns(3)
            counts = {"ERROR": 0, "FLAGGED": 0, "PENDING": 0}
            for o, p in offres_qa:
                counts[o.qa_status] = counts.get(o.qa_status, 0) + 1
            
            c_err.metric("🔴 Erreurs", counts["ERROR"])
            c_flag.metric("🟠 Doutes (Flagged)", counts["FLAGGED"])
            c_pend.metric("🔵 En attente", counts["PENDING"])

            st.divider()

            col_list, col_inspect = st.columns([1.2, 1])
            offre_objects = {o.id: (o, p) for o, p in offres_qa}

            with col_list:
                st.markdown("#### 📋 File d'attente & Bulk Validation")
                rows = []
                for o, p in offres_qa:
                    nom_ref = p.nom_genere if p else "Inconnu"
                    rows.append({
                        "✅": False,
                        "ID": o.id,
                        "Statut": "🔴" if o.qa_status == "ERROR" else "🟠" if o.qa_status == "FLAGGED" else "🔵",
                        "EAN": o.ean,
                        "Nom": nom_ref,
                        "Net-Net": f"{(o.prix_net_net_calcule or 0):.2f} €",
                    })

                df_triage = pd.DataFrame(rows)
                edited_df = st.data_editor(
                    df_triage,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "✅": st.column_config.CheckboxColumn("Valider"),
                        "ID": st.column_config.TextColumn(disabled=True),
                        "Statut": st.column_config.TextColumn(disabled=True),
                        "EAN": st.column_config.TextColumn(disabled=True),
                        "Nom": st.column_config.TextColumn(disabled=True),
                        "Net-Net": st.column_config.TextColumn(disabled=True),
                    },
                    height=400
                )

                if st.button("🚀 Exécuter Bulk Validation", type="primary"):
                    from core.stacking_engine import StackingEngine
                    engine = StackingEngine()
                    updated_count = 0
                    for index, row in edited_df.iterrows():
                        if row["✅"]:
                            o_id = row["ID"]
                            o_obj, _ = offre_objects[o_id]
                            o_obj.qa_status = "VALIDATED"
                            db.commit()
                            engine.process_offre(o_id)
                            updated_count += 1
                    
                    if updated_count > 0:
                        st.success(f"✅ {updated_count} offres validées en masse !")
                        st.rerun()

            with col_inspect:
                st.markdown("#### 🔍 Mode Inspecteur")
                inspector_options = [o.id for o, p in offres_qa]
                
                def format_inspector_opt(oid):
                    o, p = offre_objects[oid]
                    stat = "🔴" if o.qa_status == "ERROR" else "🟠" if o.qa_status == "FLAGGED" else "🔵"
                    return f"{stat} [{o.ean}] {p.nom_genere if p else 'Inconnu'}"

                selected_id = st.selectbox(
                    "Sélectionnez une offre à inspecter en détail :",
                    options=inspector_options,
                    format_func=format_inspector_opt
                )

                if selected_id:
                    o_sel, p_sel = offre_objects[selected_id]
                    
                    with st.container(border=True):
                        st.markdown(f"**Offre #{o_sel.id} — {o_sel.enseigne}**")
                        if o_sel.flag_reason:
                            st.error(f"⚠️ Motif du flag : {o_sel.flag_reason}")
                        
                        if o_sel.image_preuve_path:
                            st.image(o_sel.image_preuve_path, caption="Preuve d'extraction")
                        
                        st.markdown("##### Édition Rapide")
                        with st.form(f"form_inspect_{o_sel.id}"):
                            new_ean = st.text_input("EAN", value=o_sel.ean)
                            
                            c1, c2 = st.columns(2)
                            with c1:
                                new_public = st.number_input("Prix Public (€)", value=o_sel.prix_public or 0.0, format="%.2f")
                                new_coupon = st.number_input("Coupon (€)", value=o_sel.valeur_coupon or 0.0, format="%.2f")
                            with c2:
                                new_barre = st.number_input("Prix Barré (€)", value=o_sel.prix_initial_barre or 0.0, format="%.2f")
                                new_odr = st.number_input("ODR (€)", value=o_sel.valeur_odr or 0.0, format="%.2f")
                                
                            st.write(f"**Prix Net-Net Actuel :** {(o_sel.prix_net_net_calcule or 0):.2f} €")
                            st.write(f"**Score Fiabilité :** {(o_sel.reliability_score or 0):.2f}")

                            c_save, c_valid = st.columns(2)
                            with c_save:
                                save_info = st.form_submit_button("💾 Sauvegarder Infos", use_container_width=True)
                            with c_valid:
                                force_valid = st.form_submit_button("✅ Forcer Validation", type="primary", use_container_width=True)
                            
                            if save_info or force_valid:
                                o_sel.ean = new_ean
                                o_sel.prix_public = new_public
                                o_sel.valeur_coupon = new_coupon
                                o_sel.prix_initial_barre = new_barre
                                o_sel.valeur_odr = new_odr
                                
                                if force_valid:
                                    o_sel.qa_status = "VALIDATED"
                                    
                                db.commit()
                                
                                from core.stacking_engine import StackingEngine
                                StackingEngine().process_offre(o_sel.id)
                                
                                if force_valid:
                                    st.success("Offre corrigée et validée !")
                                else:
                                    st.success("Informations mises à jour !")
                                st.rerun()

    except Exception as e:
        st.error(f"Erreur Triage: {e}")
    finally:
        db.close()


with tab_matrice:
    st.subheader("📜 Matrice des Règles Promotionnelles (Globales)")
    st.caption("Ajoutez ou modifiez les ODR, codes promos et remises panier applicables lors du Stacking.")

    db_mat = SessionLocal()
    try:
        rules = db_mat.query(RuleMatrix).order_by(RuleMatrix.created_at.desc()).all()
        
        rules_data = []
        for r in rules:
            rules_data.append({
                "id": r.id,
                "Nom": r.rule_name,
                "Type": r.rule_type,
                "Enseigne": r.target_enseigne or "",
                "Marque": r.target_brand or "",
                "Catégorie": r.target_category or "",
                "EAN": r.target_ean or "",
                "Valeur": r.discount_value,
                "Pourcentage ?": r.is_percentage,
                "Min Achat (€)": r.min_purchase_amount or 0.0,
                "Exp. Date": r.date_expiration.strftime("%Y-%m-%d") if r.date_expiration else "",
                "Active": r.is_active,
            })
            
        df_rules = pd.DataFrame(rules_data)
        if df_rules.empty:
            df_rules = pd.DataFrame(columns=[
                "id", "Nom", "Type", "Enseigne", "Marque", "Catégorie", "EAN", 
                "Valeur", "Pourcentage ?", "Min Achat (€)", "Exp. Date", "Active"
            ])

        edited_rules_df = st.data_editor(
            df_rules,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config={
                "id": None,
                "Nom": st.column_config.TextColumn(required=True),
                "Type": st.column_config.SelectboxColumn(
                    options=["ODR", "CODE_PROMO", "REMISE_PANIER"],
                    required=True
                ),
                "Valeur": st.column_config.NumberColumn(required=True),
                "Pourcentage ?": st.column_config.CheckboxColumn(),
                "Active": st.column_config.CheckboxColumn(),
                "Min Achat (€)": st.column_config.NumberColumn(),
            }
        )
        
        st.info("💡 Laissez les champs Enseigne/Marque/Catégorie/EAN vides pour appliquer la règle par défaut (wildcard). Le format date est YYYY-MM-DD.")

        if st.button("💾 Sauvegarder la Matrice", type="secondary"):
            added = 0
            updated = 0
            
            existing_map = {r.id: r for r in rules}
            current_ids_in_df = []
            
            for index, row in edited_rules_df.iterrows():
                r_id = row.get("id")
                
                exp_date_str = str(row["Exp. Date"]).strip() if pd.notnull(row.get("Exp. Date")) else ""
                exp_date = None
                if exp_date_str:
                    try:
                        exp_date = datetime.strptime(exp_date_str, "%Y-%m-%d")
                    except ValueError:
                        pass
                        
                r_nom = str(row["Nom"]).strip() if pd.notnull(row.get("Nom")) else "Nouvelle Règle"
                r_type = str(row["Type"]) if pd.notnull(row.get("Type")) else "REMISE_PANIER"
                r_enseigne = str(row["Enseigne"]).strip() if pd.notnull(row.get("Enseigne")) and str(row["Enseigne"]).strip() else None
                r_marque = str(row["Marque"]).strip() if pd.notnull(row.get("Marque")) and str(row["Marque"]).strip() else None
                r_cat = str(row["Catégorie"]).strip() if pd.notnull(row.get("Catégorie")) and str(row["Catégorie"]).strip() else None
                r_ean = str(row["EAN"]).strip() if pd.notnull(row.get("EAN")) and str(row["EAN"]).strip() else None
                r_val = float(row["Valeur"]) if pd.notnull(row.get("Valeur")) else 0.0
                r_min = float(row["Min Achat (€)"]) if pd.notnull(row.get("Min Achat (€)")) else None
                
                if pd.isna(r_id) or not r_id:
                    new_rule = RuleMatrix(
                        rule_name=r_nom,
                        rule_type=r_type,
                        target_enseigne=r_enseigne,
                        target_brand=r_marque,
                        target_category=r_cat,
                        target_ean=r_ean,
                        discount_value=r_val,
                        is_percentage=bool(row["Pourcentage ?"]),
                        min_purchase_amount=r_min,
                        date_expiration=exp_date,
                        is_active=bool(row.get("Active", True)),
                    )
                    db_mat.add(new_rule)
                    added += 1
                else:
                    current_ids_in_df.append(r_id)
                    rule = existing_map.get(r_id)
                    if rule:
                        rule.rule_name = r_nom
                        rule.rule_type = r_type
                        rule.target_enseigne = r_enseigne
                        rule.target_brand = r_marque
                        rule.target_category = r_cat
                        rule.target_ean = r_ean
                        rule.discount_value = r_val
                        rule.is_percentage = bool(row["Pourcentage ?"])
                        rule.min_purchase_amount = r_min
                        rule.date_expiration = exp_date
                        rule.is_active = bool(row.get("Active", True))
                        updated += 1
            
            deleted = 0
            for r_id, rule in existing_map.items():
                if r_id not in current_ids_in_df:
                    db_mat.delete(rule)
                    deleted += 1
                    
            db_mat.commit()
            st.success(f"✅ Matrice synchronisée : {added} ajout(s), {updated} maj, {deleted} suppression(s).")
            st.rerun()

    except Exception as e:
        st.error(f"Erreur Matrice: {e}")
        db_mat.rollback()
    finally:
        db_mat.close()
