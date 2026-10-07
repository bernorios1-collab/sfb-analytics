# ==============================================================================
# FUNCIONALIDAD DEL ARCHIVO (calificacion_grupo.py):
# Este script genera el reporte consolidado de Calificación de Cartera y Contingente
# por Grupo de Entidades Financieras. Permite visualizar y comparar horizontalmente
# a todas las entidades pertenecientes a un grupo seleccionado a una fecha de corte,
# replicando la estructura matricial oficial de la ASFI, con soporte multimoneda,
# gráficos comparativos, notas dinámicas desde BD y exportación a Excel.
# ==============================================================================

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from config_db import obtener_engine
from scrapers.indicadores_bcb import obtener_indicadores_bcb
from sqlalchemy import text
import io

@st.cache_data(ttl=600)
def consultar_db_grupo_calif(query, params=None):
    engine = obtener_engine()
    try:
        return pd.read_sql_query(
            text(query),
            engine,
            params=params
        )
    except Exception as e:
        st.error(f"Error consultando la base de datos: {e}")
        return pd.DataFrame()

def mostrar_calificacion_grupo():
    st.markdown("""
        <style>
        [data-testid="stMetricValue"] { font-size: 1.5rem !important; }
        [data-testid="stMetricLabel"] { font-size: 0.85rem !important; }
        </style>
    """, unsafe_allow_html=True)

    st.title("📂 Calificación de Cartera y Contingente por Grupo")

    dict_indicadores = obtener_indicadores_bcb()

    if "moneda_seleccionada_calif_grupo" not in st.session_state: 
        st.session_state.moneda_seleccionada_calif_grupo = list(dict_indicadores.keys())[0]

    # ======================================================
    # 1. ENCABEZADO Y FILTROS
    # ======================================================
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([0.5, 0.8, 1.2, 1.2])

        # AÑO
        df_years = consultar_db_grupo_calif("""
            SELECT DISTINCT
                EXTRACT(YEAR FROM fecha_corte)::int as anio
            FROM calificacion_cartera
            ORDER BY anio DESC
        """)

        if df_years.empty:
            st.warning("No hay datos disponibles de Calificación de Cartera en la base de datos.")
            return

        anio_sel = c1.selectbox(
            "Año",
            df_years['anio'].tolist(),
            key="anio_calif_grupo"
        )

        # CORTE
        df_fechas = consultar_db_grupo_calif("""
            SELECT DISTINCT fecha_corte
            FROM calificacion_cartera
            WHERE EXTRACT(YEAR FROM fecha_corte) = :anio
            ORDER BY fecha_corte DESC
        """, {"anio": anio_sel})

        fecha_sel = c2.selectbox(
            "Corte",
            df_fechas['fecha_corte'].astype(str).tolist(),
            key="fecha_calif_grupo"
        )

        # UNIDAD DE MEDIDA / MONEDA
        if st.session_state.moneda_seleccionada_calif_grupo not in dict_indicadores:
            st.session_state.moneda_seleccionada_calif_grupo = list(dict_indicadores.keys())[0]

        st.session_state.moneda_seleccionada_calif_grupo = c3.selectbox(
            "💰 Unidad de Medida", 
            list(dict_indicadores.keys()), 
            index=list(dict_indicadores.keys()).index(st.session_state.moneda_seleccionada_calif_grupo),
            key="moneda_calif_grupo"
        )

        # GRUPO FINANCIERO
        df_grupos = consultar_db_grupo_calif("""
            SELECT id_grupo, nombre_grupo
            FROM grupos_asfi
            ORDER BY id_grupo ASC
        """)

        grupo_sel = c4.selectbox(
            "📂 Grupo Financiero",
            df_grupos['nombre_grupo'].tolist(),
            key="grupo_calif_grupo"
        )

        id_g = int(
            df_grupos[
                df_grupos['nombre_grupo'] == grupo_sel
            ]['id_grupo'].values[0]
        )

        if len(dict_indicadores) == 1:
            st.caption("⚠️ No existe conectividad con BCB (Muestra únicamente datos en Bs.)")

    # ======================================================
    # 2. OBTENCIÓN DE ENTIDADES DEL GRUPO Y DATOS (TS AL FINAL)
    # ======================================================
    df_ent = consultar_db_grupo_calif("""
        SELECT
            id_entidad,
            nombre_entidad as sigla,
            nombre_completo
        FROM entidades
        WHERE id_grupo = :id_grupo
          AND nombre_entidad != 'BMU'
        ORDER BY 
            CASE WHEN nombre_entidad LIKE 'TS%' THEN 1 ELSE 0 END,
            nombre_completo ASC
    """, {"id_grupo": id_g})

    if df_ent.empty:
        st.info("No se encontraron entidades asociadas al grupo seleccionado.")
        return

    entidades_unicas = df_ent['sigla'].tolist()
    dict_id_sigla = dict(zip(df_ent['id_entidad'], df_ent['sigla']))
    ids_entidades = list(dict_id_sigla.keys())

    # Consultar calificación de cartera para todas las entidades del grupo en la fecha
    query_cc = """
        SELECT
            id_entidad,
            categoria_a, prevision_a,
            categoria_b, prevision_b,
            categoria_c, prevision_c,
            categoria_d, prevision_d,
            categoria_e, prevision_e,
            categoria_f, prevision_f,
            total_cartera, total_prevision,
            porcentaje_participacion
        FROM calificacion_cartera
        WHERE fecha_corte = :fecha
          AND id_entidad IN ({})
    """.format(','.join([str(x) for x in ids_entidades]))

    df_cc_raw = consultar_db_grupo_calif(query_cc, {"fecha": fecha_sel})

    if df_cc_raw.empty:
        st.warning("No existen registros de calificación de cartera para las entidades del grupo en la fecha seleccionada.")
        return

    df_cc_raw['sigla'] = df_cc_raw['id_entidad'].map(dict_id_sigla)

    factor_conv = dict_indicadores[st.session_state.moneda_seleccionada_calif_grupo]
    nombre_moneda = st.session_state.moneda_seleccionada_calif_grupo.split(' ')[0]

    # Construir matriz de datos por entidad
    matriz_cc = {}
    for _, r in df_cc_raw.iterrows():
        sigla = r['sigla']
        matriz_cc[sigla] = {
            'cat_a': float(r['categoria_a'] or 0) / factor_conv,
            'prev_a': float(r['prevision_a'] or 0) / factor_conv,
            'cat_b': float(r['categoria_b'] or 0) / factor_conv,
            'prev_b': float(r['prevision_b'] or 0) / factor_conv,
            'cat_c': float(r['categoria_c'] or 0) / factor_conv,
            'prev_c': float(r['prevision_c'] or 0) / factor_conv,
            'cat_d': float(r['categoria_d'] or 0) / factor_conv,
            'prev_d': float(r['prevision_d'] or 0) / factor_conv,
            'cat_e': float(r['categoria_e'] or 0) / factor_conv,
            'prev_e': float(r['prevision_e'] or 0) / factor_conv,
            'cat_f': float(r['categoria_f'] or 0) / factor_conv,
            'prev_f': float(r['prevision_f'] or 0) / factor_conv,
            'tot_cartera': float(r['total_cartera'] or 0) / factor_conv,
            'tot_prevision': float(r['total_prevision'] or 0) / factor_conv,
            'porcentaje': float(r['porcentaje_participacion'] or 0)
        }

    # ======================================================
    # 3. GRÁFICOS COMPARATIVOS POR ENTIDAD
    # ======================================================
    entidades_individuales = [e for e in entidades_unicas if not e.startswith('TS')]
    
    if entidades_individuales:
        lista_tot_cartera = [matriz_cc.get(e, {}).get('tot_cartera', 0) for e in entidades_individuales]
        lista_tot_prev = [matriz_cc.get(e, {}).get('tot_prevision', 0) for e in entidades_individuales]

        plotly_layout_theme = dict(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(showgrid=False, tickangle=-45),
            yaxis=dict(gridcolor='rgba(128,128,128,0.2)')
        )

        gc1, gc2 = st.columns(2)

        with gc1:
            fig1 = go.Figure()
            fig1.add_trace(go.Bar(
                x=entidades_individuales,
                y=lista_tot_cartera,
                name='Cartera y Contingente',
                marker_color='#004a99',
                hovertemplate='%{x} - Cartera: %{y:,.2f}<extra></extra>'
            ))
            fig1.update_layout(
                height=260,
                margin=dict(t=35, b=10, l=10, r=10),
                title=f"Total Cartera y Contingente por Entidad ({nombre_moneda})",
                showlegend=False,
                **plotly_layout_theme
            )
            st.plotly_chart(fig1, use_container_width=True)

        with gc2:
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(
                x=entidades_individuales,
                y=lista_tot_prev,
                name='Previsión Específica',
                marker_color='#d62728',
                hovertemplate='%{x} - Previsión: %{y:,.2f}<extra></extra>'
            ))
            fig2.update_layout(
                height=260,
                margin=dict(t=35, b=10, l=10, r=10),
                title=f"Total Previsiones Constituidas ({nombre_moneda})",
                showlegend=False,
                **plotly_layout_theme
            )
            st.plotly_chart(fig2, use_container_width=True)

    st.markdown("---")

    # ======================================================
    # 4. TABLA MATRICIAL OFICIAL ASFI (HTML ADAPTATIVO)
    # ======================================================
    st.markdown("""
    <style>
        .calif-grp-container {
            max-height: 600px;
            overflow-y: auto;
            overflow-x: auto;
            border: 2px solid var(--border-color);
            border-radius: 8px;
            margin-bottom: 1rem;
            background-color: var(--background-color);
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
        }
        .calif-grp-table {
            width: 100%;
            border-collapse: collapse;
            font-family: inherit;
        }
        .calif-grp-titulo {
            background-color: var(--secondary-background-color);
            color: var(--text-color);
            text-align: center;
            font-weight: 800;
            font-size: 13px;
            padding: 9px;
            letter-spacing: 0.06em;
            border-bottom: 1px solid var(--border-color);
            filter: brightness(0.92);
        }
        .calif-grp-subtitulo {
            background-color: var(--secondary-background-color);
            color: var(--text-color);
            text-align: center;
            font-size: 11px;
            padding: 6px;
            border-bottom: 2px solid #004a99;
            filter: brightness(0.96);
            opacity: 0.9;
        }
        .calif-grp-table thead th {
            position: sticky;
            top: 0;
            z-index: 10;
            background-color: var(--secondary-background-color);
            color: var(--text-color);
            font-size: 11px;
            font-weight: 700;
            padding: 8px 10px;
            border-bottom: 2px solid var(--border-color);
            border-left: 1px solid var(--border-color);
            text-align: right;
        }
        .calif-grp-table thead th:first-child {
            text-align: left;
            min-width: 280px;
        }
        .calif-grp-col-cat {
            padding: 6px 12px;
            font-size: 11px;
            color: var(--text-color);
            background-color: var(--background-color);
            border-bottom: 1px solid var(--border-color);
            white-space: nowrap;
            font-weight: 600;
        }
        .calif-grp-col-prev {
            padding: 6px 12px 6px 24px;
            font-size: 11px;
            color: var(--text-color);
            background-color: var(--background-color);
            border-bottom: 1px solid var(--border-color);
            white-space: nowrap;
            font-style: italic;
            opacity: 0.9;
        }
        .calif-grp-col-val {
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
        .calif-grp-total-row {
            font-weight: bold;
            background-color: var(--secondary-background-color) !important;
            border-top: 2px solid var(--border-color);
            border-bottom: 2px solid var(--border-color);
        }
        @media (prefers-color-scheme: dark) {
            .calif-grp-container {
                box-shadow: 0 4px 18px rgba(255, 255, 255, 0.08), 0 0 0 1px rgba(255, 255, 255, 0.05);
            }
            .calif-grp-titulo {
                filter: brightness(1.15);
            }
        }
    </style>
    """, unsafe_allow_html=True)

    headers_html = '<th style="text-align: left;">CATEGORÍA DE RIESGO</th>' + "".join(
        [f'<th>{col}</th>' for col in entidades_unicas]
    )

    filas_estructura = [
        ("CATEGORÍA A ⁽²⁾", "cat_a", False),
        ("PREVISIÓN conforme a (2)", "prev_a", True),
        ("CATEGORÍA B ⁽³⁾", "cat_b", False),
        ("PREVISIÓN conforme a (3)", "prev_b", True),
        ("CATEGORÍA C", "cat_c", False),
        ("PREVISIÓN 20%", "prev_c", True),
        ("CATEGORÍA D", "cat_d", False),
        ("PREVISIÓN 50%", "prev_d", True),
        ("CATEGORÍA E", "cat_e", False),
        ("PREVISIÓN 80%", "prev_e", True),
        ("CATEGORÍA F", "cat_f", False),
        ("PREVISIÓN 100%", "prev_f", True),
        ("TOTAL CARTERA Y CONTINGENTE ⁽⁴⁾", "tot_cartera", False, True),
        ("TOTAL PREVISIÓN ESPECÍFICA", "tot_prevision", False, True),
        ("Particip.Respecto Tot.Sistema", "porcentaje", False, False, True)
    ]

    rows_html = []
    for item in filas_estructura:
        nombre_fila = item[0]
        key_val = item[1]
        es_prev = item[2] if len(item) > 2 else False
        es_total = item[3] if len(item) > 3 else False
        es_porc = item[4] if len(item) > 4 else False

        clase_td_nombre = "calif-grp-col-prev" if es_prev else "calif-grp-col-cat"
        clase_tr = ' class="calif-grp-total-row"' if es_total or es_porc else ''

        row_tds = [f'<td class="{clase_td_nombre}">{nombre_fila}</td>']

        for ent in entidades_unicas:
            val = matriz_cc.get(ent, {}).get(key_val, 0.0)
            if es_porc:
                val_pct = val * 100 if val <= 1.0 else val
                val_fmt = f"{val_pct:,.2f}%" if val > 0 else "-"
            else:
                val_fmt = f"{val:,.2f}" if val != 0 else "-"
            row_tds.append(f'<td class="calif-grp-col-val">{val_fmt}</td>')

        rows_html.append(f'<tr{clase_tr}>{"".join(row_tds)}</tr>')

    fecha_fmt = pd.to_datetime(fecha_sel).strftime('%d/%m/%Y')
    total_cols = len(entidades_unicas) + 1

    html_table = (
        f'<div class="calif-grp-container">'
        f'<table class="calif-grp-table">'
        f'<thead>'
        f'<tr><td colspan="{total_cols}" class="calif-grp-titulo">CALIFICACIÓN DE CARTERA Y CONTINGENTE ⁽¹⁾</td></tr>'
        f'<tr><td colspan="{total_cols}" class="calif-grp-subtitulo"><b>Grupo:</b> {grupo_sel} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Fecha de Corte:</b> {fecha_fmt} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Expresado en:</b> {nombre_moneda}</td></tr>'
        f'<tr>{headers_html}</tr>'
        f'</thead>'
        f'<tbody>{"".join(rows_html)}</tbody>'
        f'</table>'
        f'</div>'
    )

    st.markdown(html_table, unsafe_allow_html=True)

    # Consulta y despliegue dinámico de notas desde la Base de Datos
    query_notas = """
        SELECT numero_nota, texto_nota 
        FROM calificacion_notas 
        WHERE id_grupo = :id_grupo AND fecha_corte = :fecha 
        ORDER BY numero_nota ASC
    """
    df_notas = consultar_db_grupo_calif(query_notas, {"id_grupo": id_g, "fecha": fecha_sel})

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

    # ======================================================
    # 5. EXPORTAR A EXCEL
    # ======================================================
    filas_export = []
    for item in filas_estructura:
        nombre_fila = item[0]
        key_val = item[1]
        es_porc = item[4] if len(item) > 4 else False
        f_data = {'CATEGORÍA DE RIESGO': nombre_fila}
        for ent in entidades_unicas:
            val = matriz_cc.get(ent, {}).get(key_val, 0.0)
            if es_porc:
                f_data[ent] = (val * 100 if val <= 1.0 else val) / 100.0
            else:
                f_data[ent] = val
        filas_export.append(f_data)

    df_export = pd.DataFrame(filas_export)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as wr:
        df_export.to_excel(
            wr,
            index=False,
            sheet_name='Calif_Cartera_Grupo'
        )
        if not df_notas.empty:
            df_notas.to_excel(wr, index=False, sheet_name='Notas_ASFI')

    _, col_boton = st.columns([3, 1])
    with col_boton:
        nombre_file = f"Calificacion_Cartera_{grupo_sel.replace(' ', '_')}_{fecha_sel}"
        st.download_button(
            "📥 Descargar Reporte Excel",
            buf.getvalue(),
            f"{nombre_file}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

if __name__ == "__main__":
    mostrar_calificacion_grupo()