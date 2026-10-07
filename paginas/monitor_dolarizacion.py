# ==============================================================================
# MÓDULO: paginas/monitor_dolarizacion.py
# Monitor de Dolarización, Estructura Multimoneda y Riesgo Cambiario
# ==============================================================================

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from config_db import obtener_engine
from scrapers.indicadores_bcb import obtener_indicadores_bcb

@st.cache_data(ttl=600)
def consultar_db(query, params=None):
    engine = obtener_engine()
    try:
        return pd.read_sql_query(query, engine, params=params)
    except Exception as e:
        st.error(f"Error técnico: {e}")
        return pd.DataFrame()

def mostrar_monitor_dolarizacion():
    st.header("💱 Monitor de Dolarización y Riesgo Cambiario")
    
    dict_indicadores = obtener_indicadores_bcb()

    # --- 1. FILTROS Y CONFIGURACIÓN ---
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([0.6, 0.8, 1.2, 1.0])
        
        df_years = consultar_db("SELECT DISTINCT EXTRACT(YEAR FROM fecha_corte)::int as anio FROM estados_financieros_moneda ORDER BY anio DESC")
        if df_years.empty:
            st.warning("No hay datos cargados en Estados Financieros por Moneda.")
            return

        anio_sel = c1.selectbox("Año", df_years['anio'].tolist())
        df_f = consultar_db("SELECT DISTINCT fecha_corte FROM estados_financieros_moneda WHERE EXTRACT(YEAR FROM fecha_corte) = %s ORDER BY fecha_corte DESC", (anio_sel,))
        fecha_sel = c2.selectbox("Corte de Análisis", df_f['fecha_corte'].astype(str).tolist())
        
        df_grupos = consultar_db("SELECT id_grupo, nombre_grupo FROM grupos_asfi ORDER BY id_grupo ASC")
        grupo_sel = c3.selectbox("📂 Grupo ASFI", options=df_grupos['nombre_grupo'].tolist())
        id_g = int(df_grupos[df_grupos['nombre_grupo'] == grupo_sel]['id_grupo'].values[0])
        
        moneda_sel = c4.selectbox("💰 Expresado en", list(dict_indicadores.keys()))
        factor = dict_indicadores[moneda_sel]

    # --- 2. EXTRACCIÓN DE DATOS DE LA FECHA DE CORTE ---
    query_corte = """
        SELECT 
            f.codigo_cuenta as cod,
            p.descripcion_cuenta as desc_cta,
            f.monto_mn,
            f.monto_me,
            f.monto_mnmv,
            f.monto_mnufv,
            f.monto_total
        FROM estados_financieros_moneda f
        JOIN plan_cuentas_moneda p ON f.codigo_cuenta = p.codigo_cuenta
        WHERE f.id_grupo = %s AND f.fecha_corte = %s
    """
    df_corte = consultar_db(query_corte, (id_g, fecha_sel))
    if df_corte.empty:
        st.info("No hay datos cargados para la combinación seleccionada.")
        return

    # Aplicar conversión de moneda
    for col in ['monto_mn', 'monto_me', 'monto_mnmv', 'monto_mnufv', 'monto_total']:
        df_corte[col] = df_corte[col] / factor

    # --- 3. CÁLCULO DE METRICAS DE DOLARIZACIÓN ---
    def get_row(cod_cuenta):
        res = df_corte[df_corte['cod'] == cod_cuenta]
        if not res.empty:
            return res.iloc[0]
        return pd.Series({'monto_mn': 0, 'monto_me': 0, 'monto_mnmv': 0, 'monto_mnufv': 0, 'monto_total': 0})

    act = get_row('100.00')
    cart = get_row('130.00')
    pas = get_row('200.00')
    obl = get_row('210.00')
    dpf = get_row('213.00')

    # Ratios porcentuales
    pct_cart_me = (cart['monto_me'] / cart['monto_total'] * 100) if cart['monto_total'] > 0 else 0
    pct_obl_me = (obl['monto_me'] / obl['monto_total'] * 100) if obl['monto_total'] > 0 else 0
    pct_dpf_ufv = (dpf['monto_mnufv'] / dpf['monto_total'] * 100) if dpf['monto_total'] > 0 else 0
    gap_me = act['monto_me'] - pas['monto_me']

    # --- 4. TARJETAS DE INDICADORES CLAVE ---
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Dolarización de Cartera", f"{pct_cart_me:.2f}%")
    k2.metric("Dolarización de Captaciones", f"{pct_obl_me:.2f}%")
    k3.metric("Indexación UFV en DPFs", f"{pct_dpf_ufv:.2f}%")
    k4.metric("Posición Neta ME (FX Gap)", f"{gap_me:,.2f}")

    st.markdown("---")

    # --- 5. GRÁFICOS DE ESTRUCTURA Y DOLARIZACIÓN ---
    m1, m2 = st.columns(2)
    
    with m1:
        st.subheader("📊 Estructura de Moneda en Activos y Pasivos")
        data_comp = [
            {'Categoría': 'Activo Total (100.00)', 'MN': act['monto_mn'], 'ME': act['monto_me'], 'UFV/MNMV': act['monto_mnufv'] + act['monto_mnmv']},
            {'Categoría': 'Cartera (130.00)', 'MN': cart['monto_mn'], 'ME': cart['monto_me'], 'UFV/MNMV': cart['monto_mnufv'] + cart['monto_mnmv']},
            {'Categoría': 'Pasivo Total (200.00)', 'MN': pas['monto_mn'], 'ME': pas['monto_me'], 'UFV/MNMV': pas['monto_mnufv'] + pas['monto_mnmv']},
            {'Categoría': 'Obligaciones Público (210.00)', 'MN': obl['monto_mn'], 'ME': obl['monto_me'], 'UFV/MNMV': obl['monto_mnufv'] + obl['monto_mnmv']}
        ]
        df_comp = pd.DataFrame(data_comp)
        
        fig_comp = go.Figure()
        fig_comp.add_trace(go.Bar(y=df_comp['Categoría'], x=df_comp['MN'], name='Moneda Nacional (MN)', orientation='h', marker_color='#2ca02c'))
        fig_comp.add_trace(go.Bar(y=df_comp['Categoría'], x=df_comp['ME'], name='Moneda Extranjera (ME)', orientation='h', marker_color='#d62728'))
        fig_comp.add_trace(go.Bar(y=df_comp['Categoría'], x=df_comp['UFV/MNMV'], name='Indexado UFV/MNMV', orientation='h', marker_color='#ff7f0e'))
        fig_comp.update_layout(barmode='stack', height=320, margin=dict(t=20, b=10, l=10, r=10), legend=dict(orientation="h", y=1.15))
        st.plotly_chart(fig_comp, use_container_width=True)

    with m2:
        st.subheader("📈 Tendencia Histórica de Dolarización (%)")
        query_hist = """
            SELECT 
                f.fecha_corte,
                f.codigo_cuenta as cod,
                f.monto_me,
                f.monto_total
            FROM estados_financieros_moneda f
            WHERE f.id_grupo = %s AND f.codigo_cuenta IN ('130.00', '210.00')
            ORDER BY f.fecha_corte ASC
        """
        df_hist = consultar_db(query_hist, (id_g,))
        if not df_hist.empty:
            df_hist['fecha_label'] = pd.to_datetime(df_hist['fecha_corte']).dt.strftime('%b %Y')
            df_hist['pct_me'] = (df_hist['monto_me'] / df_hist['monto_total'].replace(0, pd.NA)) * 100
            
            piv_hist = df_hist.pivot_table(index='fecha_label', columns='cod', values='pct_me', sort=False).reset_index()
            
            fig_hist = go.Figure()
            if '130.00' in piv_hist.columns:
                fig_hist.add_trace(go.Scatter(x=piv_hist['fecha_label'], y=piv_hist['130.00'], name='Cartera en ME (%)', line=dict(color='#d62728', width=3)))
            if '210.00' in piv_hist.columns:
                fig_hist.add_trace(go.Scatter(x=piv_hist['fecha_label'], y=piv_hist['210.00'], name='Captaciones en ME (%)', line=dict(color='#1f77b4', width=3, dash='dash')))
            
            fig_hist.update_layout(height=320, margin=dict(t=20, b=10, l=10, r=10), yaxis_title="Porcentaje (%)", hovermode="x unified", legend=dict(orientation="h", y=1.15))
            st.plotly_chart(fig_hist, use_container_width=True)

    # --- 6. TABLA RESUMEN DE POSICIÓN CAMBIARIA POR RUBROS PRINCIPALES ---
    st.subheader("📋 Matriz de Descalce Cambiario por Rubro Principal")
    rubros_interes = ['110.00', '120.00', '130.00', '160.00', '210.00', '230.00', '240.00', '270.00', '280.00']
    
    df_matriz = df_corte[df_corte['cod'].isin(rubros_interes)].copy()
    df_matriz['% ME'] = (df_matriz['monto_me'] / df_matriz['monto_total'].replace(0, pd.NA)) * 100
    df_matriz['% UFV'] = (df_matriz['monto_mnufv'] / df_matriz['monto_total'].replace(0, pd.NA)) * 100
    
    cols_display = ['cod', 'desc_cta', 'monto_mn', 'monto_me', 'monto_mnufv', 'monto_total', '% ME', '% UFV']
    df_matriz = df_matriz[cols_display].sort_values('cod')
    
    df_style = df_matriz.copy()
    for col in ['monto_mn', 'monto_me', 'monto_mnufv', 'monto_total']:
        df_style[col] = df_style[col].map('{:,.2f}'.format)
    df_style['% ME'] = df_style['% ME'].map('{:.2f}%'.format)
    df_style['% UFV'] = df_style['% UFV'].map('{:.2f}%'.format)
    
    st.dataframe(
        df_style, 
        use_container_width=True, 
        hide_index=True,
        column_config={
            "cod": "Código",
            "desc_cta": "Rubro Principal",
            "monto_mn": "Moneda Nacional",
            "monto_me": "Moneda Extranjera",
            "monto_mnufv": "Indexado UFV",
            "monto_total": "Total Consolidado"
        }
    )

if __name__ == "__main__":
    mostrar_monitor_dolarizacion()