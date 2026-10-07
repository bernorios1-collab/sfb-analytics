# ==============================================================================
# FUNCIONALIDAD DEL ARCHIVO (IIFFGrupoEntidad.py):
# Este script genera la información de los Indicadores Financieros por Grupo
# de Entidades Financieras. Permite visualizar y comparar horizontalmente a las
# entidades pertenecientes a un grupo seleccionado a una fecha de corte dada,
# replicando la estructura en matriz de la ASFI y agregando gráficos comparativos.
# ==============================================================================

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from config_db import obtener_engine
from sqlalchemy import text
import io

@st.cache_data(ttl=600)
def consultar_db_grupo(query, params=None):
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

def mostrar_iiff_grupo():
    st.title("📊 Indicadores Financieros por Grupo de Entidades")

    # ======================================================
    # 1. ENCABEZADO Y FILTROS
    # ======================================================
    with st.container(border=True):
        c1, c2, c3 = st.columns([0.6, 0.9, 1.5])

        # AÑO
        df_years = consultar_db_grupo("""
            SELECT DISTINCT
                EXTRACT(YEAR FROM fecha_corte)::int as anio
            FROM estados_financieros
            ORDER BY anio DESC
        """)

        if df_years.empty:
            st.warning("No hay datos disponibles en la base de datos.")
            return

        anio_sel = c1.selectbox(
            "Año",
            df_years['anio'].tolist(),
            key="a_iiff_grupo"
        )

        # CORTE
        df_fechas = consultar_db_grupo("""
            SELECT DISTINCT fecha_corte
            FROM estados_financieros
            WHERE EXTRACT(YEAR FROM fecha_corte) = :anio
            ORDER BY fecha_corte DESC
        """, {"anio": anio_sel})

        fecha_sel = c2.selectbox(
            "Corte",
            df_fechas['fecha_corte'].astype(str).tolist(),
            key="f_iiff_grupo"
        )

        # GRUPO FINANCIERO
        df_grupos = consultar_db_grupo("""
            SELECT id_grupo, nombre_grupo
            FROM grupos_asfi
            ORDER BY id_grupo ASC
        """)

        grupo_sel = c3.selectbox(
            "📂 Grupo Financiero",
            df_grupos['nombre_grupo'].tolist(),
            key="g_iiff_grupo"
        )

        id_g = int(
            df_grupos[
                df_grupos['nombre_grupo'] == grupo_sel
            ]['id_grupo'].values[0]
        )

    # ======================================================
    # 2. OBTENCIÓN DE ENTIDADES DEL GRUPO
    # ======================================================
    df_ent = consultar_db_grupo("""
        SELECT
            id_entidad,
            nombre_entidad as sigla,
            nombre_completo
        FROM entidades
        WHERE id_grupo = :id_grupo
        ORDER BY 
            CASE WHEN nombre_entidad LIKE 'TS%%' THEN 0 ELSE 1 END,
            nombre_completo ASC
    """, {"id_grupo": id_g})

    if df_ent.empty:
        st.info("No se encontraron entidades asociadas al grupo seleccionado.")
        return

    # Listas de siglas para estructurar columnas
    entidades_unicas = df_ent['sigla'].tolist()
    entidades_ts = [e for e in entidades_unicas if e.startswith('TS')]
    entidades_individuales = [e for e in entidades_unicas if not e.startswith('TS')]
    columnas_entidades = entidades_individuales + entidades_ts

    # Mapa de id_entidad -> sigla
    dict_id_sigla = dict(zip(df_ent['id_entidad'], df_ent['sigla']))

    # ======================================================
    # 3. GRÁFICOS COMPARATIVOS POR ENTIDAD (ESTRUCTURA DE BALANCES)
    # ======================================================
    query_ef = """
        SELECT
            entidad,
            codigo_cuenta as cod,
            monto as monto_bs
        FROM estados_financieros
        WHERE fecha_corte = :fecha
          AND entidad IN ({})
    """.format(','.join([f"'{e}'" for e in entidades_individuales]))

    df_ef = consultar_db_grupo(query_ef, {"fecha": fecha_sel})

    if not df_ef.empty:
        def obtener_monto_cuenta(codigo):
            filtro = df_ef[df_ef['cod'].astype(str).str.startswith(str(codigo))]
            if filtro.empty:
                return pd.Series(0.0, index=entidades_individuales)
            return filtro.groupby('entidad')['monto_bs'].sum().reindex(entidades_individuales, fill_value=0)

        activos_ent = obtener_monto_cuenta('100')
        cartera_ent = obtener_monto_cuenta('130')
        pasivos_ent = obtener_monto_cuenta('200')
        patrimonio_ent = obtener_monto_cuenta('300')
        obl_pub_ent = obtener_monto_cuenta('210')

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
                height=260,
                margin=dict(t=35, b=10, l=10, r=10),
                title="Estructura del Activo por Entidad (en Bs.)",
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
                height=260,
                margin=dict(t=35, b=10, l=10, r=10),
                title="Estructura Pasivo + Patrimonio por Entidad (en Bs.)",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                **plotly_layout_theme
            )
            st.plotly_chart(fig2, use_container_width=True)

    # ======================================================
    # 4. CARGA DE INDICADORES FINANCIEROS Y PLAN
    # ======================================================
    st.markdown("---")

    ids_entidades = list(dict_id_sigla.keys())
    query_ind = """
        SELECT
            i.id,
            i.id_entidad,
            i.codigo_indicador,
            p.grupo_indicador,
            i.valor
        FROM indicadores_financieros i
        LEFT JOIN plan_indicadores p ON i.codigo_indicador = p.codigo_indicador
        WHERE i.fecha_corte = :fecha
          AND i.id_entidad IN ({})
        ORDER BY i.id ASC
    """.format(','.join([str(x) for x in ids_entidades]))

    df_ind_raw = consultar_db_grupo(query_ind, {"fecha": fecha_sel})

    if df_ind_raw.empty:
        st.warning("No existen indicadores financieros cargados para las entidades del grupo en la fecha seleccionada.")
        return

    df_ind_raw['sigla'] = df_ind_raw['id_entidad'].map(dict_id_sigla)

    grupos_plan = {}
    matriz_valores = {}

    for _, r in df_ind_raw.iterrows():
        g = str(r["grupo_indicador"]).strip() if pd.notna(r["grupo_indicador"]) and str(r["grupo_indicador"]).strip() != "" else "GENERAL"
        ind = str(r["codigo_indicador"]).strip()
        sigla = r["sigla"]
        val = float(r["valor"]) if pd.notna(r["valor"]) else None

        if g not in grupos_plan:
            grupos_plan[g] = []
        if ind not in grupos_plan[g]:
            grupos_plan[g].append(ind)

        if ind not in matriz_valores:
            matriz_valores[ind] = {}
        matriz_valores[ind][sigla] = val

    # ======================================================
    # 5. TABLA DESAGREGADA POR GRUPO (DIFERENCIADO NATIVO)
    # ======================================================
    st.markdown("""
    <style>
        .iiff-grp-container {
            max-height: 580px;
            overflow-y: auto;
            overflow-x: auto;
            border: 2px solid var(--border-color);
            border-radius: 8px;
            margin-bottom: 1rem;
            background-color: var(--background-color);
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
        }
        .iiff-grp-table {
            width: 100%;
            border-collapse: collapse;
            font-family: inherit;
        }

        /* CABECERA Y TÍTULOS PRINCIPALES CON TONO DIFERENCIADO ADAPTATIVA */
        .iiff-grp-titulo {
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
        .iiff-grp-subtitulo {
            background-color: var(--secondary-background-color);
            color: var(--text-color);
            text-align: center;
            font-size: 11px;
            padding: 6px;
            border-bottom: 2px solid #2563eb;
            filter: brightness(0.96);
            opacity: 0.9;
        }
        .iiff-grp-table thead th {
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
            letter-spacing: 0.04em;
        }

        /* GRUPOS INTERNOS */
        .iiff-grp-header {
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
        }
        .iiff-grp-col-ind {
            padding: 6px 10px;
            font-size: 11px;
            color: var(--text-color);
            background-color: var(--background-color);
            border-bottom: 1px solid var(--border-color);
            white-space: nowrap;
        }
        .iiff-grp-col-val {
            text-align: right;
            padding: 6px 8px;
            font-size: 11px;
            font-family: Consolas, monospace;
            color: var(--text-color);
            background-color: var(--background-color);
            border-bottom: 1px solid var(--border-color);
            border-left: 1px solid var(--border-color);
            white-space: nowrap;
        }
        .iiff-grp-col-ts {
            font-weight: bold;
            background-color: var(--secondary-background-color);
        }

        @media (prefers-color-scheme: dark) {
            .iiff-grp-container {
                box-shadow: 0 4px 18px rgba(255, 255, 255, 0.08), 0 0 0 1px rgba(255, 255, 255, 0.05);
            }
            .iiff-grp-titulo {
                filter: brightness(1.15);
            }
        }
    </style>
    """, unsafe_allow_html=True)

    headers_html = '<th style="min-width: 260px; text-align: left;">INDICADOR</th>' + "".join(
        [f'<th style="text-align: right; min-width: 95px;">{col}</th>' for col in columnas_entidades]
    )

    rows_list = []
    for grupo_nombre, lista_indicadores in grupos_plan.items():
        rows_list.append(f'<tr><td colspan="{len(columnas_entidades) + 1}" class="iiff-grp-header">{grupo_nombre}</td></tr>')

        for nombre_ind in lista_indicadores:
            row_tds = [f'<td class="iiff-grp-col-ind">{nombre_ind}</td>']

            for col in columnas_entidades:
                val = matriz_valores.get(nombre_ind, {}).get(col, None)
                val_fmt = f"{val * 100:,.2f}%" if val is not None and abs(val) <= 1.0 else (f"{val:,.4f}" if val is not None else "-")
                clase_td = "iiff-grp-col-val iiff-grp-col-ts" if col.startswith('TS') else "iiff-grp-col-val"
                row_tds.append(f'<td class="{clase_td}">{val_fmt}</td>')

            rows_list.append(f'<tr>{"".join(row_tds)}</tr>')

    rows_html = "".join(rows_list)
    fecha_fmt = pd.to_datetime(fecha_sel).strftime('%d/%m/%Y')
    total_cols = len(columnas_entidades) + 1

    html_table = (
        f'<div class="iiff-grp-container">'
        f'<table class="iiff-grp-table">'
        f'<thead>'
        f'<tr><td colspan="{total_cols}" class="iiff-grp-titulo">INDICADORES FINANCIEROS DESAGREGADOS POR GRUPO</td></tr>'
        f'<tr><td colspan="{total_cols}" class="iiff-grp-subtitulo"><b>Grupo Financiero:</b> {grupo_sel} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Fecha de Corte:</b> {fecha_fmt}</td></tr>'
        f'<tr>{headers_html}</tr>'
        f'</thead>'
        f'<tbody>{rows_html}</tbody>'
        f'</table>'
        f'</div>'
    )

    st.markdown(html_table, unsafe_allow_html=True)

    # ======================================================
    # 6. EXPORTAR A EXCEL
    # ======================================================
    filas_export = []
    for g_n, l_ind in grupos_plan.items():
        for ind_n in l_ind:
            f_data = {'GRUPO DE INDICADOR': g_n, 'INDICADOR': ind_n}
            for col in columnas_entidades:
                f_data[col] = matriz_valores.get(ind_n, {}).get(col, None)
            filas_export.append(f_data)

    df_export = pd.DataFrame(filas_export)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as wr:
        df_export.to_excel(
            wr,
            index=False,
            sheet_name='IIFF_Grupo'
        )

    _, col_boton = st.columns([3, 1])
    with col_boton:
        nombre_file = f"IIFF_Grupo_{grupo_sel.replace(' ', '_')}_{fecha_sel}"
        st.download_button(
            "📥 Descargar Reporte Excel",
            buf.getvalue(),
            f"{nombre_file}.xlsx",
            use_container_width=True
        )

# ==========================================================
# MAIN
# ==========================================================
if __name__ == "__main__":
    mostrar_iiff_grupo()