import streamlit as st
import pandas as pd
import plotly.express as px
from config_db import obtener_engine
from sqlalchemy import text
from scrapers.indicadores_bcb import obtener_indicadores_bcb
import io

@st.cache_data(ttl=600)
def consultar_db(query, params=None):
    engine = obtener_engine()
    try:
        return pd.read_sql_query(
            text(query),
            engine,
            params=params
        )
    except Exception as e:
        st.error(f"Error al consultar la base de datos: {e}")
        return pd.DataFrame()

def generar_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Ranking_Cartera')
    return output.getvalue()

def mostrar_ranking_cartera():
    st.title("🏆 Ranking de Cartera Bruta")

    dict_indicadores = obtener_indicadores_bcb()

    if "moneda_seleccionada" not in st.session_state:
        st.session_state.moneda_seleccionada = list(dict_indicadores.keys())[0]

    # --- 1. ENCABEZADO Y FILTROS ---
    with st.container(border=True):
        t1, t2, t3, t4 = st.columns([0.6, 0.8, 1.0, 1.4])

        # 1.1 AÑO
        df_years = consultar_db("""
            SELECT DISTINCT EXTRACT(YEAR FROM fecha_corte)::int as anio 
            FROM estados_financieros 
            ORDER BY anio DESC
        """)
        if df_years.empty:
            st.warning("No hay datos disponibles en la base de datos.")
            return
        anio_sel = t1.selectbox("Año", df_years['anio'].tolist(), key="a_rcartera")

        # 1.2 FECHA CORTE
        df_fechas = consultar_db("""
            SELECT DISTINCT fecha_corte 
            FROM estados_financieros 
            WHERE EXTRACT(YEAR FROM fecha_corte) = :anio 
            ORDER BY fecha_corte DESC
        """, {"anio": anio_sel})
        
        if df_fechas.empty:
            st.warning("No se encontraron fechas de corte para el año seleccionado.")
            return

        fecha_sel = t2.selectbox("Corte", df_fechas['fecha_corte'].astype(str).tolist(), key="f_rcartera")

        # 1.3 MONEDA
        if st.session_state.moneda_seleccionada not in dict_indicadores:
            st.session_state.moneda_seleccionada = list(dict_indicadores.keys())[0]
        st.session_state.moneda_seleccionada = t3.selectbox(
            "💰 Unidad de Medida", 
            list(dict_indicadores.keys()), 
            index=list(dict_indicadores.keys()).index(st.session_state.moneda_seleccionada),
            key="m_rcartera"
        )

        # 1.4 GRUPO FINANCIERO
        df_grupos = consultar_db("SELECT id_grupo, nombre_grupo FROM grupos_asfi ORDER BY id_grupo ASC")

        opciones_consolidadas = [
            "TOTAL SISTEMA FINANCIERO BOLIVIANO",
            "TOTAL SISTEMA BANCARIO"
        ]
        opciones_grupo = opciones_consolidadas + df_grupos['nombre_grupo'].tolist()
        grupo_sel = t4.selectbox("📂 Ámbito / Grupo Financiero", opciones_grupo, key="g_rcartera")

    # --- 2. CONSULTA DE CARTERA Y AGRUPACIÓN ---
    filtro_grupo_sql = ""
    params = {"fecha": fecha_sel}

    if grupo_sel == "TOTAL SISTEMA FINANCIERO BOLIVIANO":
        filtro_grupo_sql = ""
    elif grupo_sel == "TOTAL SISTEMA BANCARIO":
        filtro_grupo_sql = """
            AND TRANSLATE(UPPER(g.nombre_grupo), 'ÁÉÍÓÚ', 'AEIOU') IN (
                'BANCOS MULTIPLES', 'BANCOS PYME', 'BANCOS DE DESARROLLO PRODUCTIVO'
            )
        """
    else:
        id_g = int(df_grupos[df_grupos['nombre_grupo'] == grupo_sel]['id_grupo'].values[0])
        filtro_grupo_sql = " AND g.id_grupo = :id_grupo "
        params["id_grupo"] = id_g

    # Limpieza de códigos usando expresiones regulares para máxima compatibilidad
    query_cartera = f"""
        SELECT 
            e.nombre_entidad as sigla,
            COALESCE(NULLIF(e.nombre_completo, ''), e.nombre_entidad) as nombre_completo,
            g.nombre_grupo,
            REGEXP_REPLACE(f.codigo_cuenta, '[^0-9]', '', 'g') as cod_limpio,
            f.monto as monto_bs
        FROM estados_financieros f
        JOIN entidades e ON f.entidad = e.nombre_entidad
        JOIN grupos_asfi g ON e.id_grupo = g.id_grupo
        WHERE f.fecha_corte = :fecha
          AND REGEXP_REPLACE(f.codigo_cuenta, '[^0-9]', '', 'g') IN ('13100', '13300', '13400', '13500', '13600', '13700')
          AND e.nombre_entidad NOT LIKE 'TS%%'
          {filtro_grupo_sql}
    """

    df_raw = consultar_db(query_cartera, params)

    if df_raw.empty:
        st.info("ℹ️ No se encontraron registros de cartera para la selección realizada.")
        return

    # Factor de conversión a la moneda elegida
    factor_conv = dict_indicadores[st.session_state.moneda_seleccionada]
    nombre_moneda = st.session_state.moneda_seleccionada.split(' ')[0]
    df_raw['monto'] = df_raw['monto_bs'] / factor_conv

    # Mapeo y estandarización de cuentas
    mapeo_codigos = {
        '13100': '131.00', '13300': '133.00', '13400': '134.00',
        '13500': '135.00', '13600': '136.00', '13700': '137.00'
    }
    df_raw['codigo_cuenta'] = df_raw['cod_limpio'].map(mapeo_codigos)

    # Pivotear cuentas a columnas
    df_pivot = df_raw.pivot_table(
        index=['sigla', 'nombre_completo', 'nombre_grupo'], 
        columns='codigo_cuenta', 
        values='monto', 
        aggfunc='sum',
        fill_value=0
    ).reset_index()

    # Garantizar presencia de todas las columnas necesarias
    for cod in ['131.00', '133.00', '134.00', '135.00', '136.00', '137.00']:
        if cod not in df_pivot.columns:
            df_pivot[cod] = 0.0

    # Cálculo de subtotales
    df_pivot['Vigente'] = df_pivot['131.00'] + df_pivot['135.00']
    df_pivot['Vencida'] = df_pivot['133.00'] + df_pivot['136.00']
    df_pivot['Ejecución'] = df_pivot['134.00'] + df_pivot['137.00']
    df_pivot['Reprogramada Total'] = df_pivot['135.00'] + df_pivot['136.00'] + df_pivot['137.00']
    df_pivot['Cartera Bruta'] = df_pivot['Vigente'] + df_pivot['Vencida'] + df_pivot['Ejecución']

    # Filtrar entidades con saldo 0
    df_pivot = df_pivot[df_pivot['Cartera Bruta'] > 0].reset_index(drop=True)

    if df_pivot.empty:
        st.info("ℹ️ Todas las entidades en esta selección tienen saldo 0 en Cartera Bruta.")
        return

    # Ordenamiento por Cartera Bruta descendente
    df_pivot = df_pivot.sort_values(by='Cartera Bruta', ascending=False).reset_index(drop=True)
    df_pivot['Posición'] = df_pivot.index + 1

    # Construcción segura de etiqueta de entidad para evitar errores de tipo
    df_pivot['entidad_etiqueta'] = [
        f"{int(pos):02d}. {sigla}" 
        for pos, sigla in zip(df_pivot['Posición'], df_pivot['sigla'])
    ]

    # --- 3. VISUALIZACIÓN GRÁFICA HORIZONTAL ---
    st.subheader(f"📊 Ranking por Cartera Bruta ({nombre_moneda})")

    fig = px.bar(
        df_pivot,
        y='entidad_etiqueta',
        x=['Vigente', 'Vencida', 'Ejecución'],
        orientation='h',
        title=f"Distribución de Cartera Bruta - {grupo_sel}",
        color_discrete_sequence=['#1f77b4', '#d62728', '#ff7f0e'],
        labels={'value': f'Monto ({nombre_moneda})', 'entidad_etiqueta': 'Entidad (Ranking)', 'variable': 'Estado'},
        custom_data=['Posición', 'nombre_completo', 'sigla', 'nombre_grupo', 'Cartera Bruta', 'Reprogramada Total']
    )

    fig.update_traces(
        hovertemplate=(
            "<b>Puesto #%{customdata[0]}: %{customdata[1]}</b> (%{customdata[2]})<br>" +
            "Grupo: %{customdata[3]}<br>" +
            "Estado: %{fullData.name}<br>" +
            "Monto Estado: %{x:,.2f}<br>" +
            "<b>Cartera Bruta Total: %{customdata[4]:,.2f}</b><br>" +
            "Reprogramada Total: %{customdata[5]:,.2f}" +
            "<extra></extra>"
        )
    )

    altura_grafico = max(450, len(df_pivot) * 32)

    fig.update_layout(
        barmode='stack',
        height=altura_grafico,
        margin=dict(l=10, r=20, t=50, b=50),
        yaxis={
            'autorange': 'reversed', 
            'title': '',
            'tickfont': {'family': 'monospace', 'size': 13}
        },
        xaxis={'title': f'Monto ({nombre_moneda})'}
    )

    st.plotly_chart(fig, use_container_width=True)

    # --- 4. TABLA DETALLADA ---
    st.markdown("---")
    st.subheader("📋 Tabla de Datos Detallada")

    cols_mostrar = ['Posición', 'sigla', 'nombre_completo', 'nombre_grupo', 'Vigente', 'Vencida', 'Ejecución', 'Reprogramada Total', 'Cartera Bruta']
    df_tabla = df_pivot[cols_mostrar].copy()
    df_tabla.rename(columns={'sigla': 'Sigla', 'nombre_completo': 'Nombre Completo', 'nombre_grupo': 'Grupo'}, inplace=True)

    st.dataframe(
        df_tabla.style.format({
            'Vigente': '{:,.2f}',
            'Vencida': '{:,.2f}',
            'Ejecución': '{:,.2f}',
            'Reprogramada Total': '{:,.2f}',
            'Cartera Bruta': '{:,.2f}'
        }),
        use_container_width=True,
        hide_index=True
    )

    # --- 5. BOTÓN DE EXPORTACIÓN ---
    excel_data = generar_excel(df_pivot)
    _, col_boton = st.columns([3, 1])
    with col_boton:
        st.download_button(
            label="📥 Descargar Ranking Excel",
            data=excel_data,
            file_name=f"Ranking_Cartera_{fecha_sel}.xlsx",
            use_container_width=True
        )

    # --- 6. TEXTO DE DESCARGO ---
    st.markdown("---")
    st.caption(
        "📌 **Nota de Descargo:** Los datos mostrados proceden de los Boletines Estadísticos Oficiales de la ASFI "
        "(información pública). Esta información se difunde con fines strictly analíticos e informativos; "
        "no constituye una calificación de riesgo, opinión de auditoría, ni recomendación de inversión."
    )

if __name__ == "__main__":
    mostrar_ranking_cartera()