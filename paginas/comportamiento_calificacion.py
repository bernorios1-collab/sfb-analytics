# ==============================================================================
# FUNCIONALIDAD DEL ARCHIVO (comportamiento_calificacion.py):
# Este script implementa una interfaz interactiva en Streamlit para analizar la 
# evolución temporal y las tendencias históricas de la Calificación de Cartera 
# y Contingente (Categorías A a F, previsiones, índice de mora y cobertura)
# con notas dinámicas desde la BD, estructura y formato oficial de los reportes ASFI.
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

def mostrar_comportamiento_calificacion():
    st.header("📈 Comportamiento Histórico de Calificación de Cartera")
    
    dict_indicadores = obtener_indicadores_bcb()
    if "moneda_seleccionada_comport_calif" not in st.session_state: 
        st.session_state.moneda_seleccionada_comport_calif = list(dict_indicadores.keys())[0]

    # --- 1. CONFIGURACIÓN DE CONSULTA Y FILTROS ---
    with st.container(border=True):
        c1, c2, c3, c4, c5 = st.columns([0.4, 0.6, 1.0, 0.8, 0.8])
        
        df_years = consultar_db("""
            SELECT DISTINCT EXTRACT(YEAR FROM fecha_corte)::int as anio 
            FROM calificacion_cartera 
            ORDER BY anio DESC
        """)
        if df_years.empty:
            st.warning("No hay datos de Calificación de Cartera disponibles en la Base de Datos.")
            return

        anio_sel = c1.selectbox("Año", df_years['anio'].tolist(), key="sb_cc_anio")
        
        df_f = consultar_db("""
            SELECT DISTINCT fecha_corte 
            FROM calificacion_cartera 
            WHERE EXTRACT(YEAR FROM fecha_corte) = :anio 
            ORDER BY fecha_corte DESC
        """, {"anio": anio_sel})
        
        fecha_sel_input = c2.selectbox("Corte Base", df_f['fecha_corte'].astype(str).tolist(), key="sb_cc_corte")
        
        if st.session_state.moneda_seleccionada_comport_calif not in dict_indicadores:
            st.session_state.moneda_seleccionada_comport_calif = list(dict_indicadores.keys())[0]

        moneda_sel = c3.selectbox(
            "💰 Unidad de Medida", 
            list(dict_indicadores.keys()), 
            index=list(dict_indicadores.keys()).index(st.session_state.moneda_seleccionada_comport_calif),
            key="sb_cc_moneda"
        )
        st.session_state.moneda_seleccionada_comport_calif = moneda_sel

        frecuencia = c4.selectbox("🔄 Frecuencia", ["Mensual", "Trimestral", "Semestral", "Anual"], key="sb_cc_frec")
        periodos = c5.number_input("🔢 Periodos", min_value=1, max_value=24, value=6, key="sb_cc_periodos")

        f1, f2 = st.columns([1.3, 1.7])
        df_grupos = consultar_db("SELECT id_grupo, nombre_grupo FROM grupos_asfi ORDER BY id_grupo ASC")
        grupo_sel = f1.selectbox("📂 Grupo ASFI", options=df_grupos['nombre_grupo'].tolist(), key="sb_cc_grupo")
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
            
        entidad_display = f2.selectbox("🏛️ Entidad Financiera", options=list(opciones_ent.keys()), key="sb_cc_entidad")
        sigla_sel = opciones_ent[entidad_display]["sigla"]
        id_entidad_sel = opciones_ent[entidad_display]["id_entidad"]
        
        if len(dict_indicadores) == 1:
            st.caption("⚠️ No existe conectividad con BCB (Muestra únicamente datos expresados nominalmente en Bs.)")

    # --- 2. LÓGICA DE TEMPORALIDAD FILTRADA POR ENTIDAD ---
    map_m = {"Mensual": 1, "Trimestral": 3, "Semestral": 6, "Anual": 12}
    salto = map_m[frecuencia]
    
    es_total_sistema = sigla_sel.startswith("TS") or "TOTAL SISTEMA" in entidad_display.upper()

    if es_total_sistema:
        df_f_entidad = consultar_db("""
            SELECT DISTINCT fecha_corte 
            FROM calificacion_cartera 
            WHERE id_grupo = :id_grupo
            ORDER BY fecha_corte DESC
        """, {"id_grupo": id_g})
    else:
        df_f_entidad = consultar_db("""
            SELECT DISTINCT fecha_corte 
            FROM calificacion_cartera 
            WHERE id_entidad = :id_entidad
            ORDER BY fecha_corte DESC
        """, {"id_entidad": id_entidad_sel})
    
    lista_f = df_f_entidad['fecha_corte'].astype(str).tolist() if not df_f_entidad.empty else []
    
    if not lista_f:
        st.info(f"⚠️ La entidad **{sigla_sel}** no registra datos históricos cargados en la tabla de calificación de cartera.")
        return

    try:
        idx = lista_f.index(fecha_sel_input)
        fechas_req = lista_f[idx : idx + (periodos * salto) : salto]
    except ValueError:
        fechas_req = lista_f[0 : periodos * salto : salto]

    if not fechas_req:
        fechas_req = [lista_f[0]]

    # Consulta adaptativa (Consolidado Grupo vs Entidad Individual)
    if es_total_sistema:
        query = """
            SELECT 
                fecha_corte,
                SUM(categoria_a) as categoria_a, SUM(prevision_a) as prevision_a,
                SUM(categoria_b) as categoria_b, SUM(prevision_b) as prevision_b,
                SUM(categoria_c) as categoria_c, SUM(prevision_c) as prevision_c,
                SUM(categoria_d) as categoria_d, SUM(prevision_d) as prevision_d,
                SUM(categoria_e) as categoria_e, SUM(prevision_e) as prevision_e,
                SUM(categoria_f) as categoria_f, SUM(prevision_f) as prevision_f,
                SUM(total_cartera) as total_cartera, SUM(total_prevision) as total_prevision
            FROM calificacion_cartera 
            WHERE id_grupo = :id_grupo AND fecha_corte IN :fechas AND id_entidad != :id_entidad
            GROUP BY fecha_corte
            ORDER BY fecha_corte ASC
        """
        df_raw = consultar_db(query, {"id_grupo": id_g, "fechas": tuple(fechas_req), "id_entidad": id_entidad_sel})
        if df_raw.empty:
            query_direct = "SELECT * FROM calificacion_cartera WHERE id_entidad = :id_entidad AND fecha_corte IN :fechas ORDER BY fecha_corte ASC"
            df_raw = consultar_db(query_direct, {"id_entidad": id_entidad_sel, "fechas": tuple(fechas_req)})
    else:
        query = """
            SELECT 
                fecha_corte,
                categoria_a, prevision_a,
                categoria_b, prevision_b,
                categoria_c, prevision_c,
                categoria_d, prevision_d,
                categoria_e, prevision_e,
                categoria_f, prevision_f,
                total_cartera, total_prevision
            FROM calificacion_cartera 
            WHERE id_entidad = :id_entidad AND fecha_corte IN :fechas
            ORDER BY fecha_corte ASC
        """
        df_raw = consultar_db(query, {"id_entidad": id_entidad_sel, "fechas": tuple(fechas_req)})

    if df_raw.empty:
        st.warning(f"No se encontraron registros de calificación de cartera para **{sigla_sel}** en los periodos consultados.")
        return

    df_raw['fecha_dt'] = pd.to_datetime(df_raw['fecha_corte'])
    df_raw['fecha_label'] = df_raw['fecha_dt'].dt.strftime('%b %Y')
    orden_fechas_asc = sorted(df_raw['fecha_label'].unique(), key=lambda x: pd.to_datetime(x, format='%b %Y'))

    # Conversión por tipo de cambio / unidad de medida
    factor_conv = dict_indicadores[moneda_sel]
    nombre_moneda = moneda_sel.split(' ')[0]

    cols_montos = ['categoria_a', 'prevision_a', 'categoria_b', 'prevision_b', 
                   'categoria_c', 'prevision_c', 'categoria_d', 'prevision_d', 
                   'categoria_e', 'prevision_e', 'categoria_f', 'prevision_f', 
                   'total_cartera', 'total_prevision']
    for c in cols_montos:
        if c in df_raw.columns:
            df_raw[c] = pd.to_numeric(df_raw[c], errors='coerce').fillna(0) / factor_conv

    # Cálculos derivados (Cartera Incumplida C-F, Mora %, Cobertura %)
    df_raw['cartera_incumplida'] = df_raw['categoria_c'] + df_raw['categoria_d'] + df_raw['categoria_e'] + df_raw['categoria_f']
    df_raw['mora_pct'] = (df_raw['cartera_incumplida'] / df_raw['total_cartera'].replace(0, pd.NA)) * 100
    df_raw['cobertura_pct'] = (df_raw['total_prevision'] / df_raw['cartera_incumplida'].replace(0, pd.NA)) * 100
    df_raw['porcentaje_general'] = (df_raw['total_prevision'] / df_raw['total_cartera'].replace(0, pd.NA)) * 100

    # --- 3. GRÁFICOS REPRESENTATIVOS DE TENDENCIA ---
    st.markdown("### 📊 Evolución Histórica de Calidad y Cobertura")

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
        fig1.add_trace(go.Bar(x=df_raw['fecha_label'], y=df_raw['categoria_a'], name='Cat. A', marker_color='#1f77b4'))
        fig1.add_trace(go.Bar(x=df_raw['fecha_label'], y=df_raw['categoria_b'], name='Cat. B', marker_color='#aec7e8'))
        fig1.add_trace(go.Bar(x=df_raw['fecha_label'], y=df_raw['categoria_c'], name='Cat. C', marker_color='#ff7f0e'))
        fig1.add_trace(go.Bar(x=df_raw['fecha_label'], y=df_raw['categoria_d'], name='Cat. D', marker_color='#ffbb78'))
        fig1.add_trace(go.Bar(x=df_raw['fecha_label'], y=df_raw['categoria_e'], name='Cat. E', marker_color='#d62728'))
        fig1.add_trace(go.Bar(x=df_raw['fecha_label'], y=df_raw['categoria_f'], name='Cat. F', marker_color='#8c564b'))
        
        fig1.update_layout(
            barmode='stack',
            height=300,
            title=f"Estructura de Cartera por Categoría ({nombre_moneda})",
            hovermode="x unified",
            **plotly_layout_theme
        )
        st.plotly_chart(fig1, use_container_width=True)

    with g2:
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(
            x=df_raw['fecha_label'], 
            y=df_raw['mora_pct'], 
            name='Índice Mora (C a F %)', 
            mode='lines+markers+text',
            text=[f"{v:.2f}%" if pd.notnull(v) else "0.00%" for v in df_raw['mora_pct']],
            textposition='top center',
            line=dict(color='#d62728', width=2.5)
        ))
        fig2.add_trace(go.Scatter(
            x=df_raw['fecha_label'], 
            y=df_raw['cobertura_pct'], 
            name='Cobertura Previsión (%)', 
            mode='lines+markers+text',
            text=[f"{v:.2f}%" if pd.notnull(v) else "0.00%" for v in df_raw['cobertura_pct']],
            textposition='bottom center',
            line=dict(color='#2ca02c', width=2.5)
        ))
        
        fig2.update_layout(
            height=300,
            title="Evolución de Mora (%) y Cobertura (%)",
            hovermode="x unified",
            **plotly_layout_theme
        )
        st.plotly_chart(fig2, use_container_width=True)

    # --- 4. TABLA PIVOTADA HISTÓRICA CON TERMINOLOGÍA ASFI ---
    st.markdown("---")
    st.subheader(f"📋 Calificación de Cartera y Contingente ({nombre_moneda})")

    filas_estructura = [
        {"concepto": "CATEGORÍA A", "col_key": "categoria_a", "es_pct": False, "tipo": "normal"},
        {"concepto": "PREVISIÓN conforme a (2)", "col_key": "prevision_a", "es_pct": False, "tipo": "normal"},
        {"concepto": "CATEGORÍA B", "col_key": "categoria_b", "es_pct": False, "tipo": "normal"},
        {"concepto": "PREVISIÓN conforme a (3)", "col_key": "prevision_b", "es_pct": False, "tipo": "normal"},
        {"concepto": "CATEGORÍA C", "col_key": "categoria_c", "es_pct": False, "tipo": "normal"},
        {"concepto": "PREVISIÓN 20%", "col_key": "prevision_c", "es_pct": False, "tipo": "normal"},
        {"concepto": "CATEGORÍA D", "col_key": "categoria_d", "es_pct": False, "tipo": "normal"},
        {"concepto": "PREVISIÓN 50%", "col_key": "prevision_d", "es_pct": False, "tipo": "normal"},
        {"concepto": "CATEGORÍA E", "col_key": "categoria_e", "es_pct": False, "tipo": "normal"},
        {"concepto": "PREVISIÓN 80%", "col_key": "prevision_e", "es_pct": False, "tipo": "normal"},
        {"concepto": "CATEGORÍA F", "col_key": "categoria_f", "es_pct": False, "tipo": "normal"},
        {"concepto": "PREVISIÓN 100%", "col_key": "prevision_f", "es_pct": False, "tipo": "normal"},
        {"concepto": "TOTAL CARTERA Y CONTINGENTE (4)", "col_key": "total_cartera", "es_pct": False, "tipo": "total_resalta"},
        {"concepto": "TOTAL PREVISIÓN ESPECÍFICA", "col_key": "total_prevision", "es_pct": False, "tipo": "normal_bold"},
        {"concepto": "TOT.PREV.ESPEC. / TOT.CART. Y CONTING.", "col_key": "porcentaje_general", "es_pct": True, "tipo": "normal"}
    ]

    cols_fechas_desc = sorted(df_raw['fecha_label'].unique(), key=lambda x: pd.to_datetime(x, format='%b %Y'), reverse=True)

    rows_list = []
    for item in filas_estructura:
        c_nom = item['concepto']
        k = item['col_key']
        es_pct = item['es_pct']
        tipo = item['tipo']

        if tipo == "total_resalta":
            clase_fila = "comp-total-header"
            clase_val = "comp-total-val"
        elif tipo == "normal_bold":
            clase_fila = "comp-bold-ind"
            clase_val = "comp-bold-val"
        else:
            clase_fila = "comp-col-ind"
            clase_val = "comp-col-val"

        val_cells_list = []
        for f_col in cols_fechas_desc:
            row_f = df_raw[df_raw['fecha_label'] == f_col]
            if not row_f.empty:
                val = row_f[k].values[0]
                val_num = float(val) if pd.notnull(val) else 0.0
            else:
                val_num = 0.0

            if es_pct:
                val_fmt = f"{val_num:,.2f}%"
            else:
                val_fmt = f"{val_num:,.2f}"

            val_cells_list.append(f'<td class="{clase_val}">{val_fmt}</td>')

        val_cells = "".join(val_cells_list)
        rows_list.append(f'<tr><td class="{clase_fila}">{c_nom}</td>{val_cells}</tr>')

    rows_html = "".join(rows_list)
    th_fechas = "".join([f'<th style="text-align:right; min-width:110px;">{f_col}</th>' for f_col in cols_fechas_desc])

    st.markdown("""
    <style>
        .comp-container {
            max-height: 520px;
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
        .comp-bold-ind {
            width: 35%;
            padding: 6px 10px;
            font-size: 11px;
            font-weight: bold;
            color: var(--text-color);
            background-color: var(--background-color);
            border-bottom: 1px solid var(--border-color);
            border-right: 1px solid var(--border-color);
            white-space: nowrap;
        }
        .comp-bold-val {
            text-align: right;
            padding: 6px 10px;
            font-size: 11px;
            font-weight: bold;
            font-family: Consolas, monospace;
            color: var(--text-color);
            background-color: var(--background-color);
            border-bottom: 1px solid var(--border-color);
            border-left: 1px solid var(--border-color);
            white-space: nowrap;
        }
        .comp-total-header {
            background-color: var(--secondary-background-color);
            color: var(--text-color);
            font-weight: bold;
            font-size: 11px;
            padding: 7px 12px;
            border-top: 1.5px solid var(--border-color);
            border-bottom: 1.5px solid var(--border-color);
            border-left: 4px solid #2563eb;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            white-space: nowrap;
        }
        .comp-total-val {
            text-align: right;
            padding: 7px 10px;
            font-size: 11px;
            font-weight: bold;
            font-family: Consolas, monospace;
            background-color: var(--secondary-background-color);
            color: var(--text-color);
            border-top: 1.5px solid var(--border-color);
            border-bottom: 1.5px solid var(--border-color);
            border-left: 1px solid var(--border-color);
            white-space: nowrap;
        }
        .comp-table tbody tr:hover td {
            background-color: var(--secondary-background-color) !important;
            opacity: 0.95;
        }
    </style>
    """, unsafe_allow_html=True)

    html_table = f'<div class="comp-container"><table class="comp-table"><thead><tr><th style="width:35%; text-align:left;">CATEGORÍA DE RIESGO</th>{th_fechas}</tr></thead><tbody>{rows_html}</tbody></table></div>'
    st.markdown(html_table, unsafe_allow_html=True)

    # Consulta y despliegue dinámico de notas desde la Base de Datos
    query_notas = """
        SELECT numero_nota, texto_nota 
        FROM calificacion_notas 
        WHERE id_grupo = :id_grupo AND fecha_corte = :fecha 
        ORDER BY numero_nota ASC
    """
    df_notas = consultar_db(query_notas, {"id_grupo": id_g, "fecha": fecha_sel_input})

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

    # --- 5. EXPORTACIÓN A EXCEL ---
    dict_export = {"CATEGORÍA DE RIESGO": [f['concepto'] for f in filas_estructura]}
    for f_col in cols_fechas_desc:
        row_f = df_raw[df_raw['fecha_label'] == f_col]
        vals = []
        for item in filas_estructura:
            k = item['col_key']
            if not row_f.empty:
                val = row_f[k].values[0]
                vals.append(float(val) if pd.notnull(val) else 0.0)
            else:
                vals.append(0.0)
        dict_export[f_col] = vals

    df_export = pd.DataFrame(dict_export)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as wr:
        df_export.to_excel(wr, index=False, sheet_name='Historico_Calif_Cartera')
        if not df_notas.empty:
            df_notas.to_excel(wr, index=False, sheet_name='Notas_ASFI')
    
    _, col_boton = st.columns([3, 1])
    with col_boton:
        st.download_button(
            "📥 Exportar Excel",
            buf.getvalue(),
            f"comportamiento_calificacion_{sigla_sel}.xlsx",
            use_container_width=True
        )

if __name__ == "__main__":
    mostrar_comportamiento_calificacion()