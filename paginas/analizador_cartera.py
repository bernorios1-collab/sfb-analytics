# ==============================================================================
# FUNCIONALIDAD DEL ARCHIVO (analizador_cartera.py):
# Script interactivo en Streamlit para el análisis detallado de cartera, 
# morosidad, contingentes y estructura de activos por Entidad o Total Sistema.
# ==============================================================================

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from config_db import obtener_engine
from sqlalchemy import text
from scrapers.indicadores_bcb import obtener_indicadores_bcb
import io

@st.cache_data(ttl=600)
def consultar_db(query, params=None):
    engine = obtener_engine()
    try:
        return pd.read_sql_query(text(query), engine, params=params)
    except Exception as e:
        st.error(f"Error al consultar la base de datos: {e}")
        return pd.DataFrame()

def mostrar_analizador_cartera():
    st.title("🔎 Analizador Detallado de Cartera y Contingente")

    dict_indicadores = obtener_indicadores_bcb()
    if "moneda_seleccionada" not in st.session_state:
        st.session_state.moneda_seleccionada = list(dict_indicadores.keys())[0]

    # --- 1. CABECERA Y SELECCIÓN DE ENTIDAD O TOTAL SISTEMA ---
    with st.container(border=True):
        t1, t2, t3 = st.columns([0.5, 0.8, 1.2])

        df_years = consultar_db("SELECT DISTINCT EXTRACT(YEAR FROM fecha_corte)::int as anio FROM estados_financieros ORDER BY anio DESC")
        if df_years.empty:
            st.warning("No hay datos disponibles en la base de datos.")
            return
        anio_sel = t1.selectbox("Año", df_years['anio'].tolist(), key="a_an_cartera")

        df_fechas = consultar_db("""
            SELECT DISTINCT fecha_corte 
            FROM estados_financieros 
            WHERE EXTRACT(YEAR FROM fecha_corte) = :anio 
            ORDER BY fecha_corte DESC
        """, {"anio": anio_sel})
        
        if df_fechas.empty:
            st.warning("No hay fechas de corte disponibles para el año seleccionado.")
            return
            
        fecha_sel = t2.selectbox("Corte", df_fechas['fecha_corte'].astype(str).tolist(), key="f_an_cartera")

        if st.session_state.moneda_seleccionada not in dict_indicadores:
            st.session_state.moneda_seleccionada = list(dict_indicadores.keys())[0]

        st.session_state.moneda_seleccionada = t3.selectbox(
            "💰 Unidad de Medida", 
            list(dict_indicadores.keys()), 
            index=list(dict_indicadores.keys()).index(st.session_state.moneda_seleccionada),
            key="m_an_cartera"
        )

        f2, f3 = st.columns([1.3, 1.7])

        df_grupos = consultar_db("SELECT id_grupo, nombre_grupo FROM grupos_asfi ORDER BY id_grupo ASC")
        if df_grupos.empty:
            st.warning("No hay grupos financieros registrados en la base de datos.")
            return

        grupo_sel = f2.selectbox("📂 Grupo Financiero", df_grupos['nombre_grupo'].tolist(), key="g_an_cartera")
        
        match_grupo = df_grupos[df_grupos['nombre_grupo'] == grupo_sel]
        if match_grupo.empty:
            st.warning("El grupo seleccionado no fue encontrado.")
            return
            
        id_g = int(match_grupo['id_grupo'].values[0])

        df_ent = consultar_db("""
            SELECT e.id_entidad, e.nombre_entidad as sigla, e.nombre_completo 
            FROM entidades e
            WHERE e.id_grupo = :id_grupo
            ORDER BY 
                CASE WHEN e.nombre_entidad LIKE 'TS%%' THEN 0 ELSE 1 END,
                e.nombre_completo ASC
        """, {"id_grupo": id_g})

        opciones_ent = {}
        for _, r in df_ent.iterrows():
            nombre = r['nombre_completo'] if pd.notna(r['nombre_completo']) and r['nombre_completo'] != "" else r['sigla']
            opciones_ent[f"{nombre} ({r['sigla']})"] = {
                "sigla": r['sigla'],
                "id_entidad": r['id_entidad'],
                "nombre_completo": nombre
            }

        if not opciones_ent:
            st.info("No hay entidades registradas en el grupo seleccionado.")
            return

        entidad_display = f3.selectbox("🏛️ Entidad Financiera / Consolidado", options=list(opciones_ent.keys()), key="e_an_cartera")
        sigla_ent = opciones_ent[entidad_display]["sigla"]
        id_entidad_sel = opciones_ent[entidad_display]["id_entidad"]

    factor_conv = dict_indicadores[st.session_state.moneda_seleccionada]
    nombre_moneda = st.session_state.moneda_seleccionada.split(' ')[0]
    es_total_sistema = sigla_ent.startswith("TS") or "TOTAL SISTEMA" in entidad_display.upper()

    # --- 2. PESTAÑAS DE ANÁLISIS ---
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Estructura de Cartera", 
        "🔄 Cartera Reprogramada", 
        "📈 Índice de Morosidad", 
        "📋 Indicadores de Cartera"
    ])

    # =========================================================================
    # TAB 1: ESTRUCTURA DE CARTERA
    # =========================================================================
    with tab1:
        st.subheader(f"Estructura y Resumen Completo de Cartera - {sigla_ent}")
        
        # Filtro estricto de cuentas para evitar duplicar niveles jerárquicos
        cuentas_objetivo = ('131.00', '133.00', '134.00', '135.00', '136.00', '137.00', '138.00', '139.00', '600.00', '651.00')

        if es_total_sistema:
            query_est_all = """
                SELECT 
                    :sigla as sigla,
                    g.nombre_grupo,
                    f.codigo_cuenta,
                    SUM(f.monto) as monto_bs
                FROM estados_financieros f
                JOIN entidades e ON f.entidad = e.nombre_entidad
                JOIN grupos_asfi g ON e.id_grupo = g.id_grupo
                WHERE f.fecha_corte = :fecha
                  AND e.id_grupo = :id_grupo
                  AND e.nombre_entidad NOT LIKE 'TS%%'
                  AND f.codigo_cuenta IN :cuentas
                GROUP BY g.nombre_grupo, f.codigo_cuenta
            """
            params_est = {"fecha": fecha_sel, "id_grupo": id_g, "sigla": sigla_ent, "cuentas": cuentas_objetivo}
        else:
            query_est_all = """
                SELECT 
                    e.nombre_entidad as sigla,
                    g.nombre_grupo,
                    f.codigo_cuenta,
                    f.monto as monto_bs
                FROM estados_financieros f
                JOIN entidades e ON f.entidad = e.nombre_entidad
                JOIN grupos_asfi g ON e.id_grupo = g.id_grupo
                WHERE f.fecha_corte = :fecha
                  AND e.nombre_entidad = :entidad
                  AND f.codigo_cuenta IN :cuentas
            """
            params_est = {"fecha": fecha_sel, "entidad": sigla_ent, "cuentas": cuentas_objetivo}

        df_all_est = consultar_db(query_est_all, params_est)

        if df_all_est.empty:
            st.info("No se registraron cuentas de cartera para este corte.")
        else:
            df_all_est['monto'] = df_all_est['monto_bs'] / factor_conv
            m_dict = dict(zip(df_all_est['codigo_cuenta'], df_all_est['monto']))

            # Cuentas de Cartera Directa
            c131 = m_dict.get('131.00', 0.0)
            c133 = m_dict.get('133.00', 0.0)
            c134 = m_dict.get('134.00', 0.0)
            c135 = m_dict.get('135.00', 0.0)
            c136 = m_dict.get('136.00', 0.0)
            c137 = m_dict.get('137.00', 0.0)
            c138 = m_dict.get('138.00', 0.0)
            c139 = abs(m_dict.get('139.00', 0.0))

            vigente_tot = c131 + c135
            vencida_tot = c133 + c136
            ejecucion_tot = c134 + c137
            cartera_bruta_directa = vigente_tot + vencida_tot + ejecucion_tot
            cartera_reprog_tot = c135 + c136 + c137
            cartera_neta = cartera_bruta_directa - c139
            mora_val = ((vencida_tot + ejecucion_tot) / cartera_bruta_directa * 100) if cartera_bruta_directa > 0 else 0

            # Cartera Contingente Crediticia (600.00 - Otras Contingencias 651.00)
            c600_total = m_dict.get('600.00', 0.0)
            c651_otras = m_dict.get('651.00', 0.0)
            cartera_contingente = max(0.0, c600_total - c651_otras)

            # Exposición Total Combinada
            total_cartera_contingente = cartera_bruta_directa + cartera_contingente

            col_graf, col_met = st.columns([1.2, 0.8])
            
            with col_graf:
                df_pie = pd.DataFrame({
                    'Segmento': ['Cartera Vigente', 'Cartera Vencida', 'Cartera en Ejecución'],
                    'Monto': [vigente_tot, vencida_tot, ejecucion_tot]
                })
                fig_pie = px.pie(
                    df_pie, 
                    names='Segmento', 
                    values='Monto',
                    hole=0.45,
                    color='Segmento',
                    color_discrete_map={
                        'Cartera Vigente': '#2ecc71',
                        'Cartera Vencida': '#e74c3c',
                        'Cartera en Ejecución': '#e67e22'
                    },
                    title=f"Estructura Interna de Cartera Directa ({nombre_moneda})"
                )
                fig_pie.update_traces(
                    textinfo='percent+label',
                    hovertemplate='<b>%{label}</b><br>Monto: %{value:,.2f}<br>Porcentaje: %{percent}<extra></extra>'
                )
                fig_pie.update_layout(
                    height=420, 
                    margin=dict(t=40, b=10, l=10, r=10),
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)'
                )
                st.plotly_chart(fig_pie, use_container_width=True)

            with col_met:
                st.markdown("##### 📌 Cuentas Integrales de Cartera")
                
                html_resumen_cuentas = f"""
                <style>
                    .tabla-resumen-container {{
                        border: 2px solid var(--border-color);
                        border-radius: 8px;
                        background-color: var(--background-color);
                        overflow: hidden;
                        box-shadow: 0 4px 12px rgba(0,0,0,0.12);
                    }}
                    .tabla-resumen {{
                        width: 100%;
                        border-collapse: collapse;
                        font-family: inherit;
                        font-size: 11px;
                    }}
                    .tabla-resumen td {{
                        padding: 7px 10px;
                        border-bottom: 1px solid var(--border-color);
                        color: var(--text-color);
                    }}
                    .lbl-cuenta {{
                        font-weight: 600;
                    }}
                    .val-cuenta {{
                        text-align: right;
                        font-family: Consolas, monospace;
                        font-weight: bold;
                    }}
                </style>
                <div class="tabla-resumen-container">
                    <table class="tabla-resumen">
                        <tr>
                            <td class="lbl-cuenta">Cartera Bruta Directa Total</td>
                            <td class="val-cuenta">{cartera_bruta_directa:,.2f}</td>
                        </tr>
                        <tr>
                            <td class="lbl-cuenta">Previsión Específica (139.00)</td>
                            <td class="val-cuenta" style="color: #e74c3c;">-{c139:,.2f}</td>
                        </tr>
                        <tr style="background-color: var(--secondary-background-color);">
                            <td class="lbl-cuenta" style="color: #2563eb;">Cartera Neta Directa Total</td>
                            <td class="val-cuenta" style="color: #2563eb;">{cartera_neta:,.2f}</td>
                        </tr>
                        <tr>
                            <td class="lbl-cuenta">Productos Devengados (138.00)</td>
                            <td class="val-cuenta">{c138:,.2f}</td>
                        </tr>
                        <tr>
                            <td class="lbl-cuenta">Cartera Reprogramada Total</td>
                            <td class="val-cuenta">{cartera_reprog_tot:,.2f}</td>
                        </tr>
                        <tr>
                            <td class="lbl-cuenta" style="color: #8e44ad;">Cartera Contingente (Cuentas 600)</td>
                            <td class="val-cuenta" style="color: #8e44ad;">{cartera_contingente:,.2f}</td>
                        </tr>
                        <tr style="background-color: var(--secondary-background-color);">
                            <td class="lbl-cuenta" style="color: #16a34a;">Total Exposición Cartera y Contingente</td>
                            <td class="val-cuenta" style="color: #16a34a;">{total_cartera_contingente:,.2f}</td>
                        </tr>
                        <tr>
                            <td class="lbl-cuenta">Índice de Morosidad Total (Directa)</td>
                            <td class="val-cuenta" style="color: #e67e22;">{mora_val:.2f}%</td>
                        </tr>
                    </table>
                </div>
                """
                st.markdown(html_resumen_cuentas, unsafe_allow_html=True)

            # 1.2 Comparativo Gráfico
            st.markdown("---")
            st.subheader("📊 Comparativo de Estructura de Cartera vs. Subsistema y Sistema Total (%)")

            query_comp = """
                SELECT 
                    e.nombre_entidad as sigla,
                    g.nombre_grupo,
                    f.codigo_cuenta,
                    SUM(f.monto) as monto_bs
                FROM estados_financieros f
                JOIN entidades e ON f.entidad = e.nombre_entidad
                JOIN grupos_asfi g ON e.id_grupo = g.id_grupo
                WHERE f.fecha_corte = :fecha
                  AND e.nombre_entidad NOT LIKE 'TS%%'
                  AND f.codigo_cuenta IN ('131.00', '133.00', '134.00', '135.00', '136.00', '137.00')
                GROUP BY e.nombre_entidad, g.nombre_grupo, f.codigo_cuenta
            """
            df_comp_raw = consultar_db(query_comp, {"fecha": fecha_sel})
            df_comp_raw['monto'] = df_comp_raw['monto_bs'] / factor_conv

            piv_all = df_comp_raw.pivot_table(
                index=['sigla', 'nombre_grupo'], 
                columns='codigo_cuenta', 
                values='monto', 
                aggfunc='sum', 
                fill_value=0
            ).reset_index()

            for c in ['131.00', '133.00', '134.00', '135.00', '136.00', '137.00']:
                if c not in piv_all.columns: piv_all[c] = 0.0

            piv_all['Vigente'] = piv_all['131.00'] + piv_all['135.00']
            piv_all['Vencida'] = piv_all['133.00'] + piv_all['136.00']
            piv_all['Ejecución'] = piv_all['134.00'] + piv_all['137.00']
            piv_all['Total'] = piv_all['Vigente'] + piv_all['Vencida'] + piv_all['Ejecución']

            def armar_porcentajes(df_sub, etiqueta):
                tot_v = df_sub['Vigente'].sum()
                tot_ve = df_sub['Vencida'].sum()
                tot_ej = df_sub['Ejecución'].sum()
                grand_tot = df_sub['Total'].sum()
                if grand_tot == 0: return None
                return {
                    'Ámbito': etiqueta,
                    'Vigente (%)': (tot_v / grand_tot) * 100,
                    'Vencida (%)': (tot_ve / grand_tot) * 100,
                    'Ejecución (%)': (tot_ej / grand_tot) * 100
                }

            ent_row = armar_porcentajes(piv_all[piv_all['nombre_grupo'] == grupo_sel] if es_total_sistema else piv_all[piv_all['sigla'] == sigla_ent], f"{sigla_ent}")
            sub_row = armar_porcentajes(piv_all[piv_all['nombre_grupo'] == grupo_sel], f"Subsistema: {grupo_sel}")
            sis_row = armar_porcentajes(piv_all, "Total Sistema Financiero")

            df_comp_bar = pd.DataFrame([r for r in [ent_row, sub_row, sis_row] if r])

            fig_hbar = px.bar(
                df_comp_bar,
                y='Ámbito',
                x=['Vigente (%)', 'Vencida (%)', 'Ejecución (%)'],
                orientation='h',
                title="Estructura Porcentual Relativa (100%)",
                color_discrete_sequence=['#2ecc71', '#e74c3c', '#e67e22'],
                text_auto='.2f'
            )
            fig_hbar.update_traces(
                textposition='inside',
                textfont=dict(color='white', size=12, family='Arial Black'),
                hovertemplate='<b>%{y}</b><br>%{variable}: %{x:.2f}%<extra></extra>'
            )
            fig_hbar.update_layout(
                barmode='stack', 
                height=320, 
                xaxis=dict(title="Porcentaje (%)", ticksuffix="%", showgrid=False),
                yaxis=dict(title="", gridcolor='rgba(128,128,128,0.2)'),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig_hbar, use_container_width=True)

    # =========================================================================
    # TAB 2: CARTERA REPROGRAMADA Y EVOLUCIÓN
    # =========================================================================
    with tab2:
        st.subheader(f"Análisis Específico de Cartera Reprogramada - {sigla_ent}")

        query_reprog = """
            SELECT 
                e.nombre_entidad as sigla,
                g.nombre_grupo,
                f.codigo_cuenta,
                f.monto as monto_bs
            FROM estados_financieros f
            JOIN entidades e ON f.entidad = e.nombre_entidad
            JOIN grupos_asfi g ON e.id_grupo = g.id_grupo
            WHERE f.fecha_corte = :fecha
              AND f.codigo_cuenta IN ('131.00', '133.00', '134.00', '135.00', '136.00', '137.00')
              AND e.nombre_entidad NOT LIKE 'TS%%'
        """
        df_all_reprog = consultar_db(query_reprog, {"fecha": fecha_sel})

        if not df_all_reprog.empty:
            df_all_reprog['monto'] = df_all_reprog['monto_bs'] / factor_conv
            piv_r = df_all_reprog.pivot_table(index=['sigla', 'nombre_grupo'], columns='codigo_cuenta', values='monto', aggfunc='sum', fill_value=0).reset_index()

            for c in ['131.00', '133.00', '134.00', '135.00', '136.00', '137.00']:
                if c not in piv_r.columns: piv_r[c] = 0.0

            piv_r['Reprog_Vigente'] = piv_r['135.00']
            piv_r['Reprog_Vencida'] = piv_r['136.00']
            piv_r['Reprog_Ejecución'] = piv_r['137.00']
            piv_r['Reprog_Total'] = piv_r['135.00'] + piv_r['136.00'] + piv_r['137.00']
            piv_r['Cartera_Bruta'] = piv_r[['131.00','133.00','134.00','135.00','136.00','137.00']].sum(axis=1)

            ent_r = piv_r[piv_r['nombre_grupo'] == grupo_sel] if es_total_sistema else piv_r[piv_r['sigla'] == sigla_ent]
            
            if not ent_r.empty and ent_r['Cartera_Bruta'].sum() > 0:
                tot_rep_ent = ent_r['Reprog_Total'].sum()
                mora_rep_ent = ent_r['Reprog_Vencida'].sum() + ent_r['Reprog_Ejecución'].sum()
                indicador_mora_reprog = (mora_rep_ent / tot_rep_ent * 100) if tot_rep_ent > 0 else 0

                c_rep1, c_rep2 = st.columns([1.1, 0.9])

                with c_rep1:
                    st.markdown("#### Composición y Morosidad de Cartera Reprogramada")
                    st.caption("📌 *Los porcentajes indican la proporción interna y la morosidad asociada a cada segmento reprogramado.*")
                    
                    df_pie_rep = pd.DataFrame({
                        'Segmento': ['Reprog. Vigente (135.00)', 'Reprog. Vencida (136.00)', 'Reprog. Ejecución (137.00)'],
                        'Monto': [ent_r['Reprog_Vigente'].sum(), ent_r['Reprog_Vencida'].sum(), ent_r['Reprog_Ejecución'].sum()]
                    })
                    fig_pie_rep = px.pie(
                        df_pie_rep,
                        names='Segmento',
                        values='Monto',
                        color='Segmento',
                        color_discrete_sequence=['#2ecc71', '#e74c3c', '#d35400'],
                        title=f"Morosidad Reprogramada Total: {indicador_mora_reprog:.2f}%"
                    )
                    fig_pie_rep.update_traces(
                        textinfo='percent+label',
                        hovertemplate='<b>%{label}</b><br>Monto: %{value:,.2f}<br>Porcentaje: %{percent}<extra></extra>'
                    )
                    fig_pie_rep.update_layout(
                        height=410, 
                        showlegend=False,
                        paper_bgcolor='rgba(0,0,0,0)',
                        plot_bgcolor='rgba(0,0,0,0)'
                    )
                    st.plotly_chart(fig_pie_rep, use_container_width=True)

                with c_rep2:
                    st.markdown("#### Ratio de Reprogramación sobre Cartera Bruta")
                    sub_r = piv_r[piv_r['nombre_grupo'] == grupo_sel]
                    
                    pct_ent = (ent_r['Reprog_Total'].sum() / ent_r['Cartera_Bruta'].sum()) * 100
                    pct_sub = (sub_r['Reprog_Total'].sum() / sub_r['Cartera_Bruta'].sum()) * 100 if sub_r['Cartera_Bruta'].sum() > 0 else 0
                    pct_sis = (piv_r['Reprog_Total'].sum() / piv_r['Cartera_Bruta'].sum()) * 100 if piv_r['Cartera_Bruta'].sum() > 0 else 0

                    df_comp_rep = pd.DataFrame({
                        'Ámbito': [f'Selección: {sigla_ent}', f'Subsistema: {grupo_sel}', 'Total Sistema'],
                        '% Reprogramado': [pct_ent, pct_sub, pct_sis]
                    })

                    fig_bar_rep = px.bar(
                        df_comp_rep,
                        x='Ámbito',
                        y='% Reprogramado',
                        text_auto='.2f',
                        color='Ámbito',
                        color_discrete_sequence=['#3498db', '#95a5a6', '#7f8c8d']
                    )
                    fig_bar_rep.update_traces(
                        texttemplate='%{y:.2f}%', 
                        textposition='outside'
                    )
                    fig_bar_rep.update_layout(
                        height=410, 
                        showlegend=False, 
                        yaxis=dict(ticksuffix='%', gridcolor='rgba(128,128,128,0.2)'),
                        xaxis=dict(showgrid=False),
                        paper_bgcolor='rgba(0,0,0,0)',
                        plot_bgcolor='rgba(0,0,0,0)'
                    )
                    st.plotly_chart(fig_bar_rep, use_container_width=True)

        st.markdown("---")
        st.subheader(f"📊 Evolución de la Cartera Reprogramada ({nombre_moneda}) - Últimos 18 Cortes")

        if es_total_sistema:
            query_18_reprog = """
                WITH ultimos_cortes AS (
                    SELECT DISTINCT fecha_corte 
                    FROM estados_financieros 
                    ORDER BY fecha_corte DESC 
                    LIMIT 18
                )
                SELECT 
                    f.fecha_corte,
                    SUM(f.monto) as monto_bs
                FROM estados_financieros f
                JOIN entidades e ON f.entidad = e.nombre_entidad
                WHERE e.id_grupo = :id_grupo
                  AND e.nombre_entidad NOT LIKE 'TS%%'
                  AND f.codigo_cuenta IN ('135.00', '136.00', '137.00')
                  AND f.fecha_corte IN (SELECT fecha_corte FROM ultimos_cortes)
                GROUP BY f.fecha_corte
                ORDER BY f.fecha_corte ASC
            """
            params_hist = {"id_grupo": id_g}
        else:
            query_18_reprog = """
                WITH ultimos_cortes AS (
                    SELECT DISTINCT fecha_corte 
                    FROM estados_financieros 
                    ORDER BY fecha_corte DESC 
                    LIMIT 18
                )
                SELECT 
                    fecha_corte,
                    SUM(monto) as monto_bs
                FROM estados_financieros
                WHERE entidad = :entidad
                  AND codigo_cuenta IN ('135.00', '136.00', '137.00')
                  AND fecha_corte IN (SELECT fecha_corte FROM ultimos_cortes)
                GROUP BY fecha_corte
                ORDER BY fecha_corte ASC
            """
            params_hist = {"entidad": sigla_ent}

        df_hist_rep = consultar_db(query_18_reprog, params_hist)

        if not df_hist_rep.empty:
            df_hist_rep['monto'] = df_hist_rep['monto_bs'] / factor_conv
            df_hist_rep['fecha_str'] = df_hist_rep['fecha_corte'].astype(str)

            fig_bar_hist = px.bar(
                df_hist_rep,
                x='fecha_str',
                y='monto',
                text_auto=',.2f',
                title=f"Saldo Reprogramado - {sigla_ent}",
                labels={'fecha_str': 'Fecha de Corte', 'monto': f'Monto ({nombre_moneda})'},
                color_discrete_sequence=['#8e44ad']
            )
            fig_bar_hist.update_traces(textposition='outside')
            fig_bar_hist.update_layout(
                height=380, 
                margin=dict(t=40, b=10), 
                xaxis=dict(showgrid=False),
                yaxis=dict(gridcolor='rgba(128,128,128,0.2)'),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig_bar_hist, use_container_width=True)

    # =========================================================================
    # TAB 3: ÍNDICE DE MOROSIDAD
    # =========================================================================
    with tab3:
        st.subheader("Evolución del Índice de Morosidad (Últimos 18 Cortes)")

        query_18cortes = """
            WITH ultimos_cortes AS (
                SELECT DISTINCT fecha_corte 
                FROM indicadores_financieros 
                ORDER BY fecha_corte DESC 
                LIMIT 18
            )
            SELECT 
                i.fecha_corte,
                e.nombre_entidad as sigla,
                g.nombre_grupo,
                i.valor
            FROM indicadores_financieros i
            JOIN entidades e ON i.id_entidad = e.id_entidad
            JOIN grupos_asfi g ON e.id_grupo = g.id_grupo
            WHERE TRIM(i.codigo_indicador) = 'Cartera Vencida Total+Ejecución Total /Cartera'
              AND i.fecha_corte IN (SELECT fecha_corte FROM ultimos_cortes)
              AND e.nombre_entidad NOT LIKE 'TS%%'
            ORDER BY i.fecha_corte ASC
        """
        df_18 = consultar_db(query_18cortes)

        if df_18.empty:
            st.info("No se dispone de datos de morosidad para los últimos 18 cortes.")
        else:
            df_18['mora_pct'] = df_18['valor'].apply(lambda x: float(x) * 100 if abs(float(x)) <= 1 else float(x))
            df_18['fecha_corte_str'] = df_18['fecha_corte'].astype(str)

            sub_18 = df_18[df_18['nombre_grupo'] == grupo_sel].groupby('fecha_corte_str')['mora_pct'].mean().reset_index()
            sis_18 = df_18.groupby('fecha_corte_str')['mora_pct'].mean().reset_index()

            if es_total_sistema:
                ent_18 = sub_18.copy()
                ent_18['sigla'] = sigla_ent
            else:
                ent_18 = df_18[df_18['sigla'] == sigla_ent].sort_values('fecha_corte')

            fig_18 = go.Figure()

            fig_18.add_trace(go.Scatter(
                x=ent_18['fecha_corte_str'],
                y=ent_18['mora_pct'],
                mode='lines+markers+text',
                name=f'Indicador de Morosidad ({sigla_ent})',
                text=[f"{v:.2f}%" for v in ent_18['mora_pct']],
                textposition="top center",
                textfont=dict(size=10, color='#1f77b4'),
                line=dict(color='#1f77b4', width=3),
                marker=dict(size=8)
            ))

            fig_18.add_trace(go.Scatter(
                x=sub_18['fecha_corte_str'],
                y=sub_18['mora_pct'],
                mode='lines+markers',
                name=f'Prom. {grupo_sel}',
                line=dict(color='#ff7f0e', width=2, dash='dot')
            ))

            fig_18.add_trace(go.Scatter(
                x=sis_18['fecha_corte_str'],
                y=sis_18['mora_pct'],
                mode='lines+markers',
                name='Prom. Sistema',
                line=dict(color='#2ca02c', width=2, dash='dash')
            ))

            fig_18.update_layout(
                title=f"Evolución del Indicador de Morosidad (%) - {sigla_ent} vs. Mercado",
                xaxis_title="Fecha de Corte",
                yaxis_title="Indicador de Morosidad (%)",
                height=420,
                margin=dict(t=50, b=40, l=10, r=10),
                xaxis=dict(showgrid=False),
                yaxis=dict(ticksuffix='%', gridcolor='rgba(128,128,128,0.2)'),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)'
            )

            st.plotly_chart(fig_18, use_container_width=True)

            st.markdown("---")
            st.subheader("📋 Tabla de Datos Históricos de Morosidad (%)")

            df_tabla_mora = ent_18[['fecha_corte_str', 'mora_pct']].rename(columns={'fecha_corte_str': 'Fecha Corte', 'mora_pct': f'{sigla_ent} (%)'})
            df_tabla_mora = df_tabla_mora.merge(sub_18.rename(columns={'fecha_corte_str': 'Fecha Corte', 'mora_pct': f'Subsistema ({grupo_sel}) (%)'}), on='Fecha Corte', how='left')
            df_tabla_mora = df_tabla_mora.merge(sis_18.rename(columns={'fecha_corte_str': 'Fecha Corte', 'mora_pct': 'Total Sistema (%)'}), on='Fecha Corte', how='left')

            st.dataframe(
                df_tabla_mora.style.format({
                    f'{sigla_ent} (%)': '{:.2f}%',
                    f'Subsistema ({grupo_sel}) (%)': '{:.2f}%',
                    'Total Sistema (%)': '{:.2f}%'
                }),
                use_container_width=True,
                hide_index=True
            )

    # =========================================================================
    # TAB 4: INDICADORES DE CARTERA
    # =========================================================================
    with tab4:
        st.subheader("📊 Indicadores de Calidad de Cartera (Corte Seleccionado)")

        if es_total_sistema:
            query_ind_cartera = """
                SELECT 
                    i.codigo_indicador,
                    p.grupo_indicador,
                    p.notas_aclaratorias,
                    p.orden,
                    AVG(i.valor) as valor
                FROM indicadores_financieros i
                JOIN entidades e ON i.id_entidad = e.id_entidad
                LEFT JOIN plan_indicadores p ON i.codigo_indicador = p.codigo_indicador
                WHERE e.id_grupo = :id_grupo
                  AND e.nombre_entidad NOT LIKE 'TS%%'
                  AND i.fecha_corte = :fecha
                  AND UPPER(TRIM(p.grupo_indicador)) LIKE 'CALIDAD DE CARTERA%'
                GROUP BY i.codigo_indicador, p.grupo_indicador, p.notas_aclaratorias, p.orden
                ORDER BY p.orden
            """
            params_ind = {"id_grupo": id_g, "fecha": fecha_sel}
        else:
            query_ind_cartera = """
                SELECT 
                    i.codigo_indicador,
                    p.grupo_indicador,
                    p.notas_aclaratorias,
                    p.orden,
                    i.valor
                FROM indicadores_financieros i
                LEFT JOIN plan_indicadores p ON i.codigo_indicador = p.codigo_indicador
                WHERE i.id_entidad = :id_entidad
                  AND i.fecha_corte = :fecha
                  AND UPPER(TRIM(p.grupo_indicador)) LIKE 'CALIDAD DE CARTERA%'
                ORDER BY p.orden
            """
            params_ind = {"id_entidad": id_entidad_sel, "fecha": fecha_sel}

        df_ind_c = consultar_db(query_ind_cartera, params_ind)

        if df_ind_c.empty:
            st.warning("No se encontraron indicadores de Calidad de Cartera parametrizados para la selección en este corte.")
        else:
            df_ind_c['valor_pct'] = df_ind_c['valor'].apply(lambda x: float(x) * 100 if abs(float(x)) <= 1 else float(x))
            df_ind_c['Indicador'] = df_ind_c['codigo_indicador'].astype(str).str.strip()

            fig_ind_bar = px.bar(
                df_ind_c,
                y='Indicador',
                x='valor_pct',
                orientation='h',
                title=f"Valores de Calidad de Cartera (%) - {sigla_ent}",
                text_auto='.2f',
                color='valor_pct',
                color_continuous_scale='Blues',
                labels={'valor_pct': 'Valor (%)', 'Indicador': 'Indicador'}
            )
            fig_ind_bar.update_traces(
                texttemplate='%{x:.2f}%', 
                textposition='outside'
            )
            fig_ind_bar.update_layout(
                height=max(350, len(df_ind_c) * 45), 
                coloraxis_showscale=False,
                xaxis=dict(ticksuffix='%', showgrid=False),
                yaxis=dict(gridcolor='rgba(128,128,128,0.2)'),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig_ind_bar, use_container_width=True)

            st.markdown("---")
            st.markdown("##### 📋 Detalle de Notas y Descripción")
            
            rows_html_list = []
            for _, r in df_ind_c.iterrows():
                nombre_ind = str(r["codigo_indicador"]).strip()
                val_fmt = f"{r['valor_pct']:,.2f}%"
                nota = str(r["notas_aclaratorias"]) if pd.notna(r["notas_aclaratorias"]) else ""

                rows_html_list.append(
                    f'<tr>'
                    f'<td class="cal-col-ind"><b>{nombre_ind}</b></td>'
                    f'<td class="cal-col-val">{val_fmt}</td>'
                    f'<td class="cal-col-nota">{nota}</td>'
                    f'</tr>'
                )

            rows_cal_html = "".join(rows_html_list)

            st.markdown("""
            <style>
                .cal-table-container {
                    border: 2px solid var(--border-color);
                    border-radius: 8px;
                    overflow-x: auto;
                    background-color: var(--background-color);
                    box-shadow: 0 4px 16px rgba(0,0,0,0.12);
                    margin-bottom: 1rem;
                }
                .cal-table {
                    width: 100%;
                    border-collapse: collapse;
                    font-family: inherit;
                }
                .cal-table thead th {
                    background-color: var(--secondary-background-color);
                    color: var(--text-color);
                    font-size: 11px;
                    font-weight: 700;
                    padding: 9px;
                    border-bottom: 2px solid var(--border-color);
                    text-transform: uppercase;
                }
                .cal-col-ind {
                    width: 35%;
                    padding: 7px 10px;
                    font-size: 11px;
                    color: var(--text-color);
                    border-bottom: 1px solid var(--border-color);
                }
                .cal-col-val {
                    width: 20%;
                    text-align: right;
                    padding: 7px 10px;
                    font-size: 11px;
                    font-family: Consolas, monospace;
                    font-weight: bold;
                    color: #2563eb;
                    border-bottom: 1px solid var(--border-color);
                    border-left: 1px solid var(--border-color);
                }
                .cal-col-nota {
                    width: 45%;
                    padding: 7px 10px;
                    font-size: 11px;
                    color: var(--text-color);
                    opacity: 0.8;
                    border-bottom: 1px solid var(--border-color);
                    border-left: 1px solid var(--border-color);
                }
            </style>
            """, unsafe_allow_html=True)

            html_calidad = f'<div class="cal-table-container"><table class="cal-table"><thead><tr><th style="width:35%; text-align:left;">INDICADOR</th><th style="width:20%; text-align:right;">VALOR</th><th style="width:45%; text-align:left;">NOTAS ACLARATORIAS</th></tr></thead><tbody>{rows_cal_html}</tbody></table></div>'
            st.markdown(html_calidad, unsafe_allow_html=True)

    # --- 3. TEXTO DE DESCARGO ---
    st.markdown("---")
    st.caption(
        "📌 **Nota de Descargo:** Los datos mostrados proceden de los Boletines Estadísticos Oficiales de la ASFI "
        "(información pública). Esta información se difunde con fines estrictamente analíticos e informativos; "
        "no constituye una calificación de riesgo, opinión de auditoría, ni recomendación de inversión. "
        "El análisis de riesgo es multidimensional y ningún indicador o cuenta aislados determina la salud o "
        "solvencia de una entidad financiera."
    )

if __name__ == "__main__":
    mostrar_analizador_cartera()