import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from config_db import obtener_engine
from sqlalchemy import text
import io

# ==========================================================
# FUNCIONES AUXILIARES
# ==========================================================

def calcular_indicadores_asfi_replica(df_ef):
    def get_v(codigo):
        return df_ef[
            df_ef['cod'].astype(str).str.startswith(str(codigo))
        ]['monto_bs'].sum()

    activo_total = get_v('100')
    pasivo_total = get_v('200')
    patrimonio = get_v('300')

    return {
        "activo": activo_total,
        "pasivo": pasivo_total,
        "patrimonio": patrimonio
    }

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
        st.error(f"Error: {e}")
        return pd.DataFrame()

# ==========================================================
# PANTALLA PRINCIPAL
# ==========================================================

def mostrar_iiff_entidad():
    st.title("📊 Indicadores Financieros")

    # ======================================================
    # FILTROS
    # ======================================================
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([0.4, 0.6, 1.3, 1.7])

        # AÑOS
        df_years = consultar_db("""
            SELECT DISTINCT
                EXTRACT(YEAR FROM fecha_corte)::int as anio
            FROM estados_financieros
            ORDER BY anio DESC
        """)

        if df_years.empty:
            return

        anio_sel = c1.selectbox(
            "Año",
            df_years['anio'].tolist(),
            key="a_iiff"
        )

        # FECHAS
        df_fechas = consultar_db("""
            SELECT DISTINCT fecha_corte
            FROM estados_financieros
            WHERE EXTRACT(YEAR FROM fecha_corte) = :anio
            ORDER BY fecha_corte DESC
        """, {"anio": anio_sel})

        fecha_sel = c2.selectbox(
            "Corte",
            df_fechas['fecha_corte'].astype(str).tolist(),
            key="f_iiff"
        )

        # GRUPOS
        df_grupos = consultar_db("""
            SELECT id_grupo, nombre_grupo
            FROM grupos_asfi
            ORDER BY id_grupo ASC
        """)

        grupo_sel = c3.selectbox(
            "📂 Grupo Financiero",
            df_grupos['nombre_grupo'].tolist(),
            key="g_iiff"
        )

        id_g = int(
            df_grupos[
                df_grupos['nombre_grupo'] == grupo_sel
            ]['id_grupo'].values[0]
        )

        # ENTIDADES
        df_ent = consultar_db("""
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

        opciones_ent = {}
        for _, r in df_ent.iterrows():
            nombre = r['nombre_completo'] if pd.notna(r['nombre_completo']) and r['nombre_completo'] != "" else r['sigla']
            opciones_ent[f"{nombre} ({r['sigla']})"] = {
                "sigla": r['sigla'],
                "id_entidad": r['id_entidad']
            }

        entidad_display = c4.selectbox(
            "🏛️ Entidad Financiera",
            options=list(opciones_ent.keys()),
            key="e_iiff"
        )

        banco_sel = opciones_ent[entidad_display]["sigla"]
        id_entidad_sel = opciones_ent[entidad_display]["id_entidad"]

    # ======================================================
    # ESTADOS FINANCIEROS Y GRÁFICOS
    # ======================================================
    query = """
        SELECT
            codigo_cuenta as cod,
            monto as monto_bs
        FROM estados_financieros
        WHERE entidad = :entidad
          AND fecha_corte = :fecha
    """

    df_ef = consultar_db(query, {
        "entidad": banco_sel,
        "fecha": fecha_sel
    })

    if df_ef.empty:
        st.info("No se encontraron registros contables.")
        return

    def get_v_graf(codigo):
        return df_ef[
            df_ef['cod'].astype(str).str.startswith(str(codigo))
        ]['monto_bs'].sum()

    activo = get_v_graf('100')
    pasivo = get_v_graf('200')
    patrimonio = get_v_graf('300')

    cartera = get_v_graf('130')
    obl_pub = get_v_graf('210')

    p_cartera = (cartera / activo * 100) if activo > 0 else 0
    p_otros_act = (max(0, activo - cartera) / activo * 100) if activo > 0 else 0

    p_total_pas_pat = pasivo + patrimonio

    p_obl_pub = (obl_pub / p_total_pas_pat * 100) if p_total_pas_pat > 0 else 0
    p_otros_pas = (max(0, pasivo - obl_pub) / p_total_pas_pat * 100) if p_total_pas_pat > 0 else 0
    p_pat = (patrimonio / p_total_pas_pat * 100) if p_total_pas_pat > 0 else 0

    plotly_layout_theme = dict(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(showgrid=False),
        yaxis=dict(gridcolor='rgba(128,128,128,0.2)')
    )

    cg1, cg2 = st.columns(2)

    with cg1:
        fig1 = go.Figure(data=[
            go.Bar(
                name='Cartera',
                x=['Activo'],
                y=[cartera],
                text=[f"{p_cartera:.1f}%"],
                textposition='inside',
                marker_color='#1f77b4'
            ),
            go.Bar(
                name='Otros Act.',
                x=['Activo'],
                y=[max(0, activo - cartera)],
                text=[f"{p_otros_act:.1f}%"],
                textposition='inside',
                marker_color='#aec7e8'
            )
        ])

        fig1.update_layout(
            barmode='stack',
            height=260,
            margin=dict(t=30, b=10),
            title="Estructura del Activo",
            **plotly_layout_theme
        )

        st.plotly_chart(fig1, use_container_width=True)

    with cg2:
        fig2 = go.Figure(data=[
            go.Bar(
                name='Oblig. Público',
                x=['Pas+Pat'],
                y=[obl_pub],
                text=[f"{p_obl_pub:.1f}%"],
                textposition='inside',
                marker_color='#d62728'
            ),
            go.Bar(
                name='Otros Pas.',
                x=['Pas+Pat'],
                y=[max(0, pasivo - obl_pub)],
                text=[f"{p_otros_pas:.1f}%"],
                textposition='inside',
                marker_color='#ff9896'
            ),
            go.Bar(
                name='Patrimonio',
                x=['Pas+Pat'],
                y=[patrimonio],
                text=[f"{p_pat:.1f}%"],
                textposition='inside',
                marker_color='#ff7f0e'
            )
        ])

        fig2.update_layout(
            barmode='stack',
            height=260,
            margin=dict(t=30, b=10),
            title="Estructura del Pasivo + Pat.",
            **plotly_layout_theme
        )

        st.plotly_chart(fig2, use_container_width=True)

    # ======================================================
    # TABLA DE INDICADORES FINANCIEROS (DIFERENCIADO NATIVO)
    # ======================================================
    st.markdown("---")

    query_ind = """
        SELECT
            i.id,
            i.codigo_indicador,
            p.grupo_indicador,
            p.notas_aclaratorias,
            i.valor
        FROM indicadores_financieros i
        LEFT JOIN plan_indicadores p
            ON i.codigo_indicador = p.codigo_indicador
        WHERE i.id_entidad = :id_entidad
          AND i.fecha_corte = :fecha
        ORDER BY i.id ASC
    """

    df_res = consultar_db(query_ind, {
        "id_entidad": id_entidad_sel,
        "fecha": fecha_sel
    })

    if df_res.empty:
        st.warning("No existen indicadores cargados para la selección actual.")
        return

    grupos = {}
    for _, r in df_res.iterrows():
        grupo = str(r["grupo_indicador"]).strip() if pd.notna(r["grupo_indicador"]) and str(r["grupo_indicador"]).strip() != "" else "GENERAL"
        indicador = str(r["codigo_indicador"]).strip()
        nota = str(r["notas_aclaratorias"]) if pd.notna(r["notas_aclaratorias"]) else ""
        valor = float(r["valor"]) if pd.notna(r["valor"]) else 0.0

        if grupo not in grupos:
            grupos[grupo] = []

        grupos[grupo].append({
            "indicador": indicador,
            "valor": valor,
            "nota": nota
        })

    st.markdown("""
    <style>
        .iiff-container {
            max-height: 580px;
            overflow-y: auto;
            border: 2px solid var(--border-color);
            border-radius: 8px;
            margin-bottom: 1rem;
            background-color: var(--background-color);
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
        }
        .iiff-table {
            width: 100%;
            border-collapse: collapse;
            font-family: inherit;
        }

        /* CABECERA PRINCIPAL LEVEMENTE DIFERENCIADA ADAPTATIVA */
        .iiff-titulo {
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
        .iiff-subtitulo {
            background-color: var(--secondary-background-color);
            color: var(--text-color);
            text-align: center;
            font-size: 11px;
            padding: 6px;
            border-bottom: 2px solid #2563eb;
            filter: brightness(0.96);
            opacity: 0.9;
        }
        .iiff-table thead th {
            position: sticky;
            top: 0;
            z-index: 10;
            background-color: var(--secondary-background-color);
            color: var(--text-color);
            font-size: 11px;
            font-weight: 700;
            padding: 8px 10px;
            border-bottom: 2px solid var(--border-color);
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }

        /* GRUPOS INTERNOS */
        .iiff-grupo {
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
        .iiff-col-ind {
            width: 35%;
            padding: 6px 10px;
            font-size: 11px;
            color: var(--text-color);
            background-color: var(--background-color);
            border-bottom: 1px solid var(--border-color);
            vertical-align: top;
        }
        .iiff-col-val {
            width: 15%;
            text-align: right;
            padding: 6px 10px;
            font-size: 11px;
            font-family: Consolas, monospace;
            font-weight: bold;
            color: var(--text-color);
            background-color: var(--background-color);
            border-bottom: 1px solid var(--border-color);
            border-left: 1px solid var(--border-color);
            vertical-align: top;
            white-space: nowrap;
        }
        .iiff-col-nota {
            width: 50%;
            padding: 6px 10px;
            font-size: 11px;
            color: var(--text-color);
            background-color: var(--background-color);
            opacity: 0.75;
            border-bottom: 1px solid var(--border-color);
            border-left: 1px solid var(--border-color);
            vertical-align: top;
        }

        /* MODO OSCURO SISTEMA */
        @media (prefers-color-scheme: dark) {
            .iiff-container {
                box-shadow: 0 4px 18px rgba(255, 255, 255, 0.08), 0 0 0 1px rgba(255, 255, 255, 0.05);
            }
            .iiff-titulo {
                filter: brightness(1.15);
            }
        }
    </style>
    """, unsafe_allow_html=True)

    rows_list = []
    for grupo, lista_items in grupos.items():
        rows_list.append(f'<tr><td colspan="3" class="iiff-grupo">{grupo}</td></tr>')

        for item in lista_items:
            nombre_ind = item["indicador"]
            valor = item["valor"]
            nota = item["nota"]

            valor_fmt = f"{valor * 100:,.2f}%" if abs(valor) <= 1.0 else f"{valor:,.4f}"

            rows_list.append(
                f'<tr>'
                f'<td class="iiff-col-ind">{nombre_ind}</td>'
                f'<td class="iiff-col-val">{valor_fmt}</td>'
                f'<td class="iiff-col-nota">{nota}</td>'
                f'</tr>'
            )

    rows_html = "".join(rows_list)
    fecha_fmt = pd.to_datetime(fecha_sel).strftime('%d/%m/%Y')

    html_table = (
        f'<div class="iiff-container">'
        f'<table class="iiff-table">'
        f'<thead>'
        f'<tr><td colspan="3" class="iiff-titulo">INDICADORES FINANCIEROS</td></tr>'
        f'<tr><td colspan="3" class="iiff-subtitulo"><b>Entidad:</b> {banco_sel} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Fecha:</b> {fecha_fmt}</td></tr>'
        f'<tr><th style="width:35%;">INDICADOR</th><th style="width:15%; text-align:right;">VALOR</th><th style="width:50%;">NOTAS ACLARATORIAS</th></tr>'
        f'</thead>'
        f'<tbody>{rows_html}</tbody>'
        f'</table>'
        f'</div>'
    )

    st.markdown(html_table, unsafe_allow_html=True)

    # ======================================================
    # EXPORTAR EXCEL
    # ======================================================
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as wr:
        df_res[['codigo_indicador', 'grupo_indicador', 'valor', 'notas_aclaratorias']].to_excel(
            wr, index=False, sheet_name='Indicadores'
        )

    _, col_boton = st.columns([3, 1])
    with col_boton:
        st.download_button(
            "📥 Descargar Reporte Excel",
            buf.getvalue(),
            f"IIFF_ASFI_{banco_sel}.xlsx",
            use_container_width=True
        )

if __name__ == "__main__":
    mostrar_iiff_entidad()