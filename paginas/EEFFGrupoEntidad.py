# ==============================================================================
# FUNCIONALIDAD DEL ARCHIVO (EEFFGrupoEntidad.py):
# Este script genera la información consolidada y desagregada de los Estados
# Financieros por Grupo de Entidades Financieras (Bancos Múltiples, PYME, IFD, etc.).
# Muestra una tabla comparativa en formato matricial (Cuentas vs. Entidades)
# replicando la estructura de publicación de la ASFI y agregando gráficos comparativos.
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
    st.session_state.input_busqueda_grupo = ""

def generar_excel_grupo(df, moneda_nombre):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='EEFF_Grupo')
    return output.getvalue()

@st.cache_data(ttl=600)
def consultar_eeff_grupo(query, params=None):
    engine = obtener_engine()
    try:
        return pd.read_sql_query(query, engine, params=params)
    except Exception as e:
        st.error(f"Error al consultar la base de datos: {e}")
        return pd.DataFrame()

def mostrar_eeff_grupo():
    st.title("🏛️ Estados Financieros por Grupo de Entidades")

    dict_indicadores = obtener_indicadores_bcb()

    if "slider_nivel_grupo" not in st.session_state: 
        st.session_state.slider_nivel_grupo = 1
    if "input_busqueda_grupo" not in st.session_state: 
        st.session_state.input_busqueda_grupo = ""
    if "moneda_seleccionada_grupo" not in st.session_state: 
        st.session_state.moneda_seleccionada_grupo = list(dict_indicadores.keys())[0]

    # --- 1. CONFIGURACIÓN DE CONSULTA Y FILTROS EN ENCABEZADO ---
    with st.container(border=True):
        f1, f2, f3, f4 = st.columns([0.6, 0.9, 1.2, 1.3])

        # AÑO
        df_years = consultar_eeff_grupo("SELECT DISTINCT EXTRACT(YEAR FROM fecha_corte)::int as anio FROM estados_financieros ORDER BY anio DESC")
        if df_years.empty:
            st.warning("No hay datos disponibles en la base de datos.")
            return
        anio_sel = f1.selectbox("Año", df_years['anio'].tolist(), key="eeff_grupo_anio")

        # CORTE
        df_fechas = consultar_eeff_grupo("""
            SELECT DISTINCT fecha_corte 
            FROM estados_financieros 
            WHERE EXTRACT(YEAR FROM fecha_corte) = %s 
            ORDER BY fecha_corte DESC
        """, (anio_sel,))
        fecha_sel = f2.selectbox("Corte", df_fechas['fecha_corte'].astype(str).tolist(), key="eeff_grupo_corte")

        # MONEDA / UNIDAD DE MEDIDA
        if st.session_state.moneda_seleccionada_grupo not in dict_indicadores:
            st.session_state.moneda_seleccionada_grupo = list(dict_indicadores.keys())[0]

        st.session_state.moneda_seleccionada_grupo = f3.selectbox(
            "💰 Unidad de Medida", 
            list(dict_indicadores.keys()), 
            index=list(dict_indicadores.keys()).index(st.session_state.moneda_seleccionada_grupo),
            key="eeff_grupo_moneda"
        )

        # GRUPO FINANCIERO
        df_grupos = consultar_eeff_grupo("SELECT id_grupo, nombre_grupo FROM grupos_asfi ORDER BY id_grupo ASC")
        grupo_sel = f4.selectbox("📂 Grupo Financiero", df_grupos['nombre_grupo'].tolist(), key="eeff_grupo_grupo")
        id_g = int(df_grupos[df_grupos['nombre_grupo'] == grupo_sel]['id_grupo'].values[0])

        if len(dict_indicadores) == 1:
            st.caption("⚠️ No existe conectividad con BCB (Muestra únicamente datos en Bs.)")

    # --- 2. CARGA Y PIVOTEO DE DATOS ---
    query = """
        SELECT 
            p.codigo_cuenta as cod, 
            p.descripcion_cuenta as desc, 
            f.entidad,
            f.monto as monto_bs 
        FROM estados_financieros f 
            JOIN plan_cuentas p ON f.codigo_cuenta = p.codigo_cuenta 
            JOIN entidades e ON f.entidad = e.nombre_entidad
        WHERE e.id_grupo = %s AND f.fecha_corte = %s 
        ORDER BY f.id_registro ASC
    """
    df_raw = consultar_eeff_grupo(query, (id_g, fecha_sel))

    if df_raw.empty:
        st.info("No se encontraron registros para la combinación de filtros seleccionada.")
        return

    factor_conv = dict_indicadores[st.session_state.moneda_seleccionada_grupo]
    nombre_moneda = st.session_state.moneda_seleccionada_grupo.split(' ')[0]
    df_raw['monto'] = df_raw['monto_bs'] / factor_conv
    df_raw['nivel'] = df_raw['cod'].apply(asignar_level)

    # Ordenamiento de entidades
    entidades_unicas = list(df_raw['entidad'].unique())
    entidades_ts = [e for e in entidades_unicas if e.startswith('TS')]
    entidades_individuales = sorted([e for e in entidades_unicas if not e.startswith('TS')])
    columnas_entidades = entidades_individuales + entidades_ts

    df_cuentas = df_raw[['cod', 'desc', 'nivel']].drop_duplicates(subset=['cod']).copy()
    pivot_df = df_raw.pivot_table(index='cod', columns='entidad', values='monto', aggfunc='sum').fillna(0)
    
    columnas_existentes = [col for col in columnas_entidades if col in pivot_df.columns]
    pivot_df = pivot_df[columnas_existentes]

    df_matriz = df_cuentas.merge(pivot_df, on='cod', how='left').fillna(0)

    # --- 3. BLOQUE DE GRÁFICOS PARALELOS ---
    def obtener_valores_cuenta(codigo):
        filtro = df_raw[df_raw['cod'].astype(str).str.match(rf'^{codigo}(\.00)?$', na=False)]
        if filtro.empty:
            return pd.Series(0.0, index=entidades_individuales)
        return filtro.groupby('entidad')['monto'].sum().reindex(entidades_individuales, fill_value=0)

    activos_ent = obtener_valores_cuenta('100')
    cartera_ent = obtener_valores_cuenta('130')
    pasivos_ent = obtener_valores_cuenta('200')
    patrimonio_ent = obtener_valores_cuenta('300')
    obl_pub_ent = obtener_valores_cuenta('210')

    plotly_layout_theme = dict(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(showgrid=False, tickangle=-45),
        yaxis=dict(gridcolor='rgba(128,128,128,0.2)')
    )

    cg1, cg2 = st.columns(2)

    with cg1:
        fig1 = go.Figure()
        fig1.add_trace(go.Bar(
            x=entidades_individuales, 
            y=cartera_ent.values, 
            name='Cartera (130)', 
            marker_color='#1f77b4',
            hovertemplate='%{x} - Cartera: %{y:,.2f}<extra></extra>'
        ))
        fig1.add_trace(go.Bar(
            x=entidades_individuales, 
            y=(activos_ent - cartera_ent).clip(lower=0).values, 
            name='Otros Activos', 
            marker_color='#aec7e8',
            hovertemplate='%{x} - Otros Act.: %{y:,.2f}<extra></extra>'
        ))
        fig1.update_layout(
            barmode='stack', 
            height=280, 
            margin=dict(t=40, b=10, l=10, r=10), 
            title=f"Composición del Activo por Entidad ({nombre_moneda})",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            **plotly_layout_theme
        )
        st.plotly_chart(fig1, use_container_width=True)

    with cg2:
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(
            x=entidades_individuales, 
            y=obl_pub_ent.values, 
            name='Oblig. Público (210)', 
            marker_color='#d62728',
            hovertemplate='%{x} - Oblig. Púb.: %{y:,.2f}<extra></extra>'
        ))
        fig2.add_trace(go.Bar(
            x=entidades_individuales, 
            y=(pasivos_ent - obl_pub_ent).clip(lower=0).values, 
            name='Otros Pasivos', 
            marker_color='#ff9896',
            hovertemplate='%{x} - Otros Pas.: %{y:,.2f}<extra></extra>'
        ))
        fig2.add_trace(go.Bar(
            x=entidades_individuales, 
            y=patrimonio_ent.values, 
            name='Patrimonio (300)', 
            marker_color='#ff7f0e',
            hovertemplate='%{x} - Patrimonio: %{y:,.2f}<extra></extra>'
        ))
        fig2.update_layout(
            barmode='stack', 
            height=280, 
            margin=dict(t=40, b=10, l=10, r=10), 
            title=f"Pasivo + Patrimonio por Entidad ({nombre_moneda})",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            **plotly_layout_theme
        )
        st.plotly_chart(fig2, use_container_width=True)

    # --- 4. CONTROLES DE FILTRADO Y NIVEL ---
    st.markdown("---")
    c_busq, c_slid = st.columns([1.5, 1.0])
    with c_busq:
        busqueda_actual = st.text_input("🔎 Buscar cuenta:", key="input_busqueda_grupo", placeholder="Código o descripción...")
        busqueda_clean = busqueda_actual.strip().lower()

    if busqueda_clean:
        mask = df_matriz['desc'].str.lower().str.contains(busqueda_clean, na=False) | df_matriz['cod'].astype(str).str.contains(busqueda_clean, na=False)
        matches = df_matriz[mask]
        if not matches.empty:
            nuevo_nivel = int(matches['nivel'].max())
            if nuevo_nivel > st.session_state.slider_nivel_grupo:
                st.session_state.slider_nivel_grupo = nuevo_nivel

    with c_slid:
        st.select_slider("📊 Nivel Detalle", options=[0, 1, 2, 3, 4], key="slider_nivel_grupo", on_change=limpiar_busqueda)

    # --- 5. VISUALIZACIÓN MATRICIAL NATIVA (CON SCROLLBAR Y SEPARADOR DE MILES) ---
    df_ver = df_matriz[df_matriz['nivel'] <= st.session_state.slider_nivel_grupo].copy()

    if busqueda_clean:
        df_ver = df_ver[
            df_ver['desc'].str.lower().str.contains(busqueda_clean, na=False) | 
            df_ver['cod'].astype(str).str.contains(busqueda_clean, na=False)
        ]

    # Indentación según nivel de cuenta
    df_ver['desc_indent'] = df_ver.apply(lambda r: ("⠀" * (r['nivel'] * 2)) + str(r['desc']), axis=1)

    cols_display = ['cod', 'desc_indent'] + columnas_existentes
    df_tabla = df_ver[cols_display].rename(columns={
        'cod': 'Código',
        'desc_indent': 'Descripción de la Cuenta'
    })

    # Construcción dinámica de configuración de columnas para forzar el scroll horizontal y separadores de miles
    cfg_columnas = {
        "Código": st.column_config.TextColumn("Código", width=110),
        "Descripción de la Cuenta": st.column_config.TextColumn("Descripción de la Cuenta", width=420)
    }

    for col in columnas_existentes:
        cfg_columnas[col] = st.column_config.NumberColumn(
            col,
            format="%,.2f",
            width=150
        )

    st.dataframe(
        df_tabla,
        use_container_width=True,
        hide_index=True,
        height=480,
        column_config=cfg_columnas
    )

    # --- 6. EXPORTACIÓN A EXCEL ---
    cols_export = ['cod', 'desc'] + columnas_existentes
    df_export = df_ver[cols_export].rename(columns={'cod': 'Cuenta', 'desc': 'N O M B R E'})
    
    excel_data = generar_excel_grupo(df_export, st.session_state.moneda_seleccionada_grupo)
    _, col_boton = st.columns([3, 1])
    with col_boton:
        nombre_file = f"EEFF_Grupo_{grupo_sel.replace(' ', '_')}_{fecha_sel}"
        st.download_button("📥 Descargar Excel", excel_data, f"{nombre_file}.xlsx", use_container_width=True)

if __name__ == "__main__":
    mostrar_eeff_grupo()