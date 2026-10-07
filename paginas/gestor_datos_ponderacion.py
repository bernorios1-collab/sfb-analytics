import streamlit as st
import pandas as pd
import os
from datetime import datetime
from config_db import obtener_engine

# Importaciones absolutas directas
import scrapers.ponderacion_activos_asfi as scrap_pond  # type: ignore
import procesadores.procesador_ponderacion as proc_pond  # type: ignore

descargar_y_preparar_asfi_ponderacion = scrap_pond.descargar_y_preparar_asfi_ponderacion
verificar_disponibilidad_asfi_ponderacion = scrap_pond.verificar_disponibilidad_asfi_ponderacion
procesar_archivo_ponderacion = proc_pond.procesar_archivo_ponderacion
limpiar_texto = proc_pond.limpiar_texto

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

BASE_PATH = os.path.join("exceles_asfi", "PonderacionActivos")

def asegurar_directorios():
    for sub in MAPEO_CARPETAS.values():
        os.makedirs(os.path.join(BASE_PATH, sub), exist_ok=True)

def obtener_estado_db():
    """Consulta directa a la BD sin caché rígida."""
    try:
        engine = obtener_engine()
        query = """
            SELECT DISTINCT TO_CHAR(i.fecha_corte, 'YYYY-MM') as periodo, 
            TRANSLATE(UPPER(g.nombre_grupo), 'ÁÉÍÓÚÑ', 'AEIOUN') as grupo_norm
            FROM activos_riesgo_valores i
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
            archivos_entidad = os.listdir(path)
            for a in range(2005, 2027):
                for m in range(1, 13):
                    anio_mes = f"{a}{m:02d}"
                    if entidad == "Cooperativas de Ahorro y Crédito":
                        tiene_a = any(anio_mes in f and 'A' in f.upper() and f.lower().endswith(('.xls', '.xlsx', '.xlsm')) for f in archivos_entidad)
                        tiene_b = any(anio_mes in f and 'B' in f.upper() and f.lower().endswith(('.xls', '.xlsx', '.xlsm')) for f in archivos_entidad)
                        if tiene_a and tiene_b:
                            registrados.append((f"{a}-{m:02d}", entidad))
                    else:
                        if any(anio_mes in f and f.lower().endswith(('.xls', '.xlsx', '.xlsm')) for f in archivos_entidad):
                            registrados.append((f"{a}-{m:02d}", entidad))
    return set(registrados)

@st.cache_data(ttl=600)
def cached_verificar_asfi(sig_url, sig_file, periodo):
    return verificar_disponibilidad_asfi_ponderacion(sig_url, sig_file, periodo)

def obtener_rutas_excel(entidad, periodo):
    """Retorna una lista con las rutas de los archivos excel para el periodo (maneja archivos A y B para cooperativas)."""
    sub = MAPEO_CARPETAS[entidad]
    ruta = os.path.join(BASE_PATH, sub)
    anio_mes = periodo.replace("-", "")
    archivos = []
    if os.path.exists(ruta):
        for f in os.listdir(ruta):
            if anio_mes in f and f.lower().endswith(('.xls', '.xlsx', '.xlsm')):
                archivos.append(os.path.join(ruta, f))
    archivos.sort() # Ordena para que el archivo A sea procesado antes que el B
    return archivos

def mostrar_gestor_ponderacion():
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
    
    st.title("⚖️ Activos Ponderados por Riesgo - Control de Carga")
    asegurar_directorios()
    
    años = [str(a) for a in range(datetime.now().year, 2004, -1)]
    col_nav, col_auto = st.columns([1, 1])
    with col_nav:
        anio_sel = st.selectbox("Seleccionar Gestión", años, index=0, key="sb_pond_gestion")
    
    entidades = list(MAPEO_CARPETAS.keys())
    meses_nombres = ["DIC", "NOV", "OCT", "SEPT", "AGO", "JUL", "JUN", "MAY", "ABR", "MAR", "FEB", "ENE"]
    meses_map = {"ENE":1,"FEB":2,"MAR":3,"ABR":4,"MAY":5,"JUN":6,"JUL":7,"AGO":8,"SEPT":9,"OCT":10,"NOV":11,"DIC":12}
    
    db_data = obtener_estado_db()
    local_data = obtener_archivos_locales()
    hoy = datetime.now()
    anio_int = int(anio_sel)

    with col_auto:
        st.write("") 
        if st.button("🚀 Procesar Toda la Gestión", use_container_width=True, key="btn_pond_automatico"):
            progreso = st.empty()
            with st.spinner(f"Iniciando carga masiva de activos ponderados de la gestión {anio_sel}..."):
                for ent in entidades:
                    for m_name in meses_nombres:
                        m_num = meses_map[m_name]
                        periodo = f"{anio_int}-{m_num:02d}"
                        
                        if (periodo, ent) in db_data: continue
                        if datetime(anio_int, m_num, 1) > hoy: continue
                        
                        try:
                            sig_url, sig_file = MAPEO_URL_SIGLAS[ent]
                            if (periodo, ent) not in local_data:
                                if cached_verificar_asfi(sig_url, sig_file, periodo):
                                    descargar_y_preparar_asfi_ponderacion(ent, periodo, os.path.join(BASE_PATH, MAPEO_CARPETAS[ent]))
                                    local_data = obtener_archivos_locales()

                            if (periodo, ent) in local_data:
                                rutas = obtener_rutas_excel(ent, periodo)
                                if rutas:
                                    progreso.info(f"Procesando Activos Ponderados: {ent} - {m_name}")
                                    exito_grupo = True
                                    for idx_r, ruta in enumerate(rutas):
                                        limpiar = (idx_r == 0) # Limpieza solo en el primer archivo (A)
                                        exito_proc, msg_proc = procesar_archivo_ponderacion(ruta, sig_file, limpiar_previo=limpiar)
                                        if not exito_proc:
                                            exito_grupo = False
                                            st.warning(f"Error en {ent} ({periodo}): {msg_proc}")
                                    if exito_grupo:
                                        db_data.add((periodo, ent))
                        except Exception as e:
                            st.warning(f"Error en {ent} ({periodo}): {e}")
                            continue
                
                st.success(f"Proceso de activos ponderados de la gestión {anio_sel} finalizado.")
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
                ico, help_t, dis = ICONOS["LOCAL"], "Archivos Descargados, pero no vaciados en la BD", False
            else:
                if datetime(anio_int, m_num, 1) > hoy:
                    ico, help_t, dis = ICONOS["ESPERA"], "Futuro", True
                else:
                    sig_url, sig_file = MAPEO_URL_SIGLAS[ent]
                    if cached_verificar_asfi(sig_url, sig_file, periodo):
                        ico, help_t, dis = ICONOS["ASFI"], "Disponible en ASFI, pero no Descargado localmente", False
                    else:
                        ico, help_t, dis = ICONOS["NADA"], "No disponible en ASFI", True

            if c[j+1].button(ico, key=f"mat_pond_{ent}_{periodo}", help=help_t, disabled=dis):
                if ico == ICONOS["LOCAL"]:
                    rutas = obtener_rutas_excel(ent, periodo)
                    if rutas:
                        with st.spinner("Subiendo Activos Ponderados a DB..."):
                            sig_url, sig_file = MAPEO_URL_SIGLAS[ent]
                            exito_total = True
                            msg_final = ""
                            for idx_r, ruta in enumerate(rutas):
                                limpiar = (idx_r == 0)
                                exito, msg = procesar_archivo_ponderacion(ruta, sig_file, limpiar_previo=limpiar)
                                if not exito:
                                    exito_total = False
                                    msg_final = msg
                                    break
                                else:
                                    msg_final = msg
                            if exito_total: 
                                st.success(msg_final)
                                st.rerun()
                            else: 
                                st.error(msg_final)
                    else:
                        st.warning(f"⚠️ No se encontraron los archivos Excel físicos en la ruta local para {ent} ({periodo}).")
                elif ico == ICONOS["ASFI"]:
                    with st.spinner("Descargando..."):
                        exito, msg = descargar_y_preparar_asfi_ponderacion(ent, periodo, os.path.join(BASE_PATH, MAPEO_CARPETAS[ent]))
                        if exito: 
                            st.success(msg)
                            st.rerun()
                        else: 
                            st.error(msg)
    
    st.divider()
    
    st.markdown(f"""
        <div class="leyenda-container">
            {ICONOS['BD']} Vaciado en la Base de Datos &nbsp;&nbsp; | &nbsp;&nbsp;
            {ICONOS['LOCAL']} Archivos Descargados, pero no vaciados en la BD &nbsp;&nbsp; | &nbsp;&nbsp;
            {ICONOS['ASFI']} Disponible en ASFI, pero no Descargado localmente &nbsp;&nbsp; | &nbsp;&nbsp;
            {ICONOS['NADA']} No disponible en ASFI &nbsp;&nbsp; | &nbsp;&nbsp;
            {ICONOS['ESPERA']} Futuro
        </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    mostrar_gestor_ponderacion()