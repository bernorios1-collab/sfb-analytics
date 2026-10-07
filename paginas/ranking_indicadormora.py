import streamlit as st
import pandas as pd
import plotly.express as px
from config_db import obtener_engine
from sqlalchemy import text
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
        df.to_excel(writer, index=False, sheet_name='Ranking_Mora')
    return output.getvalue()

def mostrar_ranking_mora():
    st.title("🏆 Ranking de Índice de Morosidad")

    # --- 1. ENCABEZADO Y FILTROS ---
    with st.container(border=True):
        c1, c2, c3 = st.columns([0.6, 0.8, 1.6])

        # 1.1 AÑO
        df_years = consultar_db("""
            SELECT DISTINCT EXTRACT(YEAR FROM fecha_corte)::int as anio 
            FROM indicadores_financieros 
            ORDER BY anio DESC
        """)
        if df_years.empty:
            st.warning("No hay datos disponibles en la tabla de indicadores.")
            return
        anio_sel = c1.selectbox("Año", df_years['anio'].tolist(), key="a_rmora")

        # 1.2 FECHA CORTE
        df_fechas = consultar_db("""
            SELECT DISTINCT fecha_corte 
            FROM indicadores_financieros 
            WHERE EXTRACT(YEAR FROM fecha_corte) = :anio 
            ORDER BY fecha_corte DESC
        """, {"anio": anio_sel})

        if df_fechas.empty:
            st.warning("No se encontraron fechas de corte para el año seleccionado.")
            return

        fecha_sel = c2.selectbox("Corte", df_fechas['fecha_corte'].astype(str).tolist(), key="f_rmora")

        # 1.3 GRUPO FINANCIERO (Flexible e insensible a mayúsculas/acentos)
        df_grupos = consultar_db("SELECT id_grupo, nombre_grupo FROM grupos_asfi ORDER BY id_grupo ASC")

        opciones_consolidadas = [
            "TOTAL SISTEMA FINANCIERO BOLIVIANO",
            "TOTAL SISTEMA BANCARIO"
        ]
        opciones_grupo = opciones_consolidadas + df_grupos['nombre_grupo'].tolist()
        grupo_sel = c3.selectbox("📂 Ámbito / Grupo Financiero", opciones_grupo, key="g_rmora")

    # --- 2. CONSULTA DEL INDICADOR DE MORA ---
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

    # Búsqueda insensible a espacios en blanco y variaciones en la clave del indicador
    query_mora = f"""
        SELECT 
            e.nombre_entidad as sigla,
            COALESCE(NULLIF(e.nombre_completo, ''), e.nombre_entidad) as nombre_completo,
            g.nombre_grupo,
            i.valor
        FROM indicadores_financieros i
        JOIN entidades e ON i.id_entidad = e.id_entidad
        JOIN grupos_asfi g ON e.id_grupo = g.id_grupo
        WHERE i.fecha_corte = :fecha
          AND (
            REPLACE(i.codigo_indicador, ' ', '') LIKE '%%CarteraVencidaTotal+EjecuciónTotal/Cartera%%'
            OR REPLACE(i.codigo_indicador, ' ', '') LIKE '%%CarteraVencida+Ejecucion/Cartera%%'
          )
          AND e.nombre_entidad NOT LIKE 'TS%%'
          {filtro_grupo_sql}
        ORDER BY i.valor ASC
    """

    df_mora = consultar_db(query_mora, params)

    if df_mora.empty:
        st.info("ℹ️ No se encontraron registros de morosidad para la selección realizada.")
        return

    # Formatear el valor a porcentaje
    df_mora['mora_pct'] = df_mora['valor'].apply(lambda x: float(x) * 100 if abs(float(x)) <= 1 else float(x))
    
    # Ordenar por índice de mora ascendente (menor mora primero)
    df_mora = df_mora.sort_values(by='mora_pct', ascending=True).reset_index(drop=True)
    df_mora['Posición'] = df_mora.index + 1

    # Construcción directa de la etiqueta evitando problemas de tipos
    df_mora['entidad_etiqueta'] = [
        f"{int(pos):02d}. {sigla}" 
        for pos, sigla in zip(df_mora['Posición'], df_mora['sigla'])
    ]

    # --- 3. VISUALIZACIÓN GRÁFICA HORIZONTAL ---
    st.subheader("📊 Ranking de Índice de Morosidad (%)")

    fig = px.bar(
        df_mora,
        y='entidad_etiqueta',
        x='mora_pct',
        orientation='h',
        title=f"Índice de Mora - {grupo_sel}",
        color='mora_pct',
        color_continuous_scale='Reds',
        labels={'mora_pct': 'Mora (%)', 'entidad_etiqueta': 'Entidad (Ranking)'},
        custom_data=['Posición', 'nombre_completo', 'sigla', 'nombre_grupo', 'mora_pct']
    )

    fig.update_traces(
        hovertemplate=(
            "<b>Puesto #%{customdata[0]}: %{customdata[1]}</b> (%{customdata[2]})<br>" +
            "Grupo: %{customdata[3]}<br>" +
            "<b>Índice de Mora: %{customdata[4]:,.2f}%</b>" +
            "<extra></extra>"
        )
    )

    altura_grafico = max(450, len(df_mora) * 32)

    fig.update_layout(
        height=altura_grafico,
        coloraxis_showscale=False,
        margin=dict(l=10, r=20, t=50, b=50),
        yaxis={
            'autorange': 'reversed', 
            'title': '',
            'tickfont': {'family': 'monospace', 'size': 13}
        },
        xaxis={'title': 'Índice de Mora (%)', 'ticksuffix': '%'}
    )

    st.plotly_chart(fig, use_container_width=True)

    # --- 4. TABLA DETALLADA ---
    st.markdown("---")
    st.subheader("📋 Tabla de Datos Detallada")

    cols_mostrar = ['Posición', 'sigla', 'nombre_completo', 'nombre_grupo', 'mora_pct']
    df_tabla = df_mora[cols_mostrar].copy()
    df_tabla.rename(columns={
        'sigla': 'Sigla', 
        'nombre_completo': 'Nombre Completo', 
        'nombre_grupo': 'Grupo',
        'mora_pct': 'Mora (%)'
    }, inplace=True)

    st.dataframe(
        df_tabla.style.format({
            'Mora (%)': '{:,.2f}%'
        }),
        use_container_width=True,
        hide_index=True
    )

    # --- 5. BOTÓN DE EXPORTACIÓN ---
    excel_data = generar_excel(df_mora[['Posición', 'sigla', 'nombre_completo', 'nombre_grupo', 'mora_pct']])
    _, col_boton = st.columns([3, 1])
    with col_boton:
        st.download_button(
            label="📥 Descargar Ranking Excel",
            data=excel_data,
            file_name=f"Ranking_Mora_{fecha_sel}.xlsx",
            use_container_width=True
        )

    # --- 6. TEXTO DE DESCARGO ---
    st.markdown("---")
    st.caption(
        "📌 **Nota de Descargo:** Los datos mostrados proceden de los Boletines Estadísticos Oficiales de la ASFI "
        "(información pública). Esta información se difunde con fines estrictamente analíticos e informativos; "
        "no constituye una calificación de riesgo, opinión de auditoría, ni recomendación de inversión."
    )

if __name__ == "__main__":
    mostrar_ranking_mora()