"""
PAGE 4 — Market Export v3 (B2B CSV Pipeline)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
import io
from datetime import datetime
from core.models import SessionLocal, OffreRetail, ProduitReference

st.set_page_config(page_title="Market Export | STAFF v3", page_icon="📈", layout="wide")

st.markdown("### 📈 Market Export — B2B Data Pipeline")
st.caption("Filtrez les opportunités validées, ajustez les prix manuellement, et générez des exports B2B propres.")

tab_arene, tab_export = st.tabs([
    "⚔️ L'Arène (Éditable)",
    "📦 Quai d'Export (B2B)"
])

with tab_arene:
    st.subheader("⚔️ Validation Manuelle (QA Phase 2)")
    st.markdown("Ajustez les prix marché ramassés par le Bot, et certifiez les offres prêtes pour le B2B.")

    db = SessionLocal()
    try:
        offres_val = db.query(OffreRetail, ProduitReference).outerjoin(
            ProduitReference, OffreRetail.ean == ProduitReference.ean
        ).filter(
            OffreRetail.qa_status == 'VALIDATED',
            OffreRetail.is_active == True
        ).all()

        if not offres_val:
            st.info("Aucune offre avec le statut `VALIDATED` pour le moment. Traitez-les dans le QA Lab.")
        else:
            rows = []
            offre_objects = {}

            for o, p in offres_val:
                nom_ref = p.nom_genere if p else o.enseigne
                net_net = o.prix_net_net_calcule or 0.0
                revente = o.prix_revente_marche or 0.0
                profit = revente - net_net
                roi = (profit / net_net * 100) if net_net > 0 else 0.0

                rows.append({
                    "id": o.id,
                    "EAN": o.ean,
                    "Produit": nom_ref,
                    "Marchand": o.enseigne,
                    "Net-Net (€)": net_net,
                    "Revente Marché (€)": revente,
                    "Profit (€)": profit,
                    "ROI (%)": roi,
                    "Score QA": o.reliability_score,
                    "Certifier": False,
                })
                offre_objects[o.id] = o

            df_arene = pd.DataFrame(rows)

            edited_df = st.data_editor(
                df_arene,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "id": None,
                    "Certifier": st.column_config.CheckboxColumn("✅ Certifier (GO B2B)"),
                    "EAN": st.column_config.TextColumn(disabled=False),
                    "Net-Net (€)": st.column_config.NumberColumn(format="%.2f", disabled=False),
                    "Revente Marché (€)": st.column_config.NumberColumn(format="%.2f", disabled=False),
                    "Produit": st.column_config.TextColumn(disabled=True),
                    "Marchand": st.column_config.TextColumn(disabled=True),
                    "Profit (€)": st.column_config.NumberColumn(format="%.2f", disabled=True),
                    "ROI (%)": st.column_config.NumberColumn(format="%.1f", disabled=True),
                    "Score QA": st.column_config.NumberColumn(format="%.2f", disabled=True),
                },
            )

            col1, col2 = st.columns([1, 1])
            with col1:
                cmd_sauvegarder = st.button("💾 Sauvegarder les modifications", type="secondary")
            with col2:
                cmd_certifier = st.button("✅ CERTIFIER LA SÉLECTION (GO B2B)", type="primary")

            if cmd_sauvegarder or cmd_certifier:
                updated_count = 0
                certified_count = 0

                for index, row in edited_df.iterrows():
                    o_id = row["id"]
                    o = offre_objects[o_id]
                    changed = False

                    if str(o.ean) != str(row.get("EAN", "")):
                        o.ean = str(row["EAN"])
                        changed = True
                    if o.prix_net_net_calcule != float(row.get("Net-Net (€)", 0)):
                        o.prix_net_net_calcule = float(row["Net-Net (€)"])
                        changed = True
                    if o.prix_revente_marche != float(row.get("Revente Marché (€)", 0)):
                        o.prix_revente_marche = float(row["Revente Marché (€)"])
                        changed = True

                    if cmd_certifier and row.get("Certifier"):
                        o.qa_status = "PUBLISHED"
                        changed = True
                        certified_count += 1

                    if changed:
                        updated_count += 1

                if updated_count > 0:
                    db.commit()
                    if cmd_certifier:
                        st.success(f"✅ {certified_count} offres ont été publiées et sont prêtes à l'export !")
                    else:
                        st.success(f"💾 {updated_count} offres sauvegardées manuellement.")
                    st.rerun()

            st.divider()
            st.markdown("#### 📊 Analyse des Tendances de Prix (Market History)")
            st.caption("Preuve de stabilité du prix de marché (BSR / Buy Box) pour certifier vos pépites.")

            from core.models import PriceHistory
            for o, p in offres_val:
                nom_ref = p.nom_genere if p else o.enseigne
                with st.expander(f"📉 Tendance & Historique : {nom_ref} (EAN: {o.ean})"):
                    history = db.query(PriceHistory).filter(PriceHistory.ean == o.ean).order_by(PriceHistory.fetch_date.asc()).all()
                    
                    if not history:
                        st.info("Aucun historique de prix disponible pour cet EAN.")
                    else:
                        hist_data = []
                        for h in history:
                            hist_data.append({
                                "Date": h.fetch_date,
                                "Prix Marché (€)": h.prix_revente
                            })
                        df_hist = pd.DataFrame(hist_data).set_index("Date")
                        st.line_chart(df_hist, y="Prix Marché (€)", color="#1DD05D")
                        
                        c_min, c_max, c_cur = st.columns(3)
                        c_min.metric("Prix Plus Bas", f"{df_hist['Prix Marché (€)'].min():.2f} €")
                        c_max.metric("Prix Plus Haut", f"{df_hist['Prix Marché (€)'].max():.2f} €")
                        c_cur.metric("Dernier Prix Relevé", f"{df_hist['Prix Marché (€)'].iloc[-1]:.2f} €")

    except Exception as e:
        st.error(f"Erreur UI Arène: {e}")
    finally:
        db.close()


with tab_export:
    st.subheader("📦 Quai d'Export B2B")
    st.markdown("Vue finale des pépites certifiées prêtes pour la revente ou la base de données Clients.")

    db2 = SessionLocal()
    try:
        offres_pub = db2.query(OffreRetail, ProduitReference).outerjoin(
            ProduitReference, OffreRetail.ean == ProduitReference.ean
        ).filter(
            OffreRetail.qa_status == 'PUBLISHED',
            OffreRetail.is_active == True
        ).all()

        if not offres_pub:
            st.info("Aucune offre n'est 'PUBLISHED'. Certifiez-les dans l'Arène d'abord.")
        else:
            pub_rows = []
            for o, p in offres_pub:
                nom_ref = p.nom_genere if p else o.enseigne
                net_net = o.prix_net_net_calcule or 0.0
                revente = o.prix_revente_marche or 0.0
                profit = revente - net_net
                roi = (profit / net_net * 100) if net_net > 0 else 0.0

                pub_rows.append({
                    "Date Validation": o.timestamp.strftime("%Y-%m-%d"),
                    "EAN": o.ean,
                    "Marque": p.marque if p and getattr(p, "marque", None) else "",
                    "Produit": nom_ref,
                    "Marchand": o.enseigne,
                    "Prix Achat Net (€)": net_net,
                    "Prix Revente Marché Est. (€)": revente,
                    "Marge Nette Absolue (€)": profit,
                    "ROI (%)": round(roi, 1),
                })
            
            df_export = pd.DataFrame(pub_rows)
            st.dataframe(df_export, use_container_width=True, hide_index=True)

            csv_buffer = io.StringIO()
            df_export.to_csv(csv_buffer, index=False, sep=";", encoding="utf-8-sig", decimal=",")

            st.download_button(
                label="📥 Télécharger l'export CSV (B2B)",
                data=csv_buffer.getvalue().encode('utf-8-sig'),
                file_name=f"staff_b2b_export_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                use_container_width=True,
                type="primary"
            )

    except Exception as e:
        st.error(f"Erreur UI Export: {e}")
    finally:
        db2.close()
