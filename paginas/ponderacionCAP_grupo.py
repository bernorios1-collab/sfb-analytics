# ==============================================================================
# FUNCIONALIDAD DEL ARCHIVO (ponderacionCAP_grupo.py):
# Módulo para visualizar, analizar y exportar los Activos Ponderados por Riesgo,
# Suficiencia Patrimonial y Coeficiente de Adecuación Patrimonial (CAP) agrupados 
# por entidad financiera según el Grupo ASFI seleccionado. Soporta grupos masivos
# (como Cooperativas con más de 40 entidades) con gráficos escalables y tabla unificada.
# ==============================================================================

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import io
from sqlalchemy import text
from config_db import obtener_engine
from scrapers.indicadores_bcb import obtener_indicadores_bcb

@st.cache_data(ttl=600)
def consultar_db(query, params=None):
    engine = obtener_engine()
    try:
        return pd.read_sql_query(text(query), engine, params=params)
    except Exception as e:
        st.error(f"Error técnico consultando base de datos: {e}")
        return pd.DataFrame()

def mostrar_ponderacion_grupo():
    st.header("📊 Ponderación de Activos y CAP por Grupo de Entidades")
    
    dict_indicadores = obtener_indicadores_bcb()
    if "moneda_seleccionada_pond_grupo" not in st.session_state: 
        st.session_state.moneda_seleccionada_pond_grupo = list(dict_indicadores.keys())[0]

    # --- 1. FILTROS DE CONFIGURACIÓN ---
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([0.5, 0.8, 1.2, 1.2])
        
        df_years = consultar_db("""
            SELECT DISTINCT EXTRACT(YEAR FROM fecha_corte)::int as anio 
            FROM activos_riesgo_valores 
            ORDER BY anio DESC
        """)
        if df_years.empty:
            st.warning("No hay datos disponibles de Activos Ponderados en la base de datos.")
            return
            
        anio_sel = c1.selectbox("Año", df_years['anio'].tolist(), key="sb_anio_pond_grp")
        
        df_f = consultar_db("""
            SELECT DISTINCT fecha_corte 
            FROM activos_riesgo_valores 
            WHERE EXTRACT(YEAR FROM fecha_corte) = :anio 
            ORDER BY fecha_corte DESC
        """, {"anio": anio_sel})
        
        fecha_sel = c2.selectbox("Corte Base", df_f['fecha_corte'].astype(str).tolist(), key="sb_corte_pond_grp")
        
        df_grupos = consultar_db("SELECT id_grupo, nombre_grupo FROM grupos_asfi ORDER BY id_grupo ASC")
        grupo_sel = c3.selectbox("📂 Grupo ASFI", options=df_grupos['nombre_grupo'].tolist(), key="sb_grupo_pond_grp")
        id_g = int(df_grupos[df_grupos['nombre_grupo'] == grupo_sel]['id_grupo'].values[0])

        if st.session_state.moneda_seleccionada_pond_grupo not in dict_indicadores:
            st.session_state.moneda_seleccionada_pond_grupo = list(dict_indicadores.keys())[0]

        moneda_sel = c4.selectbox(
            "💰 Unidad de Medida", 
            list(dict_indicadores.keys()), 
            index=list(dict_indicadores.keys()).index(st.session_state.moneda_seleccionada_pond_grupo),
            key="sb_moneda_pond_grp"
        )
        st.session_state.moneda_seleccionada_pond_grupo = moneda_sel

        if len(dict_indicadores) == 1:
            st.caption("⚠️ No existe conectividad con BCB (Muestra únicamente datos expresados nominalmente en Bs.)")

    # --- 2. OBTENCIÓN DE ENTIDADES DEL GRUPO (Soporte Masivo) ---
    df_ent = consultar_db("""
        SELECT id_entidad, nombre_entidad as sigla, nombre_completo 
        FROM entidades 
        WHERE id_grupo = :id_grupo 
        ORDER BY 
            CASE WHEN nombre_entidad LIKE 'TS%%' OR UPPER(nombre_entidad) LIKE 'TOTAL%%' THEN 1 ELSE 0 END,
            nombre_completo ASC
    """, {"id_grupo": id_g})

    if df_ent.empty:
        st.warning(f"No se encontraron entidades asociadas al grupo **{grupo_sel}**.")
        return

    entidades_map = {}
    ids_entidades = []
    for _, r in df_ent.iterrows():
        eid = r['id_entidad']
        sigla = r['sigla']
        entidades_map[eid] = sigla
        ids_entidades.append(eid)

    factor_conv = dict_indicadores[moneda_sel]

    # --- 3. CONSULTA MATRICIAL DE PLANES Y VALORES UNIFICADOS ---
    query_act = """
        SELECT px.id_plan_cat as id_item, px.descripcion_categoria as concepto, px.es_totalizador, px.orden, 
               '1. ACTIVOS PONDERADOS' as seccion, false as es_porcentaje, v.id_entidad, v.valor
        FROM plan_categorias_riesgo px
        JOIN activos_riesgo_valores v ON px.id_plan_cat = v.id_plan_cat
        WHERE v.fecha_corte = :fecha AND v.id_entidad = ANY(:ids)
    """
    query_pat = """
        SELECT px.id_plan_cap as id_item, px.codigo_cuenta as concepto, px.es_totalizador, px.orden + 100 as orden, 
               '2. SUFICIENCIA PATRIMONIAL' as seccion, false as es_porcentaje, v.id_entidad, v.valor
        FROM plan_suficiencia_patrimonial px
        JOIN suficiencia_patrimonial_valores v ON px.id_plan_cap = v.id_plan_cap
        WHERE v.fecha_corte = :fecha AND v.id_entidad = ANY(:ids)
    """
    query_rat = """
        SELECT px.id_plan_ratio as id_item, px.codigo_ratio as concepto, false as es_totalizador, px.orden + 200 as orden, 
               '3. RATIOS REGULATORIOS' as seccion, true as es_porcentaje, v.id_entidad, v.valor
        FROM plan_ratios_regulatorios px
        JOIN ratios_regulatorios_valores v ON px.id_plan_ratio = v.id_plan_ratio
        WHERE v.fecha_corte = :fecha AND v.id_entidad = ANY(:ids)
    """

    df_full_raw = consultar_db(f"SELECT * FROM ({query_act} UNION ALL {query_pat} UNION ALL {query_rat}) t ORDER BY orden ASC", 
                               {"fecha": fecha_sel, "ids": ids_entidades})

    if df_full_raw.empty:
        st.warning("No existen registros procesados para la fecha y grupo seleccionados.")
        return

    df_full_raw['valor_conv'] = df_full_raw.apply(
        lambda r: r['valor'] / factor_conv if not r['es_porcentaje'] else r['valor'], axis=1
    )
    df_full_raw['valor_conv'] = df_full_raw['valor_conv'].fillna(0)

    # --- 4. ORDENAMIENTO ESTRICTO DE COLUMNAS (Totalizador al Final) ---
    cols_siglas_ordenadas = []
    id_ts = None
    for eid in ids_entidades:
        sig = entidades_map[eid]
        if sig.startswith("TS") or "TOTAL SISTEMA" in sig.upper() or "TOTAL" in sig.upper():
            id_ts = eid
        else:
            cols_siglas_ordenadas.append((eid, sig))
    
    if id_ts is not None:
        cols_siglas_ordenadas.append((id_ts, entidades_map[id_ts]))

    pivot_unificado = df_full_raw.pivot_table(
        index=['orden', 'seccion', 'concepto', 'es_totalizador', 'es_porcentaje'],
        columns='id_entidad',
        values='valor_conv',
        aggfunc='first'
    ).reset_index()

    pivot_unificado = pivot_unificado.sort_values('orden')

    # --- 5. GRÁFICO INTERACTIVO ESCALABLE (EXACTAMENTE 3 TRAZAS ORDENADAS) ---
    st.markdown("---")
    st.subheader("📈 Análisis Comparativo de Coeficientes y Ratios Regulatorios")
    
    fig = go.Figure()
    
    config_coefs = [
        {
            "filtro": "COEFICIENTE DE ADECUACIÓN PATRIMONIAL", 
            "nombre": "CAP (%)", 
            "color": "#004a99", 
            "tipo": "bar", 
            "opacidad": 1.0, 
            "line_style": None
        },
        {
            "filtro": "COEFICIENTE DE PONDERACIÓN DEL ACTIVO", 
            "nombre": "Coef. Ponderación Activo", 
            "color": "#6c757d", 
            "tipo": "scatter", 
            "opacidad": 0.8, 
            "line_style": "dash"
        },
        {
            "filtro": "COEFICIENTE DE INVERSIÓN EN ACTIVOS FIJOS", 
            "nombre": "Coef. Inv. Activos Fijos", 
            "color": "#adb5bd", 
            "tipo": "scatter", 
            "opacidad": 0.7, 
            "line_style": "dot"
        }
    ]

    df_graf_base = df_full_raw[~df_full_raw['id_entidad'].isin([id_ts] if id_ts else [])]
    orden_siglas = [sig for _, sig in cols_siglas_ordenadas]

    for cfg in config_coefs:
        sub_df = df_graf_base[df_graf_base['concepto'].str.strip().str.upper().str.startswith(cfg["filtro"])]
        
        if not sub_df.empty:
            sub_df = sub_df.drop_duplicates(subset=['id_entidad']).copy()
            sub_df['sigla_entidad'] = sub_df['id_entidad'].map(entidades_map)
            sub_df['valor_pct'] = sub_df['valor'] * 100

            # Forzar orden categórico secuencial de izquierda a derecha
            sub_df['sigla_entidad'] = pd.Categorical(sub_df['sigla_entidad'], categories=orden_siglas, ordered=True)
            sub_df = sub_df.sort_values('sigla_entidad')

            if cfg["tipo"] == "bar":
                fig.add_trace(go.Bar(
                    x=sub_df['sigla_entidad'],
                    y=sub_df['valor_pct'],
                    name=cfg["nombre"],
                    marker_color=cfg["color"],
                    text=[f"{v:.2f}%" for v in sub_df['valor_pct']],
                    textposition='auto'
                ))
            else:
                fig.add_trace(go.Scatter(
                    x=sub_df['sigla_entidad'],
                    y=sub_df['valor_pct'],
                    name=cfg["nombre"],
                    mode='lines+markers',
                    line=dict(color=cfg["color"], width=2, dash=cfg["line_style"]),
                    marker=dict(size=6, opacity=cfg["opacidad"])
                ))

    num_entidades_graf = len(df_graf_base['id_entidad'].unique())
    ancho_grafico = max(900, num_entidades_graf * 35)

    fig.update_layout(
        title=dict(text=f"Indicadores Regulatorios por Entidad (Grupo: {grupo_sel}) - {fecha_sel}", font=dict(size=14)),
        xaxis_title="Entidad Financiera",
        yaxis_title="Porcentaje (%)",
        height=480,
        width=ancho_grafico,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        yaxis=dict(gridcolor='rgba(128,128,128,0.2)'),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(tickangle=-45, dtick=1)
    )
    
    st.markdown('<div style="overflow-x: auto;">', unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=False, config={"scrollZoom": True})
    st.markdown('</div>', unsafe_allow_html=True)

    # --- 6. RENDERIZADO VISUAL UNIFICADO (Optimizado para Grupos Masivos) ---
    st.markdown("---")
    st.markdown(f"### 📋 Reporte Oficial Consolidado: {grupo_sel}")
    st.caption(f"**Fecha de Corte:** {fecha_sel} | **Unidad de Medida:** {moneda_sel} (Total de Entidades: {len(cols_siglas_ordenadas)})")

    st.markdown("""
    <style>
        .asfi-container {
            max-height: 600px;
            overflow-y: auto;
            overflow-x: auto;
            border: 2px solid var(--border-color);
            border-radius: 8px;
            margin-bottom: 1.5rem;
            background-color: var(--background-color);
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
        }
        .asfi-table {
            width: 100%;
            border-collapse: collapse;
            font-family: inherit;
        }
        .asfi-table thead th {
            position: sticky;
            top: 0;
            z-index: 100;
            background-color: var(--secondary-background-color);
            color: var(--text-color);
            font-size: 11px;
            font-weight: 700;
            padding: 8px 10px;
            border-bottom: 2px solid var(--border-color);
            border-left: 1px solid var(--border-color);
            text-align: right;
            white-space: nowrap;
        }
        .asfi-table thead th:first-child {
            text-align: left;
            min-width: 380px;
            left: 0;
            z-index: 102;
            background-color: var(--secondary-background-color);
        }
        .asfi-row-seccion {
            background-color: rgba(0, 74, 153, 0.12) !important;
            font-weight: bold;
            font-size: 11px;
            color: var(--text-color);
            padding: 8px 10px;
            border-bottom: 1px solid var(--border-color);
        }
        .asfi-row-concepto {
            padding: 5px 10px;
            font-size: 11px;
            color: var(--text-color);
            background-color: var(--background-color);
            border-bottom: 1px solid var(--border-color);
            border-right: 1px solid var(--border-color);
            white-space: nowrap;
            position: sticky;
            left: 0;
            z-index: 10;
        }
        .asfi-row-val {
            text-align: right;
            padding: 5px 10px;
            font-size: 11px;
            font-family: Consolas, monospace;
            color: var(--text-color);
            background-color: var(--background-color);
            border-bottom: 1px solid var(--border-color);
            border-left: 1px solid var(--border-color);
            white-space: nowrap;
        }
        .asfi-total-row td {
            font-weight: bold;
            background-color: rgba(0, 74, 153, 0.05) !important;
        }
    </style>
    """, unsafe_allow_html=True)

    th_html = '<th style="text-align:left;">CONCEPTO / DESCRIPCIÓN</th>'
    siglas_activas = []
    for eid, sig in cols_siglas_ordenadas:
        if eid in pivot_unificado.columns:
            th_html += f'<th>{sig}</th>'
            siglas_activas.append(eid)

    rows_html = []
    seccion_actual = ""

    for _, r in pivot_unificado.iterrows():
        sec = r['seccion']
        if sec != seccion_actual:
            seccion_actual = sec
            col_span_len = len(siglas_activas) + 1
            rows_html.append(f'<tr><td colspan="{col_span_len}" class="asfi-row-seccion"><b>{seccion_actual}</b></td></tr>')

        concepto = r['concepto']
        es_tot = r['es_totalizador']
        es_pct = r['es_porcentaje']
        tr_class = "asfi-total-row" if es_tot else ""
        
        tds = f'<td class="asfi-row-concepto"><b>{concepto}</b></td>' if es_tot else f'<td class="asfi-row-concepto">{concepto}</td>'
        
        for eid in siglas_activas:
            val = r[eid] if pd.notna(r[eid]) else 0.0
            if es_pct:
                val_fmt = f"{val * 100:,.2f}%"
            else:
                val_fmt = f"{val:,.2f}"
            tds += f'<td class="asfi-row-val">{val_fmt}</td>'
        
        rows_html.append(f'<tr class="{tr_class}">{tds}</tr>')

    html_code = f'<div class="asfi-container"><table class="asfi-table"><thead><tr>{th_html}</tr></thead><tbody>{"".join(rows_html)}</tbody></table></div>'
    st.markdown(html_code, unsafe_allow_html=True)

    # --- 7. EXPORTACIÓN A EXCEL UNIFICADO ---
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_exp = pivot_unificado.drop(columns=['orden', 'seccion', 'es_totalizador', 'es_porcentaje']).rename(columns={'concepto': 'CONCEPTO / DESCRIPCIÓN'})
        df_exp.to_excel(writer, index=False, sheet_name='Ponderacion_CAP_Consolidado')

    _, col_btn = st.columns([3, 1])
    with col_btn:
        st.download_button(
            "📥 Descargar Reporte Excel Unificado",
            data=output.getvalue(),
            file_name=f"Ponderacion_CAP_Grupo_Consolidado_{grupo_sel.replace(' ', '_')}_{fecha_sel}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

if __name__ == "__main__":
    mostrar_ponderacion_grupo()