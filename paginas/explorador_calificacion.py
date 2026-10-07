# ==============================================================================
# FUNCIONALIDAD DEL ARCHIVO (explorador_calificacion.py):
# Permite visualizar, analizar y exportar la Calificación de Cartera y Previsiones
# de entidades financieras bolivianas o consolidados por grupo a una fecha de corte.
# Incluye vinculación explícita entre notas normativas y soporte multimoneda.
# ==============================================================================

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from config_db import obtener_engine
from scrapers.indicadores_bcb import obtener_indicadores_bcb
import io

def generar_excel_calificacion(df_datos, df_notas, entidad_nombre, fecha_corte):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # CORRECCIÓN: Nombre de pestaña <= 31 caracteres (25 caracteres)
        df_datos.to_excel(writer, index=False, sheet_name='Calif_Cartera_Contingente')
        if not df_notas.empty:
            df_notas.to_excel(writer, index=False, sheet_name='Notas_ASFI')
    return output.getvalue()

@st.cache_data(ttl=600)
def consultar_db(query, params=None):
    engine = obtener_engine()
    try:
        return pd.read_sql_query(query, engine, params=params)
    except Exception as e:
        st.error(f"Error al consultar la base de datos: {e}")
        return pd.DataFrame()

def mostrar_explorador_calificacion():
    st.markdown("""
        <style>
        [data-testid="stMetricValue"] { font-size: 1.6rem !important; }
        [data-testid="stMetricLabel"] { font-size: 0.9rem !important; }
        </style>
    """, unsafe_allow_html=True)

    st.title("🔍 Explorador de Calificación de Cartera y Contingente")
    
    dict_indicadores = obtener_indicadores_bcb()

    if "moneda_seleccionada_cartera" not in st.session_state: 
        st.session_state.moneda_seleccionada_cartera = list(dict_indicadores.keys())[0]

    # --- 1. CONFIGURACIÓN Y FILTROS ---
    with st.container(border=True):
        t1, t2, t3 = st.columns([0.5, 0.8, 1.2])
        
        df_years = consultar_db("""
            SELECT DISTINCT EXTRACT(YEAR FROM fecha_corte)::int as anio 
            FROM calificacion_cartera 
            ORDER BY anio DESC
        """)
        if df_years.empty:
            st.warning("No hay datos disponibles de Calificación de Cartera y Contingente en la base de datos.")
            return
            
        anio_sel = t1.selectbox("Año", df_years['anio'].tolist(), key="sel_anio_exp_calif")
        
        df_fechas = consultar_db("""
            SELECT DISTINCT fecha_corte 
            FROM calificacion_cartera 
            WHERE EXTRACT(YEAR FROM fecha_corte) = %s 
            ORDER BY fecha_corte DESC
        """, (anio_sel,))
        
        fecha_sel = t2.selectbox("Corte", df_fechas['fecha_corte'].astype(str).tolist(), key="sel_corte_exp_calif")
        
        if st.session_state.moneda_seleccionada_cartera not in dict_indicadores:
            st.session_state.moneda_seleccionada_cartera = list(dict_indicadores.keys())[0]

        st.session_state.moneda_seleccionada_cartera = t3.selectbox(
            "💰 Unidad de Medida", 
            list(dict_indicadores.keys()), 
            index=list(dict_indicadores.keys()).index(st.session_state.moneda_seleccionada_cartera),
            key="sel_moneda_exp_calif"
        )

        f2, f3 = st.columns([1.3, 1.7])
        
        df_grupos = consultar_db("SELECT id_grupo, nombre_grupo FROM grupos_asfi ORDER BY id_grupo ASC")
        grupo_sel = f2.selectbox("📂 Grupo Financiero", df_grupos['nombre_grupo'].tolist(), key="sel_grupo_exp_calif")
        id_g = int(df_grupos[df_grupos['nombre_grupo'] == grupo_sel]['id_grupo'].values[0])

        df_ent = consultar_db("""
            SELECT id_entidad, nombre_entidad as sigla, nombre_completo 
            FROM entidades 
            WHERE id_grupo = %s 
            ORDER BY 
                CASE WHEN nombre_entidad LIKE 'TS%%' THEN 0 ELSE 1 END,
                nombre_completo ASC
        """, (id_g,))
        
        opciones_ent = {}
        for _, r in df_ent.iterrows():
            nombre = r['nombre_completo'] if pd.notna(r['nombre_completo']) and r['nombre_completo'] != "" else r['sigla']
            opciones_ent[f"{nombre} ({r['sigla']})"] = (r['id_entidad'], r['sigla'])
            
        entidad_display = f3.selectbox("🏛️ Entidad Financiera", options=list(opciones_ent.keys()), key="sel_ent_exp_calif")
        id_entidad_sel, sigla_banco = opciones_ent[entidad_display]
        
        if len(dict_indicadores) == 1:
            st.caption("⚠️ No existe conectividad con BCB (Muestra únicamente datos en Bs.)")

    # --- 2. CONSULTA ADAPTATIVA ---
    es_total_sistema = sigla_banco.startswith("TS") or "TOTAL SISTEMA" in entidad_display.upper()

    if es_total_sistema:
        query_cartera = """
            SELECT 
                SUM(categoria_a) as categoria_a, SUM(prevision_a) as prevision_a,
                SUM(categoria_b) as categoria_b, SUM(prevision_b) as prevision_b,
                SUM(categoria_c) as categoria_c, SUM(prevision_c) as prevision_c,
                SUM(categoria_d) as categoria_d, SUM(prevision_d) as prevision_d,
                SUM(categoria_e) as categoria_e, SUM(prevision_e) as prevision_e,
                SUM(categoria_f) as categoria_f, SUM(prevision_f) as prevision_f,
                SUM(total_cartera) as total_cartera, SUM(total_prevision) as total_prevision,
                AVG(porcentaje_participacion) as porcentaje_participacion
            FROM calificacion_cartera 
            WHERE id_grupo = %s AND fecha_corte = %s AND id_entidad != %s
        """
        df_raw = consultar_db(query_cartera, (id_g, fecha_sel, id_entidad_sel))
        
        if df_raw.empty or pd.isnull(df_raw.iloc[0]['total_cartera']):
            query_cartera_directa = "SELECT * FROM calificacion_cartera WHERE id_entidad = %s AND fecha_corte = %s"
            df_raw = consultar_db(query_cartera_directa, (id_entidad_sel, fecha_sel))
    else:
        query_cartera = "SELECT * FROM calificacion_cartera WHERE id_entidad = %s AND fecha_corte = %s"
        df_raw = consultar_db(query_cartera, (id_entidad_sel, fecha_sel))

    if df_raw.empty or pd.isnull(df_raw.iloc[0]['total_cartera']):
        st.info("No se encontraron registros de calificación de cartera y contingente para la selección actual.")
        return

    row = df_raw.iloc[0]
    factor_conv = dict_indicadores[st.session_state.moneda_seleccionada_cartera]
    nombre_moneda = st.session_state.moneda_seleccionada_cartera.split(' ')[0]

    cat_a = float(row['categoria_a'] or 0) / factor_conv
    cat_b = float(row['categoria_b'] or 0) / factor_conv
    cat_c = float(row['categoria_c'] or 0) / factor_conv
    cat_d = float(row['categoria_d'] or 0) / factor_conv
    cat_e = float(row['categoria_e'] or 0) / factor_conv
    cat_f = float(row['categoria_f'] or 0) / factor_conv
    
    prev_a = float(row['prevision_a'] or 0) / factor_conv
    prev_b = float(row['prevision_b'] or 0) / factor_conv
    prev_c = float(row['prevision_c'] or 0) / factor_conv
    prev_d = float(row['prevision_d'] or 0) / factor_conv
    prev_e = float(row['prevision_e'] or 0) / factor_conv
    prev_f = float(row['prevision_f'] or 0) / factor_conv

    tot_cartera = float(row['total_cartera'] or 0) / factor_conv
    tot_prevision = float(row['total_prevision'] or 0) / factor_conv

    cartera_incumplida = cat_c + cat_d + cat_e + cat_f
    mora_pct = (cartera_incumplida / tot_cartera * 100) if tot_cartera > 0 else 0.0
    cobertura_pct = (tot_prevision / cartera_incumplida * 100) if cartera_incumplida > 0 else 0.0

    m1, m2, m3, m4 = st.columns([1.3, 1.2, 0.8, 0.8])
    m1.metric(f"Total Cartera y Contingente ({nombre_moneda}) ⁽⁴⁾", f"{tot_cartera:,.2f}")
    m2.metric(f"Total Previsiones ({nombre_moneda})", f"{tot_prevision:,.2f}")
    m3.metric("Índice C a F", f"{mora_pct:.2f}%")
    m4.metric("Cobertura Previsión", f"{cobertura_pct:.2f}%")

    plotly_theme = dict(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(showgrid=False),
        yaxis=dict(gridcolor='rgba(128,128,128,0.2)')
    )

    categorias = ['Cat. A ⁽²⁾', 'Cat. B ⁽³⁾', 'Cat. C', 'Cat. D', 'Cat. E', 'Cat. F']
    valores_cartera = [cat_a, cat_b, cat_c, cat_d, cat_e, cat_f]
    valores_prevision = [prev_a, prev_b, prev_c, prev_d, prev_e, prev_f]

    cg1, cg2 = st.columns(2)
    with cg1:
        fig1 = go.Figure(data=[
            go.Bar(name='Cartera y Contingente', x=categorias, y=valores_cartera, marker_color='#004a99', text=[f"{v:,.1f}" for v in valores_cartera], textposition='auto')
        ])
        fig1.update_layout(
            height=280, margin=dict(t=30, b=10), showlegend=False, 
            title=f"Distribución por Categoría ({nombre_moneda})",
            **plotly_theme
        )
        st.plotly_chart(fig1, use_container_width=True)

    with cg2:
        fig2 = go.Figure(data=[
            go.Bar(name='Previsión Específica', x=categorias, y=valores_prevision, marker_color='#d62728', text=[f"{v:,.1f}" for v in valores_prevision], textposition='auto')
        ])
        fig2.update_layout(
            height=280, margin=dict(t=30, b=10), showlegend=False, 
            title=f"Previsiones Constituidas por Categoría ({nombre_moneda})",
            **plotly_theme
        )
        st.plotly_chart(fig2, use_container_width=True)

    st.markdown("---")
    st.subheader("📋 Detalle de Calificación de Cartera y Contingente ⁽¹⁾")

    data_tabla = [
        {"Categoría de Riesgo": "Categoría A (Previsión según norma) ⁽²⁾", "Cartera y Contingente": cat_a, "Previsión Específica": prev_a, "% Previsión": (prev_a/cat_a*100) if cat_a>0 else 0},
        {"Categoría de Riesgo": "Categoría B (Previsión según norma) ⁽³⁾", "Cartera y Contingente": cat_b, "Previsión Específica": prev_b, "% Previsión": (prev_b/cat_b*100) if cat_b>0 else 0},
        {"Categoría de Riesgo": "Categoría C (Previsión 20%)", "Cartera y Contingente": cat_c, "Previsión Específica": prev_c, "% Previsión": (prev_c/cat_c*100) if cat_c>0 else 0},
        {"Categoría de Riesgo": "Categoría D (Previsión 50%)", "Cartera y Contingente": cat_d, "Previsión Específica": prev_d, "% Previsión": (prev_d/cat_d*100) if cat_d>0 else 0},
        {"Categoría de Riesgo": "Categoría E (Previsión 80%)", "Cartera y Contingente": cat_e, "Previsión Específica": prev_e, "% Previsión": (prev_e/cat_e*100) if cat_e>0 else 0},
        {"Categoría de Riesgo": "Categoría F (Previsión 100%)", "Cartera y Contingente": cat_f, "Previsión Específica": prev_f, "% Previsión": (prev_f/cat_f*100) if cat_f>0 else 0},
        {"Categoría de Riesgo": "TOTAL CARTERA Y CONTINGENTE ⁽⁴⁾", "Cartera y Contingente": tot_cartera, "Previsión Específica": tot_prevision, "% Previsión": (tot_prevision/tot_cartera*100) if tot_cartera>0 else 0}
    ]

    df_display = pd.DataFrame(data_tabla)

    col_cartera_head = f"Cartera y Contingente ({nombre_moneda})"
    col_prev_head = f"Previsión ({nombre_moneda})"

    df_display = df_display.rename(columns={
        "Cartera y Contingente": col_cartera_head,
        "Previsión Específica": col_prev_head
    })

    st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Categoría de Riesgo": st.column_config.TextColumn("Categoría de Riesgo", width=320),
            col_cartera_head: st.column_config.NumberColumn(col_cartera_head, format="%,.2f", width=220),
            col_prev_head: st.column_config.NumberColumn(col_prev_head, format="%,.2f", width=180),
            "% Previsión": st.column_config.NumberColumn("% Previsión Efectiva", format="%.2f %%", width=150)
        }
    )

    query_notas = """
        SELECT numero_nota, texto_nota 
        FROM calificacion_notas 
        WHERE id_grupo = %s AND fecha_corte = %s 
        ORDER BY numero_nota ASC
    """
    df_notas = consultar_db(query_notas, (id_g, fecha_sel))

    REFERENCIA_NOTAS = {
        1: "Título general del reporte y origen de la información",
        2: "Previsiones de la Categoría A (según tipo de crédito y moneda)",
        3: "Previsiones de la Categoría B (según tipo de crédito y moneda)",
        4: "Total Cartera y Contingente (Exclusiones específicas de cuentas)"
    }

    if not df_notas.empty:
        with st.expander("📌 Notas Aclaratorias de la ASFI y su correspondencia", expanded=False):
            for _, n_row in df_notas.iterrows():
                num = int(n_row['numero_nota'])
                ref_texto = REFERENCIA_NOTAS.get(num, "Línea específica del reporte")
                with st.container(border=True):
                    st.markdown(f"**Nota ({num})** — *Aplica a: {ref_texto}*")
                    st.caption(n_row['texto_nota'])

    excel_bytes = generar_excel_calificacion(df_display, df_notas, sigla_banco, fecha_sel)
    _, col_btn = st.columns([3, 1])
    with col_btn:
        st.download_button(
            "📥 Descargar Reporte Excel", 
            data=excel_bytes, 
            file_name=f"Calificacion_Cartera_Contingente_{sigla_banco}_{fecha_sel}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

if __name__ == "__main__":
    mostrar_explorador_calificacion()