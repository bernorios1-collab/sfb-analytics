# ==============================================================================
# MÓDULO: comportamiento_cuentas_moneda.py
# Análisis histórico y evolución temporal de los EEFF por Moneda (MN, ME, MNMV, UFV)
# ==============================================================================

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import io
from config_db import obtener_engine
from scrapers.indicadores_bcb import obtener_indicadores_bcb

# --- CONSULTAS A BASE DE DATOS ---
@st.cache_data(ttl=600)
def consultar_db(query, params=None):
    engine = obtener_engine()
    try:
        return pd.read_sql_query(query, engine, params=params)
    except Exception as e:
        st.error(f"Error técnico: {e}")
        return pd.DataFrame()

def asignar_level_moneda(nivel_db):
    try:
        return int(nivel_db)
    except:
        return 3

def limpiar_busqueda():
    st.session_state.input_bus_comport_moneda = ""

# --- DIÁLOGO DE DETALLE MULTIMONEDA ---
@st.dialog("Detalle de Composición Monetaria Histórica", width="large")
def mostrar_detalle_cuenta_moneda(df_raw, cod, moneda_conversion):
    datos_cta = df_raw[df_raw['cod'] == cod].copy().sort_values('fecha_dt')
    if datos_cta.empty:
        st.warning("No hay datos disponibles para la cuenta seleccionada.")
        return
    
    st.subheader(f"Cuenta: {cod} - {datos_cta['desc_cta'].iloc[0]}")
    
    # Gráfica de 4 líneas por tipo de moneda
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=datos_cta['fecha_label'], y=datos_cta['monto_total'], name='Total (Bs)', line=dict(color='#1f77b4', width=3)))
    fig.add_trace(go.Scatter(x=datos_cta['fecha_label'], y=datos_cta['monto_mn'], name='Moneda Nacional (MN)', line=dict(color='#2ca02c', dash='dash')))
    fig.add_trace(go.Scatter(x=datos_cta['fecha_label'], y=datos_cta['monto_me'], name='Moneda Extranjera (ME)', line=dict(color='#d62728', dash='dot')))
    fig.add_trace(go.Scatter(x=datos_cta['fecha_label'], y=datos_cta['monto_mnufv'], name='UFV', line=dict(color='#ff7f0e', dash='dashdot')))
    
    fig.update_layout(
        height=360, 
        margin=dict(t=20, b=20, l=20, r=20), 
        xaxis=dict(type='category'),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # Tabla histórica desagregada por moneda
    df_tab = datos_cta[['fecha_label', 'monto_total', 'monto_mn', 'monto_me', 'monto_mnmv', 'monto_mnufv']].copy()
    
    # Calcular % de Dolarización (ME / Total)
    df_tab['% ME (Dolarización)'] = (df_tab['monto_me'] / df_tab['monto_total'].replace(0, pd.NA)) * 100
    
    df_style = df_tab.copy()
    for col in ['monto_total', 'monto_mn', 'monto_me', 'monto_mnmv', 'monto_mnufv']:
        df_style[col] = df_style[col].map('{:,.2f}'.format)
    df_style['% ME (Dolarización)'] = df_style['% ME (Dolarización)'].apply(lambda x: f"{x:.2f}%" if pd.notnull(x) else "0.00%")
    
    st.table(df_style.set_index('fecha_label'))

# --- VISTA PRINCIPAL ---
def mostrar_comportamiento_moneda():
    st.header("💱 Comportamiento Histórico por Moneda")
    
    dict_indicadores = obtener_indicadores_bcb()
    if "input_bus_comport_moneda" not in st.session_state: 
        st.session_state.input_bus_comport_moneda = ""

    # --- 1. CONFIGURACIÓN DE CONSULTA ---
    with st.container(border=True):
        c1, c2, c3, c4, c5 = st.columns([0.4, 0.6, 1.0, 0.8, 0.8])
        df_years = consultar_db("SELECT DISTINCT EXTRACT(YEAR FROM fecha_corte)::int as anio FROM estados_financieros_moneda ORDER BY anio DESC")
        
        if df_years.empty:
            st.warning("No hay datos cargados en Estados Financieros por Moneda.")
            return

        anio_sel = c1.selectbox("Año", df_years['anio'].tolist())
        df_f = consultar_db("SELECT DISTINCT fecha_corte FROM estados_financieros_moneda WHERE EXTRACT(YEAR FROM fecha_corte) = %s ORDER BY fecha_corte DESC", (anio_sel,))
        fecha_sel_input = c2.selectbox("Corte Base", df_f['fecha_corte'].astype(str).tolist())
        
        moneda_sel = c3.selectbox("💰 Expresado en", list(dict_indicadores.keys()))
        frecuencia = c4.selectbox("🔄 Frecuencia", ["Mensual", "Trimestral", "Semestral", "Anual"])
        periodos = c5.number_input("🔢 Periodos", min_value=1, max_value=24, value=6)

        f1, f2, f3 = st.columns([1.2, 1.2, 1.2])
        df_grupos = consultar_db("SELECT id_grupo, nombre_grupo FROM grupos_asfi ORDER BY id_grupo ASC")
        grupo_sel = f1.selectbox("📂 Grupo ASFI", options=df_grupos['nombre_grupo'].tolist())
        id_g = int(df_grupos[df_grupos['nombre_grupo'] == grupo_sel]['id_grupo'].values[0])
        
        # Tipo de moneda a analizar en la tabla principal
        tipo_monto_sel = f2.selectbox(
            "📊 Denominación a Analizar", 
            ["monto_total", "monto_mn", "monto_me", "monto_mnmv", "monto_mnufv"],
            format_func=lambda x: {
                "monto_total": "Monto Total Consolidado",
                "monto_mn": "Moneda Nacional (MN)",
                "monto_me": "Moneda Extranjera (ME)",
                "monto_mnmv": "Muestras Mantenimiento Valor (MNMV)",
                "monto_mnufv": "Indexado UFV (MNUFV)"
            }[x]
        )
        
        vista_porcentaje = f3.checkbox("📐 Ver en Porcentaje de Dolarización (% ME / Total)", value=False)

    # --- 2. LÓGICA DE DATES & PERIODOS ---
    map_m = {"Mensual": 1, "Trimestral": 3, "Semestral": 6, "Anual": 12}
    salto = map_m[frecuencia]
    df_f_global = consultar_db("SELECT DISTINCT fecha_corte FROM estados_financieros_moneda ORDER BY fecha_corte DESC")
    lista_f = df_f_global['fecha_corte'].astype(str).tolist()
    
    try:
        idx = lista_f.index(fecha_sel_input)
        fechas_req = lista_f[idx : idx + (periodos * salto) : salto]
    except:
        fechas_req = [fecha_sel_input]

    # Consulta a estados_financieros_moneda
    query = """
        SELECT 
            f.fecha_corte, 
            p.codigo_cuenta as cod, 
            p.descripcion_cuenta as desc_cta, 
            p.nivel,
            f.monto_mn,
            f.monto_me,
            f.monto_mnmv,
            f.monto_mnufv,
            f.monto_total
        FROM estados_financieros_moneda f 
        JOIN plan_cuentas_moneda p ON f.codigo_cuenta = p.codigo_cuenta 
        WHERE f.id_grupo = %s AND f.fecha_corte IN %s 
        ORDER BY p.codigo_cuenta ASC, f.fecha_corte ASC
    """
    df_raw = consultar_db(query, (id_g, tuple(fechas_req)))

    if df_raw.empty:
        st.info("No se encontraron registros para los parámetros seleccionados.")
        return

    df_raw['fecha_dt'] = pd.to_datetime(df_raw['fecha_corte'])
    df_raw['fecha_label'] = df_raw['fecha_dt'].dt.strftime('%b %Y')

    # Convertir por tipo de cambio si corresponde
    factor = dict_indicadores[moneda_sel]
    for c_monto in ['monto_mn', 'monto_me', 'monto_mnmv', 'monto_mnufv', 'monto_total']:
        df_raw[c_monto] = df_raw[c_monto] / factor

    # --- 3. GRÁFICOS RESUMEN DE COMPOSICIÓN HISTÓRICA ---
    st.markdown("### 🏛️ Estructura y Composición de Dolarización")
    
    # Extraer Cartera (130.00) y Obligaciones con el Público (210.00)
    df_cart = df_raw[df_raw['cod'] == '130.00'].sort_values('fecha_dt')
    df_obl = df_raw[df_raw['cod'] == '210.00'].sort_values('fecha_dt')

    g1, g2 = st.columns(2)
    with g1:
        st.caption("Evolución por Moneda: Cartera (130.00)")
        fig1 = go.Figure()
        labels_time = df_cart['fecha_label'].tolist()
        fig1.add_trace(go.Bar(x=labels_time, y=df_cart['monto_mn'], name='MN', marker_color='#2ca02c'))
        fig1.add_trace(go.Bar(x=labels_time, y=df_cart['monto_me'], name='ME', marker_color='#d62728'))
        fig1.add_trace(go.Bar(x=labels_time, y=df_cart['monto_mnufv'], name='UFV', marker_color='#ff7f0e'))
        fig1.update_layout(barmode='stack', height=260, margin=dict(t=20, b=10, l=10, r=10), hovermode="x unified")
        st.plotly_chart(fig1, use_container_width=True)
        
    with g2:
        st.caption("Evolución por Moneda: Obligaciones Público (210.00)")
        fig2 = go.Figure()
        labels_time_obl = df_obl['fecha_label'].tolist()
        fig2.add_trace(go.Bar(x=labels_time_obl, y=df_obl['monto_mn'], name='MN', marker_color='#2ca02c'))
        fig2.add_trace(go.Bar(x=labels_time_obl, y=df_obl['monto_me'], name='ME', marker_color='#d62728'))
        fig2.add_trace(go.Bar(x=labels_time_obl, y=df_obl['monto_mnufv'], name='UFV', marker_color='#ff7f0e'))
        fig2.update_layout(barmode='stack', height=260, margin=dict(t=20, b=10, l=10, r=10), hovermode="x unified")
        st.plotly_chart(fig2, use_container_width=True)

    # --- 4. TABLA INTERACTIVA HISTÓRICA ---
    st.markdown("---")
    c_busq, c_slid = st.columns([1.5, 1.0])
    busqueda = c_busq.text_input("🔎 Buscar cuenta:", key="input_bus_comport_moneda")
    nivel_filtro = c_slid.select_slider("📊 Nivel Jerárquico", options=[1,2,3,4,5], value=2, on_change=limpiar_busqueda)

    # Determinar valor a pivotar
    if vista_porcentaje:
        df_raw['monto_mostrar'] = (df_raw['monto_me'] / df_raw['monto_total'].replace(0, pd.NA)) * 100
        formato_num = "%.2f%%"
    else:
        df_raw['monto_mostrar'] = df_raw[tipo_monto_sel]
        formato_num = "%,.2f"

    if busqueda:
        df_display = df_raw[df_raw['desc_cta'].str.lower().str.contains(busqueda.lower()) | df_raw['cod'].str.contains(busqueda)].copy()
    else:
        df_display = df_raw[df_raw['nivel'] <= nivel_filtro].copy()

    df_display['desc_cta_indented'] = df_display.apply(lambda x: (" " * 4 * int(x['nivel'])) + x['desc_cta'], axis=1)
    
    df_pivot = df_display.pivot_table(
        index=['cod', 'desc_cta_indented', 'nivel'], 
        columns='fecha_label', 
        values='monto_mostrar', 
        sort=False
    ).reset_index()
    
    cols_f = sorted([c for c in df_pivot.columns if c not in ['cod', 'desc_cta_indented', 'nivel']], key=lambda x: pd.to_datetime(x, format='%b %Y'), reverse=True)
    df_pivot = df_pivot[['cod', 'desc_cta_indented', 'nivel'] + cols_f]

    def style_rows(row):
        is_bold = row['nivel'] <= 2 or str(row['cod']).strip() in ['510.00', '410.00', 'CC0.00', 'CC0.07']
        return ['font-weight: bold' if is_bold else '' for _ in row]

    df_styled = df_pivot.style.apply(style_rows, axis=1)

    config_actual = {
        "cod": st.column_config.TextColumn("Código ASFI"), 
        "desc_cta_indented": st.column_config.TextColumn("Descripción de Cuenta"),
        "nivel": None
    }
    for f in cols_f: 
        config_actual[f] = st.column_config.NumberColumn(f, format=formato_num)
    
    event = st.dataframe(
        df_styled, 
        use_container_width=True, 
        hide_index=True, 
        on_select="rerun", 
        selection_mode="single-row", 
        column_config=config_actual
    )
    
    if len(event.selection.rows) > 0:
        row_idx = event.selection.rows[0]
        cod_clic = df_pivot.iloc[row_idx]['cod']
        mostrar_detalle_cuenta_moneda(df_raw, cod_clic, moneda_sel)

    _, col_btn = st.columns([3, 1])
    with col_btn:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer: 
            df_pivot.to_excel(writer, index=False, sheet_name='Comportamiento Moneda')
        st.download_button("📥 Exportar Excel", output.getvalue(), f"comportamiento_moneda_{grupo_sel}.xlsx", use_container_width=True)

if __name__ == "__main__":
    mostrar_comportamiento_moneda()