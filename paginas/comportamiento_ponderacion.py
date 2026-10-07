# ==============================================================================
# FUNCIONALIDAD DEL ARCHIVO (comportamiento_ponderacion.py):
# Este script implementa una interfaz interactiva en Streamlit para analizar la 
# evolución temporal y las tendencias históricas de los Activos Ponderados por Riesgo,
# la Suficiencia Patrimonial y los Ratios Regulatorios (CAP) de entidades financieras
# o consolidados por grupo, con soporte multimoneda, gráficos de tendencia y exportación a Excel.
# ==============================================================================

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import io
from sqlalchemy import text
from config_db import obtener_engine
from scrapers.indicadores_bcb import obtener_indicadores_bcb

# --- FUNCIONES TÉCNICAS ---
@st.cache_data(ttl=600)
def consultar_db(query, params=None):
    engine = obtener_engine()
    try:
        return pd.read_sql_query(text(query), engine, params=params)
    except Exception as e:
        st.error(f"Error técnico: {e}")
        return pd.DataFrame()

def mostrar_comportamiento_ponderacion():
    st.header("📈 Comportamiento Histórico de Activos Ponderados y CAP")
    
    dict_indicadores = obtener_indicadores_bcb()
    if "moneda_seleccionada_comp_pond" not in st.session_state: 
        st.session_state.moneda_seleccionada_comp_pond = list(dict_indicadores.keys())[0]

    # --- 1. CONFIGURACIÓN DE CONSULTA Y FILTROS ---
    with st.container(border=True):
        c1, c2, c3, c4, c5 = st.columns([0.4, 0.6, 1.0, 0.8, 0.8])
        
        df_years = consultar_db("""
            SELECT DISTINCT EXTRACT(YEAR FROM fecha_corte)::int as anio 
            FROM activos_riesgo_valores 
            ORDER BY anio DESC
        """)
        if df_years.empty:
            st.warning("No hay datos de Activos Ponderados disponibles en la Base de Datos.")
            return

        anio_sel = c1.selectbox("Año", df_years['anio'].tolist(), key="sb_pond_anio")
        
        df_f = consultar_db("""
            SELECT DISTINCT fecha_corte 
            FROM activos_riesgo_valores 
            WHERE EXTRACT(YEAR FROM fecha_corte) = :anio 
            ORDER BY fecha_corte DESC
        """, {"anio": anio_sel})
        
        fecha_sel_input = c2.selectbox("Corte Base", df_f['fecha_corte'].astype(str).tolist(), key="sb_pond_corte")
        
        if st.session_state.moneda_seleccionada_comp_pond not in dict_indicadores:
            st.session_state.moneda_seleccionada_comp_pond = list(dict_indicadores.keys())[0]

        moneda_sel = c3.selectbox(
            "💰 Unidad de Medida", 
            list(dict_indicadores.keys()), 
            index=list(dict_indicadores.keys()).index(st.session_state.moneda_seleccionada_comp_pond),
            key="sb_pond_moneda"
        )
        st.session_state.moneda_seleccionada_comp_pond = moneda_sel

        frecuencia = c4.selectbox("🔄 Frecuencia", ["Mensual", "Trimestral", "Semestral", "Anual"], key="sb_pond_frec")
        periodos = c5.number_input("🔢 Periodos", min_value=1, max_value=24, value=6, key="sb_pond_periodos")

        f1, f2 = st.columns([1.3, 1.7])
        df_grupos = consultar_db("SELECT id_grupo, nombre_grupo FROM grupos_asfi ORDER BY id_grupo ASC")
        grupo_sel = f1.selectbox("📂 Grupo ASFI", options=df_grupos['nombre_grupo'].tolist(), key="sb_pond_grupo")
        id_g = int(df_grupos[df_grupos['nombre_grupo'] == grupo_sel]['id_grupo'].values[0])
        
        df_ent = consultar_db("""
            SELECT id_entidad, nombre_entidad as sigla, nombre_completo 
            FROM entidades 
            WHERE id_grupo = :id_grupo 
            ORDER BY 
                CASE WHEN nombre_entidad LIKE 'TS%%' THEN 0 ELSE 1 END,
                nombre_completo ASC
        """, {"id_grupo": id_g})
        
        opciones_ent = {}
        for _, r in df_ent.iterrows():
            nombre = r['nombre_completo'] if pd.notna(r['nombre_completo']) and r['nombre_completo'] != "" else r['sigla']
            opciones_ent[f"{nombre} ({r['sigla']})"] = {
                "sigla": r['sigla'],
                "id_entidad": r['id_entidad']
            }
            
        entidad_display = f2.selectbox("🏛️ Entidad Financiera", options=list(opciones_ent.keys()), key="sb_pond_entidad")
        sigla_sel = opciones_ent[entidad_display]["sigla"]
        id_entidad_sel = opciones_ent[entidad_display]["id_entidad"]
        
        if len(dict_indicadores) == 1:
            st.caption("⚠️ No existe conectividad con BCB (Muestra únicamente datos expresados nominalmente en Bs.)")

    # --- 2. LÓGICA DE TEMPORALIDAD FILTRADA POR ENTIDAD ---
    map_m = {"Mensual": 1, "Trimestral": 3, "Semestral": 6, "Anual": 12}
    salto = map_m[frecuencia]
    
    es_total_sistema = sigla_sel.startswith("TS") or "TOTAL SISTEMA" in entidad_display.upper()

    df_f_entidad = consultar_db("""
        SELECT DISTINCT fecha_corte 
        FROM activos_riesgo_valores 
        WHERE id_entidad = :id_entidad
        ORDER BY fecha_corte DESC
    """, {"id_entidad": id_entidad_sel})
    
    lista_f = df_f_entidad['fecha_corte'].astype(str).tolist() if not df_f_entidad.empty else []
    
    if not lista_f:
        st.info(f"⚠️ La entidad **{sigla_sel}** no registra datos históricos de activos ponderados.")
        return

    try:
        idx = lista_f.index(fecha_sel_input)
        fechas_req = lista_f[idx : idx + (periodos * salto) : salto]
    except ValueError:
        fechas_req = lista_f[0 : periodos * salto : salto]

    if not fechas_req:
        fechas_req = [lista_f[0]]

    # --- CONSULTAS HISTÓRICAS (Activos de Riesgo) ---
    if es_total_sistema:
        query_act = """
            SELECT v.fecha_corte, c.descripcion_categoria, c.es_totalizador, c.orden, SUM(v.valor) as valor
            FROM plan_categorias_riesgo c
            JOIN activos_riesgo_valores v ON c.id_plan_cat = v.id_plan_cat
            JOIN entidades e ON v.id_entidad = e.id_entidad
            WHERE e.id_grupo = :id_grupo AND v.fecha_corte IN :fechas AND v.id_entidad != :id_entidad
            GROUP BY v.fecha_corte, c.id_plan_cat, c.descripcion_categoria, c.es_totalizador, c.orden
            ORDER BY c.orden ASC, v.fecha_corte ASC
        """
        df_act = consultar_db(query_act, {"id_grupo": id_g, "fechas": tuple(fechas_req), "id_entidad": id_entidad_sel})
        if df_act.empty:
            q_dir = """
                SELECT v.fecha_corte, c.descripcion_categoria, c.es_totalizador, c.orden, v.valor
                FROM plan_categorias_riesgo c
                JOIN activos_riesgo_valores v ON c.id_plan_cat = v.id_plan_cat
                WHERE v.id_entidad = :id_entidad AND v.fecha_corte IN :fechas
                ORDER BY c.orden ASC, v.fecha_corte ASC
            """
            df_act = consultar_db(q_dir, {"id_entidad": id_entidad_sel, "fechas": tuple(fechas_req)})
    else:
        query_act = """
            SELECT v.fecha_corte, c.descripcion_categoria, c.es_totalizador, c.orden, v.valor
            FROM plan_categorias_riesgo c
            JOIN activos_riesgo_valores v ON c.id_plan_cat = v.id_plan_cat
            WHERE v.id_entidad = :id_entidad AND v.fecha_corte IN :fechas
            ORDER BY c.orden ASC, v.fecha_corte ASC
        """
        df_act = consultar_db(query_act, {"id_entidad": id_entidad_sel, "fechas": tuple(fechas_req)})

    if df_act.empty:
        st.warning("No se encontraron registros históricos de activos ponderados para el periodo seleccionado.")
        return

    # Suficiencia Patrimonial Histórica
    if es_total_sistema:
        query_pat = """
            SELECT v.fecha_corte, p.codigo_cuenta, p.seccion_cap, p.es_totalizador, p.orden, SUM(v.valor) as valor
            FROM plan_suficiencia_patrimonial p
            JOIN suficiencia_patrimonial_valores v ON p.id_plan_cap = v.id_plan_cap
            JOIN entidades e ON v.id_entidad = e.id_entidad
            WHERE e.id_grupo = :id_grupo AND v.fecha_corte IN :fechas AND v.id_entidad != :id_entidad
            GROUP BY v.fecha_corte, p.id_plan_cap, p.codigo_cuenta, p.seccion_cap, p.es_totalizador, p.orden
            ORDER BY p.orden ASC, v.fecha_corte ASC
        """
        df_pat = consultar_db(query_pat, {"id_grupo": id_g, "fechas": tuple(fechas_req), "id_entidad": id_entidad_sel})
        if df_pat.empty:
            q_pat_dir = """
                SELECT v.fecha_corte, p.codigo_cuenta, p.seccion_cap, p.es_totalizador, p.orden, v.valor
                FROM plan_suficiencia_patrimonial p
                JOIN suficiencia_patrimonial_valores v ON p.id_plan_cap = v.id_plan_cap
                WHERE v.id_entidad = :id_entidad AND v.fecha_corte IN :fechas
                ORDER BY p.orden ASC, v.fecha_corte ASC
            """
            df_pat = consultar_db(q_pat_dir, {"id_entidad": id_entidad_sel, "fechas": tuple(fechas_req)})
    else:
        query_pat = """
            SELECT v.fecha_corte, p.codigo_cuenta, p.seccion_cap, p.es_totalizador, p.orden, v.valor
            FROM plan_suficiencia_patrimonial p
            JOIN suficiencia_patrimonial_valores v ON p.id_plan_cap = v.id_plan_cap
            WHERE v.id_entidad = :id_entidad AND v.fecha_corte IN :fechas
            ORDER BY p.orden ASC, v.fecha_corte ASC
        """
        df_pat = consultar_db(query_pat, {"id_entidad": id_entidad_sel, "fechas": tuple(fechas_req)})

    # Ratios Regulatorios Históricos
    if es_total_sistema:
        query_rat = """
            SELECT v.fecha_corte, r.codigo_ratio, r.orden, AVG(v.valor) as valor
            FROM plan_ratios_regulatorios r
            JOIN ratios_regulatorios_valores v ON r.id_plan_ratio = v.id_plan_ratio
            JOIN entidades e ON v.id_entidad = e.id_entidad
            WHERE e.id_grupo = :id_grupo AND v.fecha_corte IN :fechas AND v.id_entidad != :id_entidad
            GROUP BY v.fecha_corte, r.id_plan_ratio, r.codigo_ratio, r.orden
            ORDER BY r.orden ASC, v.fecha_corte ASC
        """
        df_rat = consultar_db(query_rat, {"id_grupo": id_g, "fechas": tuple(fechas_req), "id_entidad": id_entidad_sel})
        if df_rat.empty:
            q_rat_dir = """
                SELECT v.fecha_corte, r.codigo_ratio, r.orden, v.valor
                FROM plan_ratios_regulatorios r
                JOIN ratios_regulatorios_valores v ON r.id_plan_ratio = v.id_plan_ratio
                WHERE v.id_entidad = :id_entidad AND v.fecha_corte IN :fechas
                ORDER BY r.orden ASC, v.fecha_corte ASC
            """
            df_rat = consultar_db(q_rat_dir, {"id_entidad": id_entidad_sel, "fechas": tuple(fechas_req)})
    else:
        query_rat = """
            SELECT v.fecha_corte, r.codigo_ratio, r.orden, v.valor
            FROM plan_ratios_regulatorios r
            JOIN ratios_regulatorios_valores v ON r.id_plan_ratio = v.id_plan_ratio
            WHERE v.id_entidad = :id_entidad AND v.fecha_corte IN :fechas
            ORDER BY r.orden ASC, v.fecha_corte ASC
        """
        df_rat = consultar_db(query_rat, {"id_entidad": id_entidad_sel, "fechas": tuple(fechas_req)})

    # Procesamiento de fechas y etiquetas
    df_act['fecha_dt'] = pd.to_datetime(df_act['fecha_corte'])
    df_act['fecha_label'] = df_act['fecha_dt'].dt.strftime('%b %Y')
    orden_fechas_asc = sorted(df_act['fecha_label'].unique(), key=lambda x: pd.to_datetime(x, format='%b %Y'))

    factor_conv = dict_indicadores[moneda_sel]
    nombre_moneda = moneda_sel.split(' ')[0]

    df_act['valor_conv'] = df_act['valor'].fillna(0) / factor_conv
    if not df_pat.empty:
        df_pat['fecha_label'] = pd.to_datetime(df_pat['fecha_corte']).dt.strftime('%b %Y')
        df_pat['valor_conv'] = df_pat['valor'].fillna(0) / factor_conv
    if not df_rat.empty:
        df_rat['fecha_label'] = pd.to_datetime(df_rat['fecha_corte']).dt.strftime('%b %Y')
        df_rat['valor_pct'] = df_rat['valor'].fillna(0) * 100

    # --- 3. GRÁFICOS DE TENDENCIA ---
    st.markdown("### 📊 Tendencias Clave: CAP y Activos Ponderados")

    plotly_layout_theme = dict(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(showgrid=False, type='category'),
        yaxis=dict(gridcolor='rgba(128,128,128,0.2)'),
        margin=dict(t=35, b=10, l=10, r=10)
    )

    g1, g2 = st.columns(2)
    with g1:
        fig1 = go.Figure()
        if not df_rat.empty:
            cap_sub = df_rat[df_rat['codigo_ratio'].str.upper().str.contains("COEFICIENTE DE ADECUACIÓN PATRIMONIAL", na=False)]
            if not cap_sub.empty:
                cap_serie = cap_sub.set_index('fecha_label')['valor_pct'].reindex(orden_fechas_asc)
                fig1.add_trace(go.Scatter(
                    x=orden_fechas_asc,
                    y=cap_serie.values,
                    name='CAP (%)',
                    mode='lines+markers+text',
                    text=[f"{v:.2f}%" if pd.notnull(v) else "" for v in cap_serie.values],
                    textposition='top center',
                    line=dict(color='#004a99', width=2.5)
                ))
        fig1.update_layout(
            height=300,
            title="Evolución del Coeficiente de Adecuación Patrimonial (CAP %)",
            hovermode="x unified",
            **plotly_layout_theme
        )
        st.plotly_chart(fig1, use_container_width=True)

    with g2:
        fig2 = go.Figure()
        tot_act_sub = df_act[df_act['descripcion_categoria'].str.upper().str.contains("TOTAL ACTIVO Y CONTINGENTE", na=False)]
        if not tot_act_sub.empty:
            tot_act_serie = tot_act_sub.set_index('fecha_label')['valor_conv'].reindex(orden_fechas_asc)
            fig2.add_trace(go.Scatter(
                x=orden_fechas_asc,
                y=tot_act_serie.values,
                name='Total Activo y Contingente',
                mode='lines+markers',
                line=dict(color='#2ca02c', width=2.5)
            ))
        fig2.update_layout(
            height=300,
            title=f"Evolución Total Activo y Contingente ({nombre_moneda})",
            hovermode="x unified",
            **plotly_layout_theme
        )
        st.plotly_chart(fig2, use_container_width=True)

    # --- 4. TABLAS PIVOTADAS HISTÓRICAS ---
    st.markdown("---")
    st.subheader(f"📋 1. Histórico de Activos Ponderados por Riesgo ({nombre_moneda})")

    df_act_pivot = df_act.pivot_table(index=['orden', 'descripcion_categoria'], columns='fecha_label', values='valor_conv', aggfunc='first').reset_index()
    df_act_pivot = df_act_pivot.sort_values('orden').drop(columns=['orden'])
    
    cols_fechas_desc = sorted(orden_fechas_asc, key=lambda x: pd.to_datetime(x, format='%b %Y'), reverse=True)
    
    rows_act = []
    for _, r in df_act_pivot.iterrows():
        cat_nom = r['descripcion_categoria']
        vals_html = "".join([f'<td class="comp-col-val">{r[f] if pd.notna(r[f]) else 0.0:,.2f}</td>' for f in cols_fechas_desc if f in r])
        rows_act.append(f'<tr><td class="comp-col-ind">{cat_nom}</td>{vals_html}</tr>')
    
    th_fechas = "".join([f'<th style="text-align:right; min-width:100px;">{f}</th>' for f in cols_fechas_desc])
    html_act = f'<div class="comp-container"><table class="comp-table"><thead><tr><th style="width:35%; text-align:left;">CATEGORÍA / DETALLE</th>{th_fechas}</tr></thead><tbody>{"".join(rows_act)}</tbody></table></div>'
    st.markdown(html_act, unsafe_allow_html=True)

    if not df_pat.empty:
        st.subheader(f"📋 2. Histórico de Suficiencia Patrimonial ({nombre_moneda})")
        df_pat_pivot = df_pat.pivot_table(index=['orden', 'codigo_cuenta', 'seccion_cap'], columns='fecha_label', values='valor_conv', aggfunc='first').reset_index()
        df_pat_pivot = df_pat_pivot.sort_values('orden').drop(columns=['orden'])
        
        rows_pat = []
        for _, r in df_pat_pivot.iterrows():
            c_nom = f"{r['codigo_cuenta']} ({r['seccion_cap']})"
            vals_html = "".join([f'<td class="comp-col-val">{r[f] if pd.notna(r[f]) else 0.0:,.2f}</td>' for f in cols_fechas_desc if f in r])
            rows_pat.append(f'<tr><td class="comp-col-ind">{c_nom}</td>{vals_html}</tr>')
        
        html_pat = f'<div class="comp-container"><table class="comp-table"><thead><tr><th style="width:35%; text-align:left;">CONCEPTO / CUENTA</th>{th_fechas}</tr></thead><tbody>{"".join(rows_pat)}</tbody></table></div>'
        st.markdown(html_pat, unsafe_allow_html=True)

    if not df_rat.empty:
        st.subheader("📋 3. Histórico de Ratios Regulatorios y CAP (%)")
        df_rat_pivot = df_rat.pivot_table(index=['orden', 'codigo_ratio'], columns='fecha_label', values='valor_pct', aggfunc='first').reset_index()
        df_rat_pivot = df_rat_pivot.sort_values('orden').drop(columns=['orden'])
        
        rows_rat = []
        for _, r in df_rat_pivot.iterrows():
            r_nom = r['codigo_ratio']
            vals_html = "".join([f'<td class="comp-col-val">{r[f] if pd.notna(r[f]) else 0.0:,.2f}%</td>' for f in cols_fechas_desc if f in r])
            rows_rat.append(f'<tr><td class="comp-col-ind">{r_nom}</td>{vals_html}</tr>')
        
        html_rat = f'<div class="comp-container"><table class="comp-table"><thead><tr><th style="width:35%; text-align:left;">INDICADOR / RATIO</th>{th_fechas}</tr></thead><tbody>{"".join(rows_rat)}</tbody></table></div>'
        st.markdown(html_rat, unsafe_allow_html=True)

    st.markdown("""
    <style>
        .comp-container {
            max-height: 450px;
            overflow-y: auto;
            overflow-x: auto;
            border: 2px solid var(--border-color);
            border-radius: 8px;
            margin-bottom: 1rem;
            background-color: var(--background-color);
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
        }
        .comp-table {
            width: 100%;
            border-collapse: collapse;
            font-family: inherit;
        }
        .comp-table thead th {
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
            text-transform: uppercase;
        }
        .comp-col-ind {
            width: 35%;
            padding: 6px 10px;
            font-size: 11px;
            color: var(--text-color);
            background-color: var(--background-color);
            border-bottom: 1px solid var(--border-color);
            border-right: 1px solid var(--border-color);
            white-space: nowrap;
        }
        .comp-col-val {
            text-align: right;
            padding: 6px 10px;
            font-size: 11px;
            font-family: Consolas, monospace;
            color: var(--text-color);
            background-color: var(--background-color);
            border-bottom: 1px solid var(--border-color);
            border-left: 1px solid var(--border-color);
            white-space: nowrap;
        }
        .comp-table tbody tr:hover td {
            background-color: var(--secondary-background-color) !important;
            opacity: 0.95;
        }
    </style>
    """, unsafe_allow_html=True)

    # --- 5. EXPORTACIÓN A EXCEL ---
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as wr:
        if not df_act_pivot.empty:
            df_act_pivot.to_excel(wr, index=False, sheet_name='Activos_Riesgo_Hist')
        if not df_pat.empty and 'df_pat_pivot' in locals():
            df_pat_pivot.to_excel(wr, index=False, sheet_name='Suficiencia_Pat_Hist')
        if not df_rat.empty and 'df_rat_pivot' in locals():
            df_rat_pivot.to_excel(wr, index=False, sheet_name='Ratios_Reg_Hist')

    _, col_boton = st.columns([3, 1])
    with col_boton:
        st.download_button(
            "📥 Exportar Excel",
            buf.getvalue(),
            f"comportamiento_ponderacion_{sigla_sel}.xlsx",
            use_container_width=True
        )

if __name__ == "__main__":
    mostrar_comportamiento_ponderacion()