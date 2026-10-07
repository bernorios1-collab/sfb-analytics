# ==============================================================================
# FUNCIONALIDAD DEL ARCHIVO (comportamiento_cuentas.py):
# Este script implementa una interfaz interactiva en Streamlit para analizar la 
# evolución temporal y las variaciones periódicas de las cuentas de los estados 
# financieros. Permite visualizar tendencias dinámicas mediante gráficos de 
# áreas apiladas, explorar balances estructurados por niveles jerárquicos y 
# abrir diálogos de análisis detallado por cuenta individual con tablas de 
# variación absoluta y relativa, permitiendo además la exportación de los datos 
# estructurados a un formato Excel.
# ==============================================================================

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import io
from config_db import obtener_engine
from scrapers.indicadores_bcb import obtener_indicadores_bcb

# --- FUNCIONES TÉCNICAS ---
@st.cache_data(ttl=600)
def consultar_db(query, params=None):
    engine = obtener_engine()
    try:
        return pd.read_sql_query(query, engine, params=params)
    except Exception as e:
        st.error(f"Error técnico: {e}")
        return pd.DataFrame()

def asignar_level(codigo):
    codigo = str(codigo).strip().upper()
    if codigo.startswith('C'): return 0
    partes = codigo.split('.')
    base = partes[0]
    aux = partes[1] if len(partes) > 1 else "00"
    if aux not in ["0", "00", "000"]: return 4
    if len(base) >= 3 and base[1:] in ["00", "000"]: return 1
    if len(base) >= 3 and base[2] == "0": return 2
    return 3

def limpiar_busqueda():
    st.session_state.input_bus_comport = ""

@st.dialog("Detalle de Cuenta", width="large")
def mostrar_detalle_cuenta(df_raw, cod, moneda_nombre):
    datos_cta = df_raw[df_raw['cod'] == cod].copy().sort_values('fecha_dt')
    if datos_cta.empty:
        st.warning("No hay datos.")
        return
    st.subheader(f"Cuenta: {cod} - {datos_cta['desc_cta'].iloc[0]}")
    val_min, val_max = datos_cta['monto'].min(), datos_cta['monto'].max()
    margen = (val_max - val_min) * 0.1 if val_max != val_min else 1
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=datos_cta['fecha_label'], y=datos_cta['monto'], mode='lines+markers', fill='tozeroy', line=dict(color='#1f77b4')))
    fig.update_layout(height=350, margin=dict(t=20, b=20, l=20, r=20), xaxis=dict(type='category'), yaxis=dict(range=[val_min - margen, val_max + margen]))
    st.plotly_chart(fig, use_container_width=True)
    df_tab = datos_cta[['fecha_label', 'monto']].copy()
    df_tab['Var. Absoluta'] = df_tab['monto'].diff()
    df_tab['Var. Relativa (%)'] = df_tab['monto'].pct_change() * 100
    df_style = df_tab.copy()
    df_style['monto'] = df_style['monto'].map('{:,.2f}'.format)
    df_style['Var. Absoluta'] = df_style['Var. Absoluta'].apply(lambda x: f"{x:,.2f}" if pd.notnull(x) else "-")
    df_style['Var. Relativa (%)'] = df_style['Var. Relativa (%)'].apply(lambda x: f"{x:.2f}%" if pd.notnull(x) else "-")
    st.table(df_style.set_index('fecha_label'))

def mostrar_comportamiento():
    st.header("📈 Comportamiento de Cuentas")
    
    dict_indicadores = obtener_indicadores_bcb()

    if "input_bus_comport" not in st.session_state: st.session_state.input_bus_comport = ""

    # --- 1. CONFIGURACIÓN DE CONSULTA ---
    with st.container(border=True):
        c1, c2, c3, c4, c5 = st.columns([0.4, 0.6, 1.0, 0.8, 0.8])
        df_years = consultar_db("SELECT DISTINCT EXTRACT(YEAR FROM fecha_corte)::int as anio FROM estados_financieros ORDER BY anio DESC")
        anio_sel = c1.selectbox("Año", df_years['anio'].tolist())
        df_f = consultar_db("SELECT DISTINCT fecha_corte FROM estados_financieros WHERE EXTRACT(YEAR FROM fecha_corte) = %s ORDER BY fecha_corte DESC", (anio_sel,))
        fecha_sel_input = c2.selectbox("Corte", df_f['fecha_corte'].astype(str).tolist())
        
        moneda_sel = c3.selectbox("💰 Moneda", list(dict_indicadores.keys()))
        frecuencia = c4.selectbox("🔄 Frecuencia", ["Mensual", "Trimestral", "Semestral", "Anual"])
        periodos = c5.number_input("🔢 Periodos", min_value=1, max_value=24, value=6)

        f1, f2 = st.columns([1.3, 1.7])
        df_grupos = consultar_db("SELECT id_grupo, nombre_grupo FROM grupos_asfi ORDER BY id_grupo ASC")
        grupo_sel = f1.selectbox("📂 Grupo", options=df_grupos['nombre_grupo'].tolist())
        id_g = int(df_grupos[df_grupos['nombre_grupo'] == grupo_sel]['id_grupo'].values[0])
        
        # Ordenamos la consulta SQL para que la sigla TS*** (Total Sistema) aparezca en primer lugar
        df_ent = consultar_db("""
            SELECT nombre_entidad as sigla, nombre_completo 
            FROM entidades 
            WHERE id_grupo = %s 
            ORDER BY 
                CASE WHEN nombre_entidad LIKE 'TS%%' THEN 0 ELSE 1 END,
                nombre_completo ASC
        """, (id_g,))
        
        opciones_ent = {}
        for _, r in df_ent.iterrows():
            nombre = r['nombre_completo'] if pd.notna(r['nombre_completo']) and r['nombre_completo'] != "" else r['sigla']
            opciones_ent[f"{nombre} ({r['sigla']})"] = r['sigla']
            
        sigla_sel = opciones_ent[f2.selectbox("🏛️ Entidad Financiera", options=list(opciones_ent.keys()))]
        
        if len(dict_indicadores) == 1:
            st.caption("⚠️ No existe conectividad con BCB (Muestra únicamente datos en Bs.)")

    # --- 2. LÓGICA DE DATOS ---
    map_m = {"Mensual": 1, "Trimestral": 3, "Semestral": 6, "Anual": 12}
    salto = map_m[frecuencia]
    df_f_global = consultar_db("SELECT DISTINCT fecha_corte FROM estados_financieros ORDER BY fecha_corte DESC")
    lista_f = df_f_global['fecha_corte'].astype(str).tolist()
    try:
        idx = lista_f.index(fecha_sel_input)
        fechas_req = lista_f[idx : idx + (periodos * salto) : salto]
    except:
        fechas_req = [fecha_sel_input]

    # Consulta directa y uniforme para cualquier entidad o registro de Total Sistema
    query = """
        SELECT 
            f.fecha_corte, 
            p.codigo_cuenta as cod, 
            p.descripcion_cuenta as desc_cta, 
            f.monto as monto_bs,
            f.id_registro as orden_db
        FROM estados_financieros f 
        JOIN plan_cuentas p ON f.codigo_cuenta = p.codigo_cuenta 
        WHERE f.entidad = %s AND f.fecha_corte IN %s 
        ORDER BY f.id_registro ASC, 1 ASC
    """
    df_raw = consultar_db(query, (sigla_sel, tuple(fechas_req)))

    if df_raw.empty: return
    df_raw['fecha_dt'] = pd.to_datetime(df_raw['fecha_corte'])
    df_raw['fecha_label'] = df_raw['fecha_dt'].dt.strftime('%b %Y')

    # --- 3. GRÁFICOS RESUMEN ---
    st.markdown("### Resumen Ejecutivo")
    def get_s(c): 
        res = df_raw[df_raw['cod'].astype(str).str.match(rf'^{c}(\.00)?$', na=False)].sort_values('fecha_dt')
        return res.set_index('fecha_label')['monto_bs']
    act, cart, pas, obl, pat = get_s('100'), get_s('130'), get_s('200'), get_s('210'), get_s('300')
    labels = df_raw.sort_values('fecha_dt')['fecha_label'].unique()
    g1, g2 = st.columns(2)
    with g1:
        fig1 = go.Figure()
        fig1.add_trace(go.Scatter(x=labels, y=cart.reindex(labels).values, name='Cartera', stackgroup='one', fill='tozeroy', line=dict(color='#1f77b4')))
        fig1.add_trace(go.Scatter(x=labels, y=(act.reindex(labels)-cart.reindex(labels)).values, name='Otros Activos', stackgroup='one', fill='tonexty', line=dict(color='#aec7e8')))
        fig1.update_layout(height=280, margin=dict(t=30, b=10, l=10, r=10), xaxis=dict(type='category'), hovermode="x unified")
        st.plotly_chart(fig1, use_container_width=True)
    with g2:
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=labels, y=pat.reindex(labels).values, name='Patrimonio', stackgroup='two', fill='tozeroy', line=dict(color='#ff7f0e')))
        fig2.add_trace(go.Scatter(x=labels, y=obl.reindex(labels).values, name='Oblig. Público', stackgroup='two', fill='tonexty', line=dict(color='#d62728')))
        fig2.add_trace(go.Scatter(x=labels, y=(pas.reindex(labels)-obl.reindex(labels)).values, name='Otros Pasivos', stackgroup='two', fill='tonexty', line=dict(color='#ff9896')))
        fig2.update_layout(height=280, margin=dict(t=30, b=10, l=10, r=10), xaxis=dict(type='category'), hovermode="x unified")
        st.plotly_chart(fig2, use_container_width=True)

    # --- 4. TABLA INTERACTIVA ---
    st.markdown("---")
    c_busq, c_slid = st.columns([1.5, 1.0])
    busqueda = c_busq.text_input("🔎 Buscar cuenta:", key="input_bus_comport")
    nivel = c_slid.select_slider("📊 Nivel", options=[0,1,2,3,4], value=1, on_change=limpiar_busqueda)

    factor = dict_indicadores[moneda_sel]
    df_raw['monto'] = df_raw['monto_bs'] / factor
    df_raw['nivel'] = df_raw['cod'].apply(asignar_level)
    if busqueda:
        df_display = df_raw[df_raw['desc_cta'].str.lower().str.contains(busqueda.lower()) | df_raw['cod'].str.contains(busqueda)].copy()
    else:
        df_display = df_raw[df_raw['nivel'] <= nivel].copy()

    df_display['desc_cta_indented'] = df_display.apply(lambda x: (" " * 4 * x['nivel']) + x['desc_cta'], axis=1)
    
    df_pivot = df_display.pivot_table(index=['cod', 'desc_cta_indented', 'nivel'], columns='fecha_label', values='monto', sort=False).reset_index()
    
    cols_f = sorted([c for c in df_pivot.columns if c not in ['cod', 'desc_cta_indented', 'nivel']], key=lambda x: pd.to_datetime(x, format='%b %Y'), reverse=True)
    df_pivot = df_pivot[['cod', 'desc_cta_indented', 'nivel'] + cols_f]

    def style_rows(row):
        is_bold = row['nivel'] <= 1 or str(row['cod']).strip() in ['510.00', '410.00']
        return ['font-weight: bold' if is_bold else '' for _ in row]

    df_styled = df_pivot.style.apply(style_rows, axis=1)

    config_actual = {
        "cod": st.column_config.TextColumn("Código"), 
        "desc_cta_indented": st.column_config.TextColumn("Descripción"),
        "nivel": None
    }
    for f in cols_f: 
        config_actual[f] = st.column_config.NumberColumn(f, format="%,.2f")
    
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
        mostrar_detalle_cuenta(df_raw, cod_clic, moneda_sel)

    _, col_btn = st.columns([3, 1])
    with col_btn:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer: df_pivot.to_excel(writer, index=False, sheet_name='Comportamiento')
        st.download_button("📥 Exportar Excel", output.getvalue(), f"comportamiento_{sigla_sel}.xlsx", use_container_width=True)

if __name__ == "__main__":
    mostrar_comportamiento()