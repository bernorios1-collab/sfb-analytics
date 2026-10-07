# ==============================================================================
# FUNCIONALIDAD DEL ARCHIVO (comportamiento_indicadores.py):
# Este script implementa una interfaz interactiva en Streamlit para analizar la 
# evolución temporal y las tendencias históricas de los indicadores financieros.
# Permite visualizar evoluciones clave mediante gráficos de líneas, explorar la 
# matriz de indicadores parametrizados agrupados por categoría y exportar las 
# series temporales consolidadas a Excel.
# ==============================================================================

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import io
from sqlalchemy import text
from config_db import obtener_engine
from scrapers.indicadores_bcb import obtener_indicadores_bcb

# Orden oficial de publicación de grupos según plantilla pública ASFI
ORDEN_GRUPOS_ASFI = [
    "ESTRUCTURA DE ACTIVOS",
    "ESTRUCTURA DE PASIVOS",
    "ESTRUCTURA DE OBLIGACIONES",
    "CALIDAD DE CARTERA",
    "LIQUIDEZ",
    "SOLVENCIA",
    "ESTRUCTURA FINANCIERA",
    "RENTABILIDAD",
    "RESULTADOS",
    "INGRESOS Y GASTOS FINANCIEROS",
    "EFICIENCIA ADMINISTRATIVA",
    "RATIOS DE EFICIENCIA",
    "ESTRUCTURA DE GASTOS DE ADMINISTRACIÓN",
    "CÁLCULO SPREAD EFECTIVO",
    "UTILIZACIÓN DEL SPREAD EFECTIVO"
]

def obtener_llave_orden_asfi(nombre_grupo):
    clean_g = str(nombre_grupo).upper().split('(')[0].strip()
    for idx, ref in enumerate(ORDEN_GRUPOS_ASFI):
        if ref in clean_g or clean_g in ref:
            return idx
    return 999

# --- FUNCIONES TÉCNICAS ---
@st.cache_data(ttl=600)
def consultar_db(query, params=None):
    engine = obtener_engine()
    try:
        return pd.read_sql_query(text(query), engine, params=params)
    except Exception as e:
        st.error(f"Error técnico: {e}")
        return pd.DataFrame()

def mostrar_comportamiento_indicadores():
    st.header("📈 Comportamiento de Indicadores Financieros")
    
    dict_indicadores = obtener_indicadores_bcb()

    # --- 1. CONFIGURACIÓN DE CONSULTA ---
    with st.container(border=True):
        c1, c2, c3, c4, c5 = st.columns([0.4, 0.6, 1.0, 0.8, 0.8])
        
        df_years = consultar_db("""
            SELECT DISTINCT EXTRACT(YEAR FROM fecha_corte)::int as anio 
            FROM indicadores_financieros 
            ORDER BY anio DESC
        """)
        if df_years.empty:
            st.warning("No hay datos de indicadores disponibles en la Base de Datos.")
            return

        anio_sel = c1.selectbox("Año", df_years['anio'].tolist(), key="sb_ind_anio")
        
        df_f = consultar_db("""
            SELECT DISTINCT fecha_corte 
            FROM indicadores_financieros 
            WHERE EXTRACT(YEAR FROM fecha_corte) = :anio 
            ORDER BY fecha_corte DESC
        """, {"anio": anio_sel})
        
        fecha_sel_input = c2.selectbox("Corte", df_f['fecha_corte'].astype(str).tolist(), key="sb_ind_corte")
        
        moneda_sel = c3.selectbox("💰 Moneda", list(dict_indicadores.keys()), key="sb_ind_moneda")
        frecuencia = c4.selectbox("🔄 Frecuencia", ["Mensual", "Trimestral", "Semestral", "Anual"], key="sb_ind_frec")
        periodos = c5.number_input("🔢 Periodos", min_value=1, max_value=24, value=6, key="sb_ind_periodos")

        f1, f2 = st.columns([1.3, 1.7])
        df_grupos = consultar_db("SELECT id_grupo, nombre_grupo FROM grupos_asfi ORDER BY id_grupo ASC")
        grupo_sel = f1.selectbox("📂 Grupo", options=df_grupos['nombre_grupo'].tolist(), key="sb_ind_grupo")
        id_g = int(df_grupos[df_grupos['nombre_grupo'] == grupo_sel]['id_grupo'].values[0])
        
        # Ordenamos para que la entidad Total Sistema (TS***) aparezca al principio
        df_ent = consultar_db("""
            SELECT id_entidad, nombre_entidad as sigla, nombre_completo 
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
            
        entidad_display = f2.selectbox("🏛️ Entidad Financiera", options=list(opciones_ent.keys()), key="sb_ind_entidad")
        sigla_sel = opciones_ent[entidad_display]["sigla"]
        id_entidad_sel = opciones_ent[entidad_display]["id_entidad"]
        
        if len(dict_indicadores) == 1:
            st.caption("⚠️ No existe conectividad con BCB (Muestra únicamente datos expresados nominalmente)")

    # --- 2. LÓGICA DE TEMPORALIDAD FILTRADA POR ENTIDAD ---
    map_m = {"Mensual": 1, "Trimestral": 3, "Semestral": 6, "Anual": 12}
    salto = map_m[frecuencia]
    
    # Consultamos ÚNICAMENTE las fechas donde la entidad seleccionada tiene indicadores cargados
    df_f_entidad = consultar_db("""
        SELECT DISTINCT fecha_corte 
        FROM indicadores_financieros 
        WHERE id_entidad = :id_entidad
        ORDER BY fecha_corte DESC
    """, {"id_entidad": id_entidad_sel})
    
    lista_f = df_f_entidad['fecha_corte'].astype(str).tolist()
    
    try:
        idx = lista_f.index(fecha_sel_input)
        fechas_req = lista_f[idx : idx + (periodos * salto) : salto]
    except:
        fechas_req = [fecha_sel_input]

    if not fechas_req:
        st.info("No se encontraron fechas de corte válidas para la entidad.")
        return

    query = """
        SELECT 
            i.fecha_corte,
            i.codigo_indicador,
            p.grupo_indicador,
            p.notas_aclaratorias,
            p.orden,
            i.valor
        FROM indicadores_financieros i
        LEFT JOIN plan_indicadores p ON i.codigo_indicador = p.codigo_indicador
        WHERE i.id_entidad = :id_entidad AND i.fecha_corte IN :fechas
        ORDER BY p.orden ASC, i.fecha_corte ASC
    """
    df_raw = consultar_db(query, {"id_entidad": id_entidad_sel, "fechas": tuple(fechas_req)})

    if df_raw.empty:
        st.info("No se encontraron registros de indicadores para el periodo y entidad seleccionados.")
        return

    df_raw['fecha_dt'] = pd.to_datetime(df_raw['fecha_corte'])
    df_raw['fecha_label'] = df_raw['fecha_dt'].dt.strftime('%b %Y')
    orden_fechas_asc = sorted(df_raw['fecha_label'].unique(), key=lambda x: pd.to_datetime(x, format='%b %Y'))

    # --- 3. GRÁFICOS REPRESENTATIVOS DE TENDENCIA ---
    st.markdown("### Resumen de Tendencias Clave")
    
    def obtener_serie_indicador(patrones_nombre):
        if isinstance(patrones_nombre, str):
            patrones_nombre = [patrones_nombre]
            
        for patron in patrones_nombre:
            mask = df_raw['codigo_indicador'].str.upper().str.contains(patron.upper(), na=False)
            sub = df_raw[mask].sort_values('fecha_dt')
            if not sub.empty:
                cod_ref = sub['codigo_indicador'].iloc[0]
                return df_raw[df_raw['codigo_indicador'] == cod_ref].set_index('fecha_label')['valor']
        return pd.Series(dtype=float)

    roa = obtener_serie_indicador(["ROA", "UTILIDAD NETA/ACTIVO"])
    roe = obtener_serie_indicador(["ROE", "UTILIDAD NETA/PATRIMONIO"])
    
    mora = obtener_serie_indicador([
        "Cartera Vencida Total+Ejecución Total /Cartera",
        "CARTERA VENCIDA",
        "EJECUCION TOTAL",
        "MOROSA"
    ])

    plotly_layout_theme = dict(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(showgrid=False, type='category'),
        yaxis=dict(gridcolor='rgba(128,128,128,0.2)'),
        margin=dict(t=35, b=10, l=10, r=10)
    )

    g1, g2 = st.columns(2)
    with g1:
        fig1 = go.Figure()
        if not roa.empty:
            v_roa = (roa.reindex(orden_fechas_asc)*100).values if roa.abs().max() <= 1 else roa.reindex(orden_fechas_asc).values
            fig1.add_trace(go.Scatter(
                x=orden_fechas_asc, 
                y=v_roa, 
                name='ROA (%)', 
                mode='lines+markers+text', 
                text=[f"{v:.2f}%" for v in v_roa],
                textposition='top center',
                line=dict(color='#2ca02c', width=2)
            ))
        if not roe.empty:
            v_roe = (roe.reindex(orden_fechas_asc)*100).values if roe.abs().max() <= 1 else roe.reindex(orden_fechas_asc).values
            fig1.add_trace(go.Scatter(
                x=orden_fechas_asc, 
                y=v_roe, 
                name='ROE (%)', 
                mode='lines+markers+text', 
                text=[f"{v:.2f}%" for v in v_roe],
                textposition='top center',
                line=dict(color='#1f77b4', width=2)
            ))
        fig1.update_layout(
            height=290, 
            title="Rentabilidad (ROA / ROE %)", 
            hovermode="x unified",
            **plotly_layout_theme
        )
        st.plotly_chart(fig1, use_container_width=True)

    with g2:
        fig2 = go.Figure()
        if not mora.empty:
            y_mora = (mora.reindex(orden_fechas_asc)*100).values if (mora.abs().max() <= 1) else mora.reindex(orden_fechas_asc).values
            fig2.add_trace(go.Scatter(
                x=orden_fechas_asc, 
                y=y_mora, 
                name='Mora (%)', 
                mode='lines+markers+text', 
                text=[f"{v:.2f}%" for v in y_mora],
                textposition='top center',
                line=dict(color='#d62728', width=2)
            ))
        
        fig2.update_layout(
            height=290, 
            title="Calidad de Cartera / Mora (%)", 
            hovermode="x unified",
            **plotly_layout_theme
        )
        st.plotly_chart(fig2, use_container_width=True)

    # --- 4. TABLA PIVOTADA CON SECTORES ORDENADOS SEGÚN LA PLANTILLA OFICIAL ASFI ---
    st.markdown("---")
    
    df_plan = consultar_db("SELECT codigo_indicador, grupo_indicador, orden FROM plan_indicadores ORDER BY orden ASC")
    if df_plan.empty:
        st.warning("No se encontró parametrización en plan_indicadores.")
        return

    df_pivot_val = df_raw.pivot_table(index='codigo_indicador', columns='fecha_label', values='valor', aggfunc='first').reset_index()
    
    df_matriz = pd.merge(df_plan, df_pivot_val, on='codigo_indicador', how='inner').sort_values('orden', ascending=True)
    
    cols_fechas_desc = sorted([c for c in df_matriz.columns if c not in ['codigo_indicador', 'grupo_indicador', 'orden']], 
                              key=lambda x: pd.to_datetime(x, format='%b %Y'), reverse=True)

    # Agrupación por nombre de grupo
    grupos_dic = {}
    for _, r in df_matriz.iterrows():
        g_nom = str(r['grupo_indicador']).strip()
        if g_nom not in grupos_dic:
            grupos_dic[g_nom] = []
        grupos_dic[g_nom].append(r)

    # Ordenamiento de los grupos aplicando la secuencia oficial de la ASFI
    grupos_ordenados = sorted(grupos_dic.keys(), key=obtener_llave_orden_asfi)

    rows_list = []
    total_cols = len(cols_fechas_desc) + 1

    for grupo_nom in grupos_ordenados:
        lista_filas = grupos_dic[grupo_nom]
        rows_list.append(f'<tr><td colspan="{total_cols}" class="comp-grp-header">{grupo_nom}</td></tr>')
        
        for r_ind in lista_filas:
            ind_nombre = r_ind['codigo_indicador']
            
            val_cells_list = []
            for f_col in cols_fechas_desc:
                val = r_ind[f_col]
                if pd.notna(val):
                    val_num = float(val)
                    if abs(val_num) <= 1 and val_num != 0:
                        val_fmt = f"{val_num * 100:,.2f}%"
                    else:
                        val_fmt = f"{val_num:,.4f}"
                else:
                    val_fmt = "-"
                
                val_cells_list.append(f'<td class="comp-col-val">{val_fmt}</td>')

            val_cells = "".join(val_cells_list)
            rows_list.append(f'<tr><td class="comp-col-ind">{ind_nombre}</td>{val_cells}</tr>')

    rows_html = "".join(rows_list)
    th_fechas = "".join([f'<th style="text-align:right; min-width:95px;">{f_col}</th>' for f_col in cols_fechas_desc])

    st.markdown("""
    <style>
        .comp-container {
            max-height: 520px;
            overflow-y: auto;
            overflow-x: auto;
            border: 2px solid var(--border-color);
            border-radius: 8px;
            margin-bottom: 1rem;
            background-color: var(--background-color);
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
        }
        .comp-table {
            width: 100%;
            border-collapse: collapse;
            font-family: inherit;
        }
        .comp-table thead th {
            position: sticky;
            top: 0;
            z-index: 100;
            background-color: var(--secondary-background-color);
            color: var(--text-color);
            font-size: 11px;
            font-weight: 700;
            padding: 8px 10px;
            border-bottom: 2px solid var(--border-color);
            border-left: 1px solid var(--border-color);
            text-transform: uppercase;
        }
        .comp-grp-header {
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
        .comp-col-ind {
            width: 30%;
            padding: 6px 10px;
            font-size: 11px;
            color: var(--text-color);
            background-color: var(--background-color);
            border-bottom: 1px solid var(--border-color);
            border-right: 1px solid var(--border-color);
            white-space: nowrap;
        }
        .comp-col-val {
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
        .comp-table tbody tr:hover td {
            background-color: var(--secondary-background-color) !important;
            opacity: 0.95;
        }
    </style>
    """, unsafe_allow_html=True)

    html_table = f'<div class="comp-container"><table class="comp-table"><thead><tr><th style="width:30%; text-align:left;">INDICADOR FINANCIERO</th>{th_fechas}</tr></thead><tbody>{rows_html}</tbody></table></div>'
    
    st.markdown(html_table, unsafe_allow_html=True)

    # --- 5. EXPORTACIÓN A EXCEL ---
    df_export = df_matriz[['grupo_indicador', 'codigo_indicador'] + cols_fechas_desc].copy()
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as wr:
        df_export.to_excel(wr, index=False, sheet_name='Historico_Indicadores')
    
    _, col_boton = st.columns([3, 1])
    with col_boton:
        st.download_button(
            "📥 Exportar Excel",
            buf.getvalue(),
            f"comportamiento_indicadores_{sigla_sel}.xlsx",
            use_container_width=True
        )

if __name__ == "__main__":
    mostrar_comportamiento_indicadores()