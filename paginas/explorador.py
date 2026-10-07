# ==============================================================================
# FUNCIONALIDAD DEL ARCHIVO (explorador.py):
# Este script implementa un "Explorador de Cuentas" interactivo utilizando Streamlit.
# Permite visualizar, filtrar y analizar los estados financieros de entidades 
# bancarias o de un grupo consolidado para un año y fecha de corte específicos.
# ==============================================================================

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from config_db import obtener_engine
from scrapers.indicadores_bcb import obtener_indicadores_bcb
import io

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
    st.session_state.input_busqueda = ""

def generar_excel(df, moneda_nombre):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Datos')
    return output.getvalue()

@st.cache_data(ttl=600)
def consultar_explorador(query, params=None):
    engine = obtener_engine()
    try:
        return pd.read_sql_query(query, engine, params=params)
    except Exception as e:
        st.error(f"Error: {e}")
        return pd.DataFrame()

def mostrar_explorador():
    st.title("🔍 Explorador de Cuentas")
    
    dict_indicadores = obtener_indicadores_bcb()

    if "slider_nivel" not in st.session_state: 
        st.session_state.slider_nivel = 1
    if "input_busqueda" not in st.session_state: 
        st.session_state.input_busqueda = ""
    if "moneda_seleccionada" not in st.session_state: 
        st.session_state.moneda_seleccionada = list(dict_indicadores.keys())[0]

    # --- 1. CONFIGURACIÓN DE CONSULTA ---
    with st.container(border=True):
        t1, t2, t3 = st.columns([0.5, 0.8, 1.2])
        
        df_years = consultar_explorador("SELECT DISTINCT EXTRACT(YEAR FROM fecha_corte)::int as anio FROM estados_financieros ORDER BY anio DESC")
        if df_years.empty:
            st.warning("No hay datos disponibles en la base de datos.")
            return
            
        anio_sel = t1.selectbox("Año", df_years['anio'].tolist())
        
        df_fechas = consultar_explorador("""
            SELECT DISTINCT fecha_corte 
            FROM estados_financieros 
            WHERE EXTRACT(YEAR FROM fecha_corte) = %s 
            ORDER BY fecha_corte DESC
        """, (anio_sel,))
        
        fecha_sel = t2.selectbox("Corte", df_fechas['fecha_corte'].astype(str).tolist())
        
        if st.session_state.moneda_seleccionada not in dict_indicadores:
            st.session_state.moneda_seleccionada = list(dict_indicadores.keys())[0]

        st.session_state.moneda_seleccionada = t3.selectbox("💰 Unidad de Medida", list(dict_indicadores.keys()), index=list(dict_indicadores.keys()).index(st.session_state.moneda_seleccionada))

        f2, f3 = st.columns([1.3, 1.7])
        
        df_grupos = consultar_explorador("SELECT id_grupo, nombre_grupo FROM grupos_asfi ORDER BY id_grupo ASC")
        grupo_sel = f2.selectbox("📂 Grupo Financiero", df_grupos['nombre_grupo'].tolist())
        id_g = int(df_grupos[df_grupos['nombre_grupo'] == grupo_sel]['id_grupo'].values[0])

        df_ent = consultar_explorador("""
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
            
        entidad_display = f3.selectbox("🏛️ Entidad Financiera", options=list(opciones_ent.keys()))
        banco_sel = opciones_ent[entidad_display]
        
        if len(dict_indicadores) == 1:
            st.caption("⚠️ No existe conectividad con BCB (Muestra únicamente datos en Bs.)")

    # --- 2. CARGA DE DATOS ---
    query = """
        SELECT 
            p.codigo_cuenta as cod, 
            p.descripcion_cuenta as desc, 
            f.monto as monto_bs 
        FROM estados_financieros f 
            JOIN plan_cuentas p ON f.codigo_cuenta = p.codigo_cuenta 
        WHERE f.entidad = %s AND f.fecha_corte = %s 
        ORDER BY f.id_registro ASC
    """
    df_raw = consultar_explorador(query, (banco_sel, fecha_sel))

    if df_raw.empty:
        st.info("No se encontraron registros para la selección actual.")
        return

    factor_conv = dict_indicadores[st.session_state.moneda_seleccionada]
    nombre_moneda = st.session_state.moneda_seleccionada.split(' ')[0]
    df_raw['monto'] = df_raw['monto_bs'] / factor_conv
    df_raw['nivel'] = df_raw['cod'].apply(asignar_level)

    # --- 3. BLOQUE DE GRÁFICOS ---
    def get_v(c):
        filtro = df_raw[df_raw['cod'].astype(str).str.match(rf'^{c}(\.00)?$', na=False)]
        return filtro['monto'].sum() if not filtro.empty else 0

    activo, pasivo, patrimonio = get_v('100'), get_v('200'), get_v('300')
    cartera, obl_pub = get_v('130'), get_v('210')
    otros_act = max(0, activo - cartera)
    otros_pas = max(0, pasivo - obl_pub)

    text_config = dict(
        texttemplate='%{text:,.2f}', 
        textposition='inside', 
        insidetextanchor='middle', 
        textfont=dict(size=14),
        hovertemplate='%{label}: %{y:,.2f}<extra></extra>'
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
            go.Bar(name='Cartera', x=['Activo'], y=[cartera], text=[cartera], marker_color='#1f77b4', **text_config),
            go.Bar(name='Otros Act.', x=['Activo'], y=[otros_act], text=[otros_act], marker_color='#aec7e8', **text_config)
        ])
        fig1.update_layout(
            barmode='stack', height=240, margin=dict(t=30, b=10), showlegend=True, 
            title=f"Activo ({nombre_moneda})",
            **plotly_layout_theme
        )
        st.plotly_chart(fig1, use_container_width=True)

    with cg2:
        fig2 = go.Figure(data=[
            go.Bar(name='Oblig. Público', x=['Pas+Pat'], y=[obl_pub], text=[obl_pub], marker_color='#d62728', **text_config),
            go.Bar(name='Otros Pas.', x=['Pas+Pat'], y=[otros_pas], text=[otros_pas], marker_color='#ff9896', **text_config),
            go.Bar(name='Patrimonio', x=['Pas+Pat'], y=[patrimonio], text=[patrimonio], marker_color='#ff7f0e', textfont=dict(size=14, color='white'), **{k: v for k, v in text_config.items() if k != 'textfont'})
        ])
        fig2.update_layout(
            barmode='stack', height=240, margin=dict(t=30, b=10), showlegend=True, 
            title=f"Pasivo + Pat. ({nombre_moneda})",
            **plotly_layout_theme
        )
        st.plotly_chart(fig2, use_container_width=True)

    # --- 4. CONTROLES DE TABLA ---
    st.markdown("---")
    c_busq, c_slid = st.columns([1.5, 1.0])
    with c_busq:
        busqueda_actual = st.text_input("🔎 Buscar cuenta:", key="input_busqueda", placeholder="Código o nombre...")
        busqueda_clean = busqueda_actual.strip().lower()

    if busqueda_clean:
        mask = df_raw['desc'].str.lower().str.contains(busqueda_clean, na=False) | df_raw['cod'].str.contains(busqueda_clean, na=False)
        matches = df_raw[mask]
        if not matches.empty:
            nuevo_nivel = int(matches['nivel'].max())
            if nuevo_nivel > st.session_state.slider_nivel:
                st.session_state.slider_nivel = nuevo_nivel

    with c_slid:
        st.select_slider("📊 Nivel Detalle", options=[0, 1, 2, 3, 4], key="slider_nivel", on_change=limpiar_busqueda)

    # --- 5. VISUALIZACIÓN CON ST.DATAFRAME Y SEPARADOR DE MILES ---
    df_ver = df_raw[df_raw['nivel'] <= st.session_state.slider_nivel].copy()
    
    if busqueda_clean:
        df_ver = df_ver[
            df_ver['desc'].str.lower().str.contains(busqueda_clean, na=False) | 
            df_ver['cod'].str.contains(busqueda_clean, na=False)
        ]

    df_ver['desc_indent'] = df_ver.apply(lambda r: ("⠀" * (r['nivel'] * 2)) + str(r['desc']), axis=1)

    col_monto_nombre = f'Monto ({nombre_moneda})'

    df_tabla = df_ver[['cod', 'desc_indent', 'monto']].rename(columns={
        'cod': 'Código',
        'desc_indent': 'Descripción de la Cuenta',
        'monto': col_monto_nombre
    })

    st.dataframe(
        df_tabla,
        use_container_width=True,
        hide_index=True,
        height=450,
        column_config={
            "Código": st.column_config.TextColumn("Código", width=120),
            "Descripción de la Cuenta": st.column_config.TextColumn("Descripción de la Cuenta", width=500),
            col_monto_nombre: st.column_config.NumberColumn(
                col_monto_nombre, 
                format="%,.2f",  # %,.2f añade separador de miles y limita a 2 decimales
                width=200
            )
        }
    )

    # --- 6. BOTÓN DE EXPORTACIÓN ---
    excel_data = generar_excel(df_ver[['cod', 'desc', 'monto']], st.session_state.moneda_seleccionada)
    _, col_boton = st.columns([3, 1])
    with col_boton:
        nombre_file = f"EEFF_{banco_sel}"
        st.download_button(f"📥 Descargar Excel", excel_data, f"{nombre_file}.xlsx", use_container_width=True)

if __name__ == "__main__":
    mostrar_explorador()