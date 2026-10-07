# ==============================================================================
# FUNCIONALIDAD DEL ARCHIVO (calidad_activos_grupo.py):
# Reporte analítico de Calidad de Activos y Cobertura de Previsiones por Grupo.
# Calcula índices gerenciales de morosidad ampliada (C a F), ratios de cobertura
# de previsiones específicas y gráficos comparativos de riesgo crediticio con
# nombres completos de entidades (también en el hover), etiquetas de porcentaje
# y exportación a Excel.
# ==============================================================================

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from config_db import obtener_engine
from scrapers.indicadores_bcb import obtener_indicadores_bcb
from sqlalchemy import text
import io

@st.cache_data(ttl=600)
def consultar_db_calidad_activos(query, params=None):
    engine = obtener_engine()
    try:
        return pd.read_sql_query(
            text(query),
            engine,
            params=params
        )
    except Exception as e:
        st.error(f"Error consultando la base de datos: {e}")
        return pd.DataFrame()

def mostrar_calidad_activos_grupo():
    st.markdown("""
        <style>
        [data-testid="stMetricValue"] { font-size: 1.5rem !important; }
        [data-testid="stMetricLabel"] { font-size: 0.85rem !important; }
        </style>
    """, unsafe_allow_html=True)

    st.title("🛡️ Calidad de Activos y Cobertura de Previsiones por Grupo")
    st.markdown("Análisis estratégico de riesgo crediticio, morosidad ampliada y suficiencia de previsiones por entidad.")

    dict_indicadores = obtener_indicadores_bcb()

    if "moneda_seleccionada_calidad_activos" not in st.session_state: 
        st.session_state.moneda_seleccionada_calidad_activos = list(dict_indicadores.keys())[0]

    # ======================================================
    # 1. ENCABEZADO Y FILTROS
    # ======================================================
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([0.5, 0.8, 1.2, 1.2])

        df_years = consultar_db_calidad_activos("""
            SELECT DISTINCT
                EXTRACT(YEAR FROM fecha_corte)::int as anio
            FROM calificacion_cartera
            ORDER BY anio DESC
        """)

        if df_years.empty:
            st.warning("No hay datos disponibles de Calificación de Cartera en la base de datos.")
            return

        anio_sel = c1.selectbox("Año", df_years['anio'].tolist(), key="anio_calidad_activos")

        df_fechas = consultar_db_calidad_activos("""
            SELECT DISTINCT fecha_corte
            FROM calificacion_cartera
            WHERE EXTRACT(YEAR FROM fecha_corte) = :anio
            ORDER BY fecha_corte DESC
        """, {"anio": anio_sel})

        fecha_sel = c2.selectbox("Corte", df_fechas['fecha_corte'].astype(str).tolist(), key="fecha_calidad_activos")

        if st.session_state.moneda_seleccionada_calidad_activos not in dict_indicadores:
            st.session_state.moneda_seleccionada_calidad_activos = list(dict_indicadores.keys())[0]

        st.session_state.moneda_seleccionada_calidad_activos = c3.selectbox(
            "💰 Unidad de Medida", 
            list(dict_indicadores.keys()), 
            index=list(dict_indicadores.keys()).index(st.session_state.moneda_seleccionada_calidad_activos),
            key="moneda_calidad_activos"
        )

        df_grupos = consultar_db_calidad_activos("""
            SELECT id_grupo, nombre_grupo
            FROM grupos_asfi
            ORDER BY id_grupo ASC
        """)

        grupo_sel = c4.selectbox("📂 Grupo Financiero", df_grupos['nombre_grupo'].tolist(), key="grupo_calidad_activos")
        id_g = int(df_grupos[df_grupos['nombre_grupo'] == grupo_sel]['id_grupo'].values[0])

        if len(dict_indicadores) == 1:
            st.caption("⚠️ No existe conectividad con BCB (Muestra únicamente datos en Bs.)")

    # ======================================================
    # 2. OBTENCIÓN DE DATOS DE CALIFICACIÓN (CON NOMBRE COMPLETO)
    # ======================================================
    df_ent = consultar_db_calidad_activos("""
        SELECT
            id_entidad,
            nombre_entidad as sigla,
            nombre_completo
        FROM entidades
        WHERE id_grupo = :id_grupo
          AND nombre_entidad != 'BMU'
        ORDER BY 
            CASE WHEN nombre_entidad LIKE 'TS%' THEN 1 ELSE 0 END,
            nombre_completo ASC
    """, {"id_grupo": id_g})

    if df_ent.empty:
        st.info("No se encontraron entidades asociadas al grupo seleccionado.")
        return

    dict_id_sigla = dict(zip(df_ent['id_entidad'], df_ent['sigla']))
    dict_id_nombre = dict(zip(df_ent['id_entidad'], df_ent['nombre_completo']))
    ids_entidades = list(dict_id_sigla.keys())

    query_cc = """
        SELECT
            id_entidad,
            categoria_a, prevision_a,
            categoria_b, prevision_b,
            categoria_c, prevision_c,
            categoria_d, prevision_d,
            categoria_e, prevision_e,
            categoria_f, prevision_f,
            total_cartera, total_prevision
        FROM calificacion_cartera
        WHERE fecha_corte = :fecha
          AND id_entidad IN ({})
    """.format(','.join([str(x) for x in ids_entidades]))

    df_cc_raw = consultar_db_calidad_activos(query_cc, {"fecha": fecha_sel})

    if df_cc_raw.empty:
        st.warning("No existen registros de calificación de cartera para las entidades del grupo en la fecha seleccionada.")
        return

    df_cc_raw['sigla'] = df_cc_raw['id_entidad'].map(dict_id_sigla)
    df_cc_raw['nombre_completo'] = df_cc_raw['id_entidad'].map(dict_id_nombre)

    factor_conv = dict_indicadores[st.session_state.moneda_seleccionada_calidad_activos]
    nombre_moneda = st.session_state.moneda_seleccionada_calidad_activos.split(' ')[0]

    lista_analisis = []
    for _, r in df_cc_raw.iterrows():
        sigla = r['sigla']
        nombre_comp = r['nombre_completo'] if pd.notna(r['nombre_completo']) and str(r['nombre_completo']).strip() != "" else sigla
        
        tot_cartera = float(r['total_cartera'] or 0) / factor_conv
        tot_prev = float(r['total_prevision'] or 0) / factor_conv
        
        cat_c = float(r['categoria_c'] or 0) / factor_conv
        cat_d = float(r['categoria_d'] or 0) / factor_conv
        cat_e = float(r['categoria_e'] or 0) / factor_conv
        cat_f = float(r['categoria_f'] or 0) / factor_conv

        cartera_pesada = cat_c + cat_d + cat_e + cat_f
        indice_mora = (cartera_pesada / tot_cartera * 100) if tot_cartera > 0 else 0.0
        cobertura = (tot_prev / cartera_pesada * 100) if cartera_pesada > 0 else (100.0 if cartera_pesada == 0 else 0.0)

        lista_analisis.append({
            'Sigla': sigla,
            'Entidad Financiera': nombre_comp,
            'Total Cartera': tot_cartera,
            'Cartera Sana (A+B)': tot_cartera - cartera_pesada,
            'Cartera Pesada (C-F)': cartera_pesada,
            'Previsión Constituida': tot_prev,
            'Índice Mora (%)': indice_mora,
            'Cobertura Previsión (%)': cobertura
        })

    df_analisis = pd.DataFrame(lista_analisis)
    df_indiv = df_analisis[~df_analisis['Sigla'].str.startswith('TS')]

    # ======================================================
    # 3. GRÁFICOS COMPARATIVOS DE RIESGO (HOVER CON NOMBRE COMPLETO)
    # ======================================================
    if not df_indiv.empty:
        plotly_layout_theme = dict(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(showgrid=False, tickangle=-45),
            yaxis=dict(gridcolor='rgba(128,128,128,0.2)')
        )

        g1, g2 = st.columns(2)

        with g1:
            fig1 = go.Figure()
            fig1.add_trace(go.Bar(
                x=df_indiv['Sigla'],
                y=df_indiv['Índice Mora (%)'],
                customdata=df_indiv['Entidad Financiera'],
                name='Índice de Mora (C-F)',
                marker_color='#d62728',
                text=[f"{v:.2f}%" for v in df_indiv['Índice Mora (%)']],
                textposition='auto',
                hovertemplate='<b>%{customdata}</b><br>Índice de Mora: %{y:.2f}%<extra></extra>'
            ))
            fig1.update_layout(
                height=300,
                margin=dict(t=35, b=10, l=10, r=10),
                title="Índice de Morosidad Ampliada (Cat. C a F / Cartera Total)",
                showlegend=False,
                **plotly_layout_theme
            )
            st.plotly_chart(fig1, use_container_width=True)

        with g2:
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(
                x=df_indiv['Sigla'],
                y=df_indiv['Cobertura Previsión (%)'],
                customdata=df_indiv['Entidad Financiera'],
                name='Cobertura de Previsión',
                marker_color='#2ca02c',
                text=[f"{v:.2f}%" for v in df_indiv['Cobertura Previsión (%)']],
                textposition='auto',
                hovertemplate='<b>%{customdata}</b><br>Cobertura: %{y:.2f}%<extra></extra>'
            ))
            fig2.update_layout(
                height=300,
                margin=dict(t=35, b=10, l=10, r=10),
                title="Ratio de Cobertura de Previsiones (Previsiones / Cartera Pesada)",
                showlegend=False,
                **plotly_layout_theme
            )
            st.plotly_chart(fig2, use_container_width=True)

    st.markdown("---")

    # ======================================================
    # 4. TABLA RESUMEN DE CALIDAD DE ACTIVOS
    # ======================================================
    st.subheader(f"📋 Indicadores de Calidad de Cartera ({nombre_moneda})")

    col_cartera_head = f"Total Cartera ({nombre_moneda})"
    col_pesada_head = f"Cartera Pesada C-F ({nombre_moneda})"
    col_prev_head = f"Previsión Específica ({nombre_moneda})"

    df_display = df_analisis.drop(columns=['Sigla']).rename(columns={
        'Total Cartera': col_cartera_head,
        'Cartera Pesada (C-F)': col_pesada_head,
        'Previsión Constituida': col_prev_head
    })

    st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Entidad Financiera": st.column_config.TextColumn("Entidad Financiera", width=280),
            col_cartera_head: st.column_config.NumberColumn(col_cartera_head, format="%,.2f", width=180),
            "Cartera Sana (A+B)": st.column_config.NumberColumn("Cartera Sana", format="%,.2f", width=180),
            col_pesada_head: st.column_config.NumberColumn(col_pesada_head, format="%,.2f", width=180),
            col_prev_head: st.column_config.NumberColumn(col_prev_head, format="%,.2f", width=180),
            "Índice Mora (%)": st.column_config.NumberColumn("Índice Mora", format="%.2f %%", width=130),
            "Cobertura Previsión (%)": st.column_config.NumberColumn("Cobertura", format="%.2f %%", width=130)
        }
    )

    # ======================================================
    # 5. EXPORTAR REPORTE A EXCEL
    # ======================================================
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as wr:
        df_display.to_excel(wr, index=False, sheet_name='Calidad_Activos_Grupo')

    _, col_btn = st.columns([3, 1])
    with col_btn:
        nombre_file = f"Calidad_Activos_{grupo_sel.replace(' ', '_')}_{fecha_sel}"
        st.download_button(
            "📥 Descargar Reporte Excel",
            buf.getvalue(),
            f"{nombre_file}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

if __name__ == "__main__":
    mostrar_calidad_activos_grupo()