# ==============================================================================
# FUNCIONALIDAD DEL ARCHIVO (explorador_moneda.py):
# Este script implementa el "Explorador de Cuentas por Moneda" interactivo.
# Muestra la información financiera en el orden idéntico al generado por ASFI,
# incluyendo gráficos de composición por moneda (MN, ME, MNMV, UFV) y
# visualización jerárquica con exportación a Excel.
# ==============================================================================

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from config_db import obtener_engine
from scrapers.indicadores_bcb import obtener_indicadores_bcb
import io

def limpiar_busqueda():
    st.session_state.input_busqueda_mon = ""

def generar_excel_moneda(df, moneda_nombre):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='EEFF_Moneda')
    return output.getvalue()

@st.cache_data(ttl=600)
def consultar_explorador_moneda(query, params=None):
    engine = obtener_engine()
    try:
        return pd.read_sql_query(query, engine, params=params)
    except Exception as e:
        st.error(f"Error al consultar la BD: {e}")
        return pd.DataFrame()

def mostrar_explorador_moneda():
    st.title("💱 Explorador de Cuentas por Moneda")
    
    dict_indicadores = obtener_indicadores_bcb()

    if "slider_nivel_mon" not in st.session_state: 
        st.session_state.slider_nivel_mon = 1
    if "input_busqueda_mon" not in st.session_state: 
        st.session_state.input_busqueda_mon = ""
    if "moneda_seleccionada_mon" not in st.session_state: 
        st.session_state.moneda_seleccionada_mon = list(dict_indicadores.keys())[0]

    # --- 1. CONFIGURACIÓN DE CONSULTA ---
    with st.container(border=True):
        t1, t2, t3 = st.columns([0.5, 0.8, 1.2])
        
        df_years = consultar_explorador_moneda("""
            SELECT DISTINCT EXTRACT(YEAR FROM fecha_corte)::int as anio 
            FROM estados_financieros_moneda 
            ORDER BY anio DESC
        """)
        if df_years.empty:
            st.warning("No hay datos disponibles en la tabla de EEFF por Moneda.")
            return
            
        anio_sel = t1.selectbox("Año", df_years['anio'].tolist(), key="sb_anio_mon")
        
        df_fechas = consultar_explorador_moneda("""
            SELECT DISTINCT fecha_corte 
            FROM estados_financieros_moneda 
            WHERE EXTRACT(YEAR FROM fecha_corte) = %s 
            ORDER BY fecha_corte DESC
        """, (int(anio_sel),))
        
        fecha_sel = t2.selectbox("Corte", df_fechas['fecha_corte'].astype(str).tolist(), key="sb_fecha_mon")
        
        if st.session_state.moneda_seleccionada_mon not in dict_indicadores:
            st.session_state.moneda_seleccionada_mon = list(dict_indicadores.keys())[0]

        st.session_state.moneda_seleccionada_mon = t3.selectbox(
            "💰 Unidad de Medida", 
            list(dict_indicadores.keys()), 
            index=list(dict_indicadores.keys()).index(st.session_state.moneda_seleccionada_mon),
            key="sb_mon_mon"
        )

        f1, _ = st.columns([1.5, 1.5])
        df_grupos = consultar_explorador_moneda("SELECT id_grupo, nombre_grupo FROM grupos_asfi ORDER BY id_grupo ASC")
        grupo_sel = f1.selectbox("📂 Grupo Financiero", df_grupos['nombre_grupo'].tolist(), key="sb_grupo_mon")
        id_g = int(df_grupos[df_grupos['nombre_grupo'] == grupo_sel]['id_grupo'].values[0])

        if len(dict_indicadores) == 1:
            st.caption("⚠️ No existe conectividad con BCB (Muestra únicamente datos en Bs.)")

    # --- 2. CARGA DE DATOS (ORDEN IDENTICO A LA ASFI MEDIANTE f.id_registro ASC) ---
    query = """
        SELECT 
            p.codigo_cuenta as cod, 
            p.descripcion_cuenta as desc, 
            p.nivel,
            f.monto_mn,
            f.monto_me,
            f.monto_mnmv,
            f.monto_mnufv,
            f.monto_total
        FROM estados_financieros_moneda f 
            JOIN plan_cuentas_moneda p ON f.codigo_cuenta = p.codigo_cuenta 
        WHERE f.id_grupo = %s AND f.fecha_corte = %s 
        ORDER BY f.id_registro ASC
    """
    df_raw = consultar_explorador_moneda(query, (id_g, str(fecha_sel)))

    if df_raw.empty:
        st.info("No se encontraron registros para el grupo y fecha seleccionados.")
        return

    factor_conv = dict_indicadores[st.session_state.moneda_seleccionada_mon]
    nombre_moneda = st.session_state.moneda_seleccionada_mon.split(' ')[0]

    cols_monto = ['monto_mn', 'monto_me', 'monto_mnmv', 'monto_mnufv', 'monto_total']
    for c in cols_monto:
        df_raw[c] = df_raw[c] / factor_conv

    # --- 3. BLOQUE DE GRÁFICOS (COMPOSICIÓN POR MONEDA) ---
    def get_rubro_moneda(nombre_rubro):
        match = df_raw[df_raw['desc'].str.upper().str.strip() == nombre_rubro.upper()]
        if not match.empty:
            r = match.iloc[0]
            return [r['monto_mn'], r['monto_me'], r['monto_mnmv'], r['monto_mnufv']]
        return [0.0, 0.0, 0.0, 0.0]

    act_v = get_rubro_moneda('ACTIVO')
    pas_v = get_rubro_moneda('PASIVO')
    pat_v = get_rubro_moneda('PATRIMONIO')

    text_config = dict(
        texttemplate='%{y:,.2f}', 
        textposition='inside', 
        insidetextanchor='middle',
        hovertemplate='%{fullData.name}: %{y:,.2f}<extra></extra>'
    )

    plotly_layout_theme = dict(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(showgrid=False),
        yaxis=dict(gridcolor='rgba(128,128,128,0.2)')
    )

    cg1, cg2 = st.columns(2)
    
    with cg1:
        fig1 = go.Figure(data=[
            go.Bar(name='Moneda Nacional (MN)', x=['Activo'], y=[act_v[0]], marker_color='#1f77b4', **text_config),
            go.Bar(name='Moneda Extranjera (ME)', x=['Activo'], y=[act_v[1]], marker_color='#aec7e8', **text_config),
            go.Bar(name='MNMV', x=['Activo'], y=[act_v[2]], marker_color='#2ca02c', **text_config),
            go.Bar(name='UFV', x=['Activo'], y=[act_v[3]], marker_color='#98df8a', **text_config)
        ])
        fig1.update_layout(
            barmode='stack', height=240, margin=dict(t=30, b=10), showlegend=True, 
            title=f"Estructura del Activo ({nombre_moneda})",
            **plotly_layout_theme
        )
        st.plotly_chart(fig1, use_container_width=True)

    with cg2:
        fig2 = go.Figure(data=[
            go.Bar(name='Moneda Nacional (MN)', x=['Pasivo + Pat.'], y=[pas_v[0] + pat_v[0]], marker_color='#d62728', **text_config),
            go.Bar(name='Moneda Extranjera (ME)', x=['Pasivo + Pat.'], y=[pas_v[1] + pat_v[1]], marker_color='#ff9896', **text_config),
            go.Bar(name='MNMV', x=['Pasivo + Pat.'], y=[pas_v[2] + pat_v[2]], marker_color='#ff7f0e', **text_config),
            go.Bar(name='UFV', x=['Pasivo + Pat.'], y=[pas_v[3] + pat_v[3]], marker_color='#ffbb78', **text_config)
        ])
        fig2.update_layout(
            barmode='stack', height=240, margin=dict(t=30, b=10), showlegend=True, 
            title=f"Pasivo + Patrimonio ({nombre_moneda})",
            **plotly_layout_theme
        )
        st.plotly_chart(fig2, use_container_width=True)

    # --- 4. CONTROLES DE TABLA ---
    st.markdown("---")
    c_busq, c_slid = st.columns([1.5, 1.0])
    with c_busq:
        busqueda_actual = st.text_input("🔎 Buscar cuenta en moneda:", key="input_busqueda_mon", placeholder="Código o descripción...")
        busqueda_clean = busqueda_actual.strip().lower()

    if busqueda_clean:
        mask = df_raw['desc'].str.lower().str.contains(busqueda_clean, na=False) | df_raw['cod'].str.contains(busqueda_clean, na=False)
        matches = df_raw[mask]
        if not matches.empty:
            nuevo_nivel = int(matches['nivel'].max())
            if nuevo_nivel > st.session_state.slider_nivel_mon:
                st.session_state.slider_nivel_mon = nuevo_nivel

    max_nivel_db = int(df_raw['nivel'].max())
    min_nivel_db = int(df_raw['nivel'].min())
    opciones_slider = list(range(min_nivel_db, max_nivel_db + 1)) if max_nivel_db >= min_nivel_db else [1]

    with c_slid:
        st.select_slider("📊 Nivel Detalle", options=opciones_slider, key="slider_nivel_mon", on_change=limpiar_busqueda)

    # --- 5. VISUALIZACIÓN EN TABLA CON SEPARADOR DE MILES ---
    df_ver = df_raw[df_raw['nivel'] <= st.session_state.slider_nivel_mon].copy()
    
    if busqueda_clean:
        df_ver = df_ver[
            df_ver['desc'].str.lower().str.contains(busqueda_clean, na=False) | 
            df_ver['cod'].str.contains(busqueda_clean, na=False)
        ]

    df_ver['desc_indent'] = [("⠀" * ((int(lvl) - min_nivel_db) * 2)) + str(d) for lvl, d in zip(df_ver['nivel'], df_ver['desc'])]

    col_mn = f'MN ({nombre_moneda})'
    col_me = f'ME ({nombre_moneda})'
    col_mnmv = f'MNMV ({nombre_moneda})'
    col_ufv = f'UFV ({nombre_moneda})'
    col_total = f'Total ({nombre_moneda})'

    df_tabla = df_ver[['cod', 'desc_indent', 'monto_mn', 'monto_me', 'monto_mnmv', 'monto_mnufv', 'monto_total']].rename(columns={
        'cod': 'Código',
        'desc_indent': 'Descripción de la Cuenta',
        'monto_mn': col_mn,
        'monto_me': col_me,
        'monto_mnmv': col_mnmv,
        'monto_mnufv': col_ufv,
        'monto_total': col_total
    })

    st.dataframe(
        df_tabla,
        use_container_width=True,
        hide_index=True,
        height=450,
        column_config={
            "Código": st.column_config.TextColumn("Código", width=110),
            "Descripción de la Cuenta": st.column_config.TextColumn("Descripción de la Cuenta", width=380),
            col_mn: st.column_config.NumberColumn(col_mn, format="%,.2f", width=150),
            col_me: st.column_config.NumberColumn(col_me, format="%,.2f", width=150),
            col_mnmv: st.column_config.NumberColumn(col_mnmv, format="%,.2f", width=130),
            col_ufv: st.column_config.NumberColumn(col_ufv, format="%,.2f", width=130),
            col_total: st.column_config.NumberColumn(col_total, format="%,.2f", width=160)
        }
    )

    # --- 6. BOTÓN DE EXPORTACIÓN ---
    excel_data = generar_excel_moneda(
        df_ver[['cod', 'desc', 'monto_mn', 'monto_me', 'monto_mnmv', 'monto_mnufv', 'monto_total']], 
        st.session_state.moneda_seleccionada_mon
    )
    _, col_boton = st.columns([3, 1])
    with col_boton:
        nombre_file = f"EEFF_Moneda_{grupo_sel}_{fecha_sel}"
        st.download_button("📥 Descargar Excel", excel_data, f"{nombre_file}.xlsx", use_container_width=True)

if __name__ == "__main__":
    mostrar_explorador_moneda()