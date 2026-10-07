import streamlit as st
import pandas as pd
import os
from datetime import datetime
from config_db import obtener_engine

# Importaciones absolutas directas
import scrapers.indicadores_financieros_asfi as scrap_iiff  # type: ignore
import procesadores.procesador_iiff as proc_iiff  # type: ignore

descargar_y_preparar_asfi_indicadores = scrap_iiff.descargar_y_preparar_asfi_indicadores
verificar_disponibilidad_asfi_indicadores = scrap_iiff.verificar_disponibilidad_asfi_indicadores
procesar_archivo_indicadores = proc_iiff.procesar_archivo_indicadores
limpiar_texto = proc_iiff.limpiar_texto

ICONOS = {
    "BD": "🛢️",      
    "LOCAL": "📂",   
    "ASFI": "🟠",    
    "NADA": "❌",    
    "ESPERA": "⚪"   
}

MAPEO_CARPETAS = {
    "Bancos Múltiples": "BMU", 
    "Bancos PYME": "BPY",
    "Entidades Financieras de Vivienda": "EFV",
    "Cooperativas de Ahorro y Crédito": "CAC",
    "Instituciones Financieras de Desarrollo": "IFD",
    "Bancos de Desarrollo Productivo": "BDP"
}

MAPEO_URL_SIGLAS = {
    "Bancos Múltiples": ("bancos_multiples", "BMU"),
    "Bancos PYME": ("bancos_pymes", "BPY"),
    "Entidades Financieras de Vivienda": ("ent_fin_vivienda", "EFV"),
    "Cooperativas de Ahorro y Crédito": ("cooperativas", "COO"),
    "Instituciones Financieras de Desarrollo": ("int_fin_des", "IFD"),
    "Bancos de Desarrollo Productivo": ("ban_des_pro", "BDR")
}

BASE_PATH = os.path.join("exceles_asfi", "IndFinancieros")

def asegurar_directorios():
    for sub in MAPEO_CARPETAS.values():
        os.makedirs(os.path.join(BASE_PATH, sub), exist_ok=True)

def obtener_estado_db():
    try:
        engine = obtener_engine()
        query = """
            SELECT DISTINCT TO_CHAR(i.fecha_corte, 'YYYY-MM') as periodo, 
            TRANSLATE(UPPER(g.nombre_grupo), 'ÁÉÍÓÚÑ', 'AEIOUN') as grupo_norm
            FROM indicadores_financieros i
            JOIN entidades e ON i.id_entidad = e.id_entidad
            JOIN grupos_asfi g ON e.id_grupo = g.id_grupo
        """
        df = pd.read_sql(query, engine)
        df.columns = [c.lower() for c in df.columns]
        
        db_set = set()
        for _, r in df.iterrows():
            for nombre_interfaz in MAPEO_CARPETAS.keys():
                if limpiar_texto(nombre_interfaz) == r['grupo_norm']:
                    db_set.add((r['periodo'], nombre_interfaz))
        return db_set
    except: 
        return set()

def obtener_archivos_locales():
    registrados = []
    if not os.path.exists(BASE_PATH): return set()
    for entidad, sub in MAPEO_CARPETAS.items():
        path = os.path.join(BASE_PATH, sub)
        if os.path.exists(path):
            for f in os.listdir(path):
                for a in range(2005, 2027):
                    for m in range(1, 13):
                        if f"{a}{m:02d}" in f: 
                            registrados.append((f"{a}-{m:02d}", entidad))
    return set(registrados)

def obtener_ruta_excel(entidad, periodo):
    sub = MAPEO_CARPETAS[entidad]
    ruta = os.path.join(BASE_PATH, sub)
    anio_mes = periodo.replace("-", "")
    if os.path.exists(ruta):
        for f in os.listdir(ruta):
            if anio_mes in f and f.endswith(('.xls', '.xlsx')):
                return os.path.join(ruta, f)
    return None

def mostrar_gestor_indicadores():
    st.markdown("""
        <style>
        button[disabled] {
            opacity: 1.0 !important;
            color: black !important;
            cursor: default !important;
        }
        .stButton button { width: 100%; padding: 0px; border-radius: 4px; }
        .leyenda-container {
            font-size: 14px;
            margin-top: 10px;
        }
        </style>
    """, unsafe_allow_html=True)
    
    st.title("📂 Indicadores Financieros - Control de Carga")
    asegurar_directorios()
    
    años = [str(a) for a in range(datetime.now().year, 2004, -1)]
    col_nav, col_auto = st.columns([1, 1])
    with col_nav:
        anio_sel = st.selectbox("Seleccionar Gestión", años, index=0, key="sb_ind_gestion")
    
    entidades = list(MAPEO_CARPETAS.keys())
    meses_nombres = ["DIC", "NOV", "OCT", "SEPT", "AGO", "JUL", "JUN", "MAY", "ABR", "MAR", "FEB", "ENE"]
    meses_map = {"ENE":1,"FEB":2,"MAR":3,"ABR":4,"MAY":5,"JUN":6,"JUL":7,"AGO":8,"SEPT":9,"OCT":10,"NOV":11,"DIC":12}
    
    db_data = obtener_estado_db()
    local_data = obtener_archivos_locales()
    hoy = datetime.now()
    anio_int = int(anio_sel)

    with col_auto:
        st.write("") 
        if st.button("🚀 Procesar Toda la Gestión", use_container_width=True, key="btn_ind_automatico"):
            progreso = st.empty()
            with st.spinner(f"Iniciando carga masiva de indicadores de la gestión {anio_sel}..."):
                for ent in entidades:
                    for m_name in meses_nombres:
                        m_num = meses_map[m_name]
                        periodo = f"{anio_int}-{m_num:02d}"
                        
                        if (periodo, ent) in db_data: continue
                        if datetime(anio_int, m_num, 1) > hoy: continue
                        
                        try:
                            if (periodo, ent) not in local_data:
                                sig_url, sig_file = MAPEO_URL_SIGLAS[ent]
                                if verificar_disponibilidad_asfi_indicadores(sig_url, sig_file, periodo):
                                    descargar_y_preparar_asfi_indicadores(ent, periodo, os.path.join(BASE_PATH, MAPEO_CARPETAS[ent]))
                                    local_data = obtener_archivos_locales()

                            if (periodo, ent) in local_data:
                                ruta = obtener_ruta_excel(ent, periodo)
                                if ruta:
                                    progreso.info(f"Procesando Indicadores: {ent} - {m_name}")
                                    procesar_archivo_indicadores(ruta, MAPEO_URL_SIGLAS[ent][1])
                        except Exception as e:
                            st.warning(f"Error en {ent} ({periodo}): {e}")
                            continue
                
                st.success(f"Proceso de indicadores de la gestión {anio_sel} finalizado.")
                st.cache_data.clear()
                st.rerun()

    st.markdown(f"### 📅 Gestión {anio_sel}")

    cols_h = st.columns([3.5] + [0.7]*12)
    cols_h[0].caption("TIPO ENTIDAD")
    for j, m_name in enumerate(meses_nombres): 
        cols_h[j+1].write(f"**{m_name}**")

    for ent in entidades:
        c = st.columns([3.5] + [0.7]*12)
        c[0].write(ent)
        for j, m_name in enumerate(meses_nombres):
            m_num = meses_map[m_name]
            periodo = f"{anio_int}-{m_num:02d}"
            
            if (periodo, ent) in db_data:
                ico, help_t, dis = ICONOS["BD"], "Vaciado en la Base de Datos", True
            elif (periodo, ent) in local_data:
                ico, help_t, dis = ICONOS["LOCAL"], "Archivo Descargado, pero no vaciado en la BD", False
            else:
                if datetime(anio_int, m_num, 1) > hoy:
                    ico, help_t, dis = ICONOS["ESPERA"], "Futuro", True
                else:
                    sig_url, sig_file = MAPEO_URL_SIGLAS[ent]
                    if verificar_disponibilidad_asfi_indicadores(sig_url, sig_file, periodo):
                        ico, help_t, dis = ICONOS["ASFI"], "Disponible en ASFI, pero no Descargado localmente", False
                    else:
                        ico, help_t, dis = ICONOS["NADA"], "No disponible en ASFI", True

            if c[j+1].button(ico, key=f"mat_ind_{ent}_{periodo}", help=help_t, disabled=dis):
                if ico == ICONOS["LOCAL"]:
                    ruta = obtener_ruta_excel(ent, periodo)
                    if ruta:
                        with st.spinner("Subiendo Indicadores a DB..."):
                            exito, msg = procesar_archivo_indicadores(ruta, MAPEO_URL_SIGLAS[ent][1])
                            if exito: 
                                st.success(msg)
                                st.cache_data.clear()
                                st.rerun()
                            else: 
                                st.error(msg)
                elif ico == ICONOS["ASFI"]:
                    with st.spinner("Descargando..."):
                        exito, msg = descargar_y_preparar_asfi_indicadores(ent, periodo, os.path.join(BASE_PATH, MAPEO_CARPETAS[ent]))
                        if exito: 
                            st.success(msg)
                            st.cache_data.clear()
                            st.rerun()
                        else: 
                            st.error(msg)
    
    st.divider()
    
    st.markdown(f"""
        <div class="leyenda-container">
            {ICONOS['BD']} Vaciado en la Base de Datos &nbsp;&nbsp; | &nbsp;&nbsp;
            {ICONOS['LOCAL']} Archivo Descargado, pero no vaciado en la BD &nbsp;&nbsp; | &nbsp;&nbsp;
            {ICONOS['ASFI']} Disponible en ASFI, pero no Descargado localmente &nbsp;&nbsp; | &nbsp;&nbsp;
            {ICONOS['NADA']} No disponible en ASFI &nbsp;&nbsp; | &nbsp;&nbsp;
            {ICONOS['ESPERA']} Futuro
        </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    mostrar_gestor_indicadores()