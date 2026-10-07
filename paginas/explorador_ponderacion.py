# ==============================================================================
# FUNCIONALIDAD DEL ARCHIVO (explorador_ponderacion.py):
# Permite visualizar, analizar y exportar los Activos Ponderados por Riesgo,
# Suficiencia Patrimonial y Ratios Regulatorios (CAP) de entidades financieras
# bolivianas o consolidados por grupo a una fecha de corte.
# Incluye soporte multimoneda y notas aclaratorias normativas.
# ==============================================================================

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from config_db import obtener_engine
from scrapers.indicadores_bcb import obtener_indicadores_bcb
import io

def generar_excel_ponderacion(df_activos, df_patrimonio, df_ratios, df_notas, entidad_nombre, fecha_corte):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_activos.to_excel(writer, index=False, sheet_name='Activos_Riesgo')
        df_patrimonio.to_excel(writer, index=False, sheet_name='Suficiencia_Patrimonial')
        df_ratios.to_excel(writer, index=False, sheet_name='Ratios_Regulatorios')
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

def mostrar_explorador_ponderacion():
    st.markdown("""
        <style>
        [data-testid="stMetricValue"] { font-size: 1.6rem !important; }
        [data-testid="stMetricLabel"] { font-size: 0.9rem !important; }
        </style>
    """, unsafe_allow_html=True)

    st.title("⚖️ Explorador de Activos Ponderados por Riesgo y CAP")
    
    dict_indicadores = obtener_indicadores_bcb()

    if "moneda_seleccionada_pond" not in st.session_state: 
        st.session_state.moneda_seleccionada_pond = list(dict_indicadores.keys())[0]

    # --- 1. CONFIGURACIÓN Y FILTROS ---
    with st.container(border=True):
        t1, t2, t3 = st.columns([0.5, 0.8, 1.2])
        
        df_years = consultar_db("""
            SELECT DISTINCT EXTRACT(YEAR FROM fecha_corte)::int as anio 
            FROM activos_riesgo_valores 
            ORDER BY anio DESC
        """)
        if df_years.empty:
            st.warning("No hay datos disponibles de Activos Ponderados en la base de datos.")
            return
            
        anio_sel = t1.selectbox("Año", df_years['anio'].tolist(), key="sel_anio_exp_pond")
        
        df_fechas = consultar_db("""
            SELECT DISTINCT fecha_corte 
            FROM activos_riesgo_valores 
            WHERE EXTRACT(YEAR FROM fecha_corte) = %s 
            ORDER BY fecha_corte DESC
        """, (anio_sel,))
        
        fecha_sel = t2.selectbox("Corte", df_fechas['fecha_corte'].astype(str).tolist(), key="sel_corte_exp_pond")
        
        if st.session_state.moneda_seleccionada_pond not in dict_indicadores:
            st.session_state.moneda_seleccionada_pond = list(dict_indicadores.keys())[0]

        st.session_state.moneda_seleccionada_pond = t3.selectbox(
            "💰 Unidad de Medida", 
            list(dict_indicadores.keys()), 
            index=list(dict_indicadores.keys()).index(st.session_state.moneda_seleccionada_pond),
            key="sel_moneda_exp_pond"
        )

        f2, f3 = st.columns([1.3, 1.7])
        
        df_grupos = consultar_db("SELECT id_grupo, nombre_grupo FROM grupos_asfi ORDER BY id_grupo ASC")
        grupo_sel = f2.selectbox("📂 Grupo Financiero", df_grupos['nombre_grupo'].tolist(), key="sel_grupo_exp_pond")
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
            
        entidad_display = f3.selectbox("🏛️ Entidad Financiera", options=list(opciones_ent.keys()), key="sel_ent_exp_pond")
        id_entidad_sel, sigla_banco = opciones_ent[entidad_display]
        
        if len(dict_indicadores) == 1:
            st.caption("⚠️ No existe conectividad con BCB (Muestra únicamente datos en Bs.)")

    # --- 2. CONSULTA DE DATOS ---
    es_total_sistema = sigla_banco.startswith("TS") or "TOTAL SISTEMA" in entidad_display.upper()

    # Activos de Riesgo
    if es_total_sistema:
        query_activos = """
            SELECT c.id_plan_cat, c.descripcion_categoria, c.es_totalizador, c.notas_aclaratorias, c.orden,
                   SUM(v.valor) as valor
            FROM plan_categorias_riesgo c
            JOIN activos_riesgo_valores v ON c.id_plan_cat = v.id_plan_cat
            JOIN entidades e ON v.id_entidad = e.id_entidad
            WHERE e.id_grupo = %s AND v.fecha_corte = %s AND v.id_entidad != %s
            GROUP BY c.id_plan_cat, c.descripcion_categoria, c.es_totalizador, c.notas_aclaratorias, c.orden
            ORDER BY c.orden ASC
        """
        df_activos = consultar_db(query_activos, (id_g, fecha_sel, id_entidad_sel))
        if df_activos.empty or df_activos['valor'].sum() == 0:
            query_activos_dir = """
                SELECT c.id_plan_cat, c.descripcion_categoria, c.es_totalizador, c.notas_aclaratorias, c.orden, v.valor
                FROM plan_categorias_riesgo c
                JOIN activos_riesgo_valores v ON c.id_plan_cat = v.id_plan_cat
                WHERE v.id_entidad = %s AND v.fecha_corte = %s
                ORDER BY c.orden ASC
            """
            df_activos = consultar_db(query_activos_dir, (id_entidad_sel, fecha_sel))
    else:
        query_activos = """
            SELECT c.id_plan_cat, c.descripcion_categoria, c.es_totalizador, c.notas_aclaratorias, c.orden, v.valor
            FROM plan_categorias_riesgo c
            JOIN activos_riesgo_valores v ON c.id_plan_cat = v.id_plan_cat
            WHERE v.id_entidad = %s AND v.fecha_corte = %s
            ORDER BY c.orden ASC
        """
        df_activos = consultar_db(query_activos, (id_entidad_sel, fecha_sel))

    # Suficiencia Patrimonial
    if es_total_sistema:
        query_pat = """
            SELECT p.id_plan_cap, p.codigo_cuenta, p.seccion_cap, p.es_totalizador, p.notas_aclaratorias, p.orden,
                   SUM(v.valor) as valor
            FROM plan_suficiencia_patrimonial p
            JOIN suficiencia_patrimonial_valores v ON p.id_plan_cap = v.id_plan_cap
            JOIN entidades e ON v.id_entidad = e.id_entidad
            WHERE e.id_grupo = %s AND v.fecha_corte = %s AND v.id_entidad != %s
            GROUP BY p.id_plan_cap, p.codigo_cuenta, p.seccion_cap, p.es_totalizador, p.notas_aclaratorias, p.orden
            ORDER BY p.orden ASC
        """
        df_patrimonio = consultar_db(query_pat, (id_g, fecha_sel, id_entidad_sel))
        if df_patrimonio.empty or df_patrimonio['valor'].sum() == 0:
            query_pat_dir = """
                SELECT p.id_plan_cap, p.codigo_cuenta, p.seccion_cap, p.es_totalizador, p.notas_aclaratorias, p.orden, v.valor
                FROM plan_suficiencia_patrimonial p
                JOIN suficiencia_patrimonial_valores v ON p.id_plan_cap = v.id_plan_cap
                WHERE v.id_entidad = %s AND v.fecha_corte = %s
                ORDER BY p.orden ASC
            """
            df_patrimonio = consultar_db(query_pat_dir, (id_entidad_sel, fecha_sel))
    else:
        query_pat = """
            SELECT p.id_plan_cap, p.codigo_cuenta, p.seccion_cap, p.es_totalizador, p.notas_aclaratorias, p.orden, v.valor
            FROM plan_suficiencia_patrimonial p
            JOIN suficiencia_patrimonial_valores v ON p.id_plan_cap = v.id_plan_cap
            WHERE v.id_entidad = %s AND v.fecha_corte = %s
            ORDER BY p.orden ASC
        """
        df_patrimonio = consultar_db(query_pat, (id_entidad_sel, fecha_sel))

    # Ratios Regulatorios
    if es_total_sistema:
        query_rat = """
            SELECT r.id_plan_ratio, r.codigo_ratio, r.notas_aclaratorias, r.orden,
                   AVG(v.valor) as valor
            FROM plan_ratios_regulatorios r
            JOIN ratios_regulatorios_valores v ON r.id_plan_ratio = v.id_plan_ratio
            JOIN entidades e ON v.id_entidad = e.id_entidad
            WHERE e.id_grupo = %s AND v.fecha_corte = %s AND v.id_entidad != %s
            GROUP BY r.id_plan_ratio, r.codigo_ratio, r.notas_aclaratorias, r.orden
            ORDER BY r.orden ASC
        """
        df_ratios = consultar_db(query_rat, (id_g, fecha_sel, id_entidad_sel))
        if df_ratios.empty or df_ratios['valor'].sum() == 0:
            query_rat_dir = """
                SELECT r.id_plan_ratio, r.codigo_ratio, r.notas_aclaratorias, r.orden, v.valor
                FROM plan_ratios_regulatorios r
                JOIN ratios_regulatorios_valores v ON r.id_plan_ratio = v.id_plan_ratio
                WHERE v.id_entidad = %s AND v.fecha_corte = %s
                ORDER BY r.orden ASC
            """
            df_ratios = consultar_db(query_rat_dir, (id_entidad_sel, fecha_sel))
    else:
        query_rat = """
            SELECT r.id_plan_ratio, r.codigo_ratio, r.notas_aclaratorias, r.orden, v.valor
            FROM plan_ratios_regulatorios r
            JOIN ratios_regulatorios_valores v ON r.id_plan_ratio = v.id_plan_ratio
            WHERE v.id_entidad = %s AND v.fecha_corte = %s
            ORDER BY r.orden ASC
        """
        df_ratios = consultar_db(query_rat, (id_entidad_sel, fecha_sel))

    if df_activos.empty:
        st.info("No se encontraron registros de activos ponderados para la selección actual.")
        return

    factor_conv = dict_indicadores[st.session_state.moneda_seleccionada_pond]
    nombre_moneda = st.session_state.moneda_seleccionada_pond.split(' ')[0]

    # Conversión de valores monetarios
    df_activos['valor_conv'] = df_activos['valor'].fillna(0) / factor_conv
    if not df_patrimonio.empty:
        df_patrimonio['valor_conv'] = df_patrimonio['valor'].fillna(0) / factor_conv

    # Extraer métricas clave para tarjetas superiores
    tot_activo_computable = 0.0
    tot_activo_contingente = 0.0
    
    for _, r in df_activos.iterrows():
        desc = str(r['descripcion_categoria']).upper()
        if "TOTAL ACTIVO COMPUTABLE" in desc:
            tot_activo_computable = float(r['valor_conv'])
        elif "TOTAL ACTIVO Y CONTINGENTE" in desc:
            tot_activo_contingente = float(r['valor_conv'])

    # Buscar Coeficiente de Adecuación Patrimonial (CAP) en ratios
    cap_val = 0.0
    if not df_ratios.empty:
        for _, r in df_ratios.iterrows():
            if "COEFICIENTE DE ADECUACIÓN PATRIMONIAL" in str(r['codigo_ratio']).upper():
                cap_val = float(r['valor'] or 0) * 100

    m1, m2, m3 = st.columns(3)
    m1.metric(f"Total Activo y Contingente ({nombre_moneda})", f"{tot_activo_contingente:,.2f}")
    m2.metric(f"Total Activo Computable ({nombre_moneda})", f"{tot_activo_computable:,.2f}")
    m3.metric("Coeficiente de Adecuación Patrimonial (CAP)", f"{cap_val:.2f}%")

    # --- 3. GRÁFICOS VISUALES ---
    plotly_theme = dict(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(showgrid=False),
        yaxis=dict(gridcolor='rgba(128,128,128,0.2)')
    )

    cg1, cg2 = st.columns(2)
    with cg1:
        df_categorias_graf = df_activos[~df_activos['es_totalizador']].copy()
        fig1 = go.Figure(data=[
            go.Bar(name='Activos por Categoría', x=df_categorias_graf['descripcion_categoria'], y=df_categorias_graf['valor_conv'], marker_color='#004a99', text=[f"{v:,.1f}" for v in df_categorias_graf['valor_conv']], textposition='auto')
        ])
        fig1.update_layout(
            height=300, margin=dict(t=30, b=10), showlegend=False, 
            title=f"Activos Ponderados por Categoría de Riesgo ({nombre_moneda})",
            **plotly_theme
        )
        st.plotly_chart(fig1, use_container_width=True)

    with cg2:
        if not df_patrimonio.empty:
            df_pat_graf = df_patrimonio[df_patrimonio['es_totalizador']].copy()
            fig2 = go.Figure(data=[
                go.Bar(name='Patrimonio', x=df_pat_graf['codigo_cuenta'], y=df_pat_graf['valor_conv'], marker_color='#2ca02c', text=[f"{v:,.1f}" for v in df_pat_graf['valor_conv']], textposition='auto')
            ])
            fig2.update_layout(
                height=300, margin=dict(t=30, b=10), showlegend=False, 
                title=f"Principales Partidas Patrimoniales ({nombre_moneda})",
                **plotly_theme
            )
            st.plotly_chart(fig2, use_container_width=True)

    # --- 4. TABLAS DE DETALLE ---
    st.markdown("---")
    st.subheader("📋 1. Activos Ponderados por Riesgo")
    df_activos_disp = df_activos[['descripcion_categoria', 'valor_conv', 'notas_aclaratorias']].copy()
    col_act_head = f"Valor ({nombre_moneda})"
    df_activos_disp = df_activos_disp.rename(columns={
        'descripcion_categoria': 'Categoría / Detalle',
        'valor_conv': col_act_head,
        'notas_aclaratorias': 'Notas'
    })
    st.dataframe(
        df_activos_disp,
        use_container_width=True,
        hide_index=True,
        column_config={
            'Categoría / Detalle': st.column_config.TextColumn('Categoría / Detalle', width=380),
            col_act_head: st.column_config.NumberColumn(col_act_head, format="%,.2f", width=220),
            'Notas': st.column_config.TextColumn('Notas', width=120)
        }
    )

    if not df_patrimonio.empty:
        st.subheader("📋 2. Determinación del Capital Regulatorio y Suficiencia Patrimonial")
        df_pat_disp = df_patrimonio[['codigo_cuenta', 'seccion_cap', 'valor_conv', 'notas_aclaratorias']].copy()
        df_pat_disp = df_pat_disp.rename(columns={
            'codigo_cuenta': 'Concepto / Cuenta',
            'seccion_cap': 'Sección',
            'valor_conv': col_act_head,
            'notas_aclaratorias': 'Notas'
        })
        st.dataframe(
            df_pat_disp,
            use_container_width=True,
            hide_index=True,
            column_config={
                'Concepto / Cuenta': st.column_config.TextColumn('Concepto / Cuenta', width=380),
                'Sección': st.column_config.TextColumn('Sección', width=160),
                col_act_head: st.column_config.NumberColumn(col_act_head, format="%,.2f", width=200),
                'Notas': st.column_config.TextColumn('Notas', width=100)
            }
        )

    if not df_ratios.empty:
        st.subheader("📋 3. Ratios Regulatorios y Coeficiente de Adecuación Patrimonial (CAP)")
        df_rat_disp = df_ratios[['codigo_ratio', 'valor', 'notas_aclaratorias']].copy()
        
        # Multiplicación por 100 para mostrar el porcentaje correcto
        df_rat_disp['valor_pct'] = df_rat_disp['valor'].fillna(0) * 100
        
        df_rat_disp = df_rat_disp.drop(columns=['valor']).rename(columns={
            'codigo_ratio': 'Indicador / Ratio Regulatorio',
            'valor_pct': 'Porcentaje (%)',
            'notas_aclaratorias': 'Notas'
        })
        st.dataframe(
            df_rat_disp,
            use_container_width=True,
            hide_index=True,
            column_config={
                'Indicador / Ratio Regulatorio': st.column_config.TextColumn('Indicador / Ratio Regulatorio', width=450),
                'Porcentaje (%)': st.column_config.NumberColumn('Porcentaje (%)', format="%.2f %%", width=200),
                'Notas': st.column_config.TextColumn('Notas', width=120)
            }
        )

    # Notas Aclaratorias
    query_notas = """
        SELECT DISTINCT notas_aclaratorias 
        FROM (
            SELECT notas_aclaratorias FROM activos_riesgo_valores v JOIN plan_categorias_riesgo c ON v.id_plan_cat = c.id_plan_cat WHERE v.fecha_corte = %s
            UNION
            SELECT notas_aclaratorias FROM suficiencia_patrimonial_valores v JOIN plan_suficiencia_patrimonial p ON v.id_plan_cap = p.id_plan_cap WHERE v.fecha_corte = %s
            UNION
            SELECT notas_aclaratorias FROM ratios_regulatorios_valores v JOIN plan_ratios_regulatorios r ON v.id_plan_ratio = r.id_plan_ratio WHERE v.fecha_corte = %s
        ) sub 
        WHERE notas_aclaratorias IS NOT NULL AND notas_aclaratorias != ''
    """
    df_notas = consultar_db(query_notas, (fecha_sel, fecha_sel, fecha_sel))

    if not df_notas.empty:
        with st.expander("📌 Notas Aclaratorias Registradas en el Reporte", expanded=False):
            for idx, n_row in df_notas.iterrows():
                with st.container(border=True):
                    st.markdown(f"**Nota ({idx+1})**")
                    st.caption(n_row['notas_aclaratorias'])

    excel_bytes = generar_excel_ponderacion(df_activos_disp, df_pat_disp if not df_patrimonio.empty else pd.DataFrame(), df_rat_disp if not df_ratios.empty else pd.DataFrame(), df_notas, sigla_banco, fecha_sel)
    _, col_btn = st.columns([3, 1])
    with col_btn:
        st.download_button(
            "📥 Descargar Reporte Excel", 
            data=excel_bytes, 
            file_name=f"Ponderacion_Activos_CAP_{sigla_banco}_{fecha_sel}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

if __name__ == "__main__":
    mostrar_explorador_ponderacion()