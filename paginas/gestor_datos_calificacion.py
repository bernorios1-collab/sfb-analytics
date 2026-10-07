import streamlit as st
import pandas as pd
import os
from datetime import datetime
from config_db import obtener_engine

import procesadores.procesador_calificacion as proc_cartera  # type: ignore
import procesadores.procesador_eeff as proc_eeff  # type: ignore

limpiar_texto = proc_eeff.limpiar_texto

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
    "Cooperativas de Ahorro y Crédito": "COO",
    "Instituciones Financieras de Desarrollo": "IFD",
    "Bancos de Desarrollo Productivo": "BDR"
}

BASE_PATH_CARTERA = os.path.join("exceles_asfi", "CalificacionCartera")

def asegurar_directorios():
    for sub in MAPEO_CARPETAS.values():
        os.makedirs(os.path.join(BASE_PATH_CARTERA, sub), exist_ok=True)

def obtener_estado_db_cartera():
    try:
        engine = obtener_engine()
        query = """
            SELECT DISTINCT TO_CHAR(c.fecha_corte, 'YYYY-MM') as periodo,
            TRANSLATE(UPPER(g.nombre_grupo), 'ÁÉÍÓÚÑ', 'AEIOUN') as grupo_norm
            FROM calificacion_cartera c
            JOIN grupos_asfi g ON c.id_grupo = g.id_grupo
        """
        df = pd.read_sql(query, engine)
        df.columns = [c.lower() for c in df.columns]
        
        db_set = set()
        for _, r in df.iterrows():
            for nombre_interfaz in MAPEO_CARPETAS.keys():
                if limpiar_texto(nombre_interfaz) == r['grupo_norm']:
                    db_set.add((r['periodo'], nombre_interfaz))
        return db_set
    except Exception:
        return set()

def obtener_archivos_locales():
    registrados = []
    if not os.path.exists(BASE_PATH_CARTERA): 
        return set()
    for entidad, sub in MAPEO_CARPETAS.items():
        path = os.path.join(BASE_PATH_CARTERA, sub)
        if os.path.exists(path):
            for f in os.listdir(path):
                for a in range(2005, 2027):
                    for m in range(1, 13):
                        if f"{a}{m:02d}" in f and f.lower().endswith(('.xls', '.xlsx')): 
                            registrados.append((f"{a}-{m:02d}", entidad))
    return set(registrados)

def obtener_rutas_excel(entidad: str, periodo: str):
    sub = MAPEO_CARPETAS[entidad]
    ruta_dir = os.path.join(BASE_PATH_CARTERA, sub)
    anio_mes = periodo.replace("-", "")
    rutas_encontradas = []
    
    if os.path.exists(ruta_dir):
        for f in os.listdir(ruta_dir):
            if anio_mes in f and f.lower().endswith(('.xls', '.xlsx')):
                rutas_encontradas.append(os.path.join(ruta_dir, f))
                
    if not rutas_encontradas:
        return None
        
    # Si es cooperativas, ordenamos para que A esté primero y B después si existen ambos
    if entidad == "Cooperativas de Ahorro y Crédito":
        rutas_encontradas.sort()
        return rutas_encontradas # Retorna lista [A, B]
        
    return rutas_encontradas[0] # Retorna string único para los demás grupos

def mostrar_gestor_calificacion():
    st.markdown("""
        <style>
        button[disabled] { opacity: 1.0 !important; color: black !important; cursor: default !important; }
        .stButton button { width: 100%; padding: 0px; border-radius: 4px; }
        .leyenda-container { font-size: 14px; margin-top: 10px; }
        </style>
    """, unsafe_allow_html=True)
    
    st.title("🎯 Calificación de Cartera y Contingente - Control de Carga")
    asegurar_directorios()
    
    años = [str(a) for a in range(datetime.now().year, 2004, -1)]
    col_nav, col_auto = st.columns([1, 1])
    with col_nav:
        anio_sel = st.selectbox("Seleccionar Gestión", años, index=0, key="sel_anio_cartera")
    
    entidades = list(MAPEO_CARPETAS.keys())
    meses_nombres = ["DIC", "NOV", "OCT", "SEPT", "AGO", "JUL", "JUN", "MAY", "ABR", "MAR", "FEB", "ENE"]
    meses_map = {"ENE":1,"FEB":2,"MAR":3,"ABR":4,"MAY":5,"JUN":6,"JUL":7,"AGO":8,"SEPT":9,"OCT":10,"NOV":11,"DIC":12}
    
    db_data = obtener_estado_db_cartera()
    local_data = obtener_archivos_locales()
    hoy = datetime.now()
    anio_int = int(anio_sel)

    with col_auto:
        st.write("")
        if st.button("🚀 Procesar Gestión Completa (Cartera y Contingente)", use_container_width=True, key="btn_auto_cartera"):
            progreso = st.empty()
            with st.spinner(f"Iniciando carga masiva de Calificación de Cartera y Contingente ({anio_sel})..."):
                for ent in entidades:
                    for m_name in meses_nombres:
                        m_num = meses_map[m_name]
                        periodo = f"{anio_int}-{m_num:02d}"
                        
                        if (periodo, ent) in db_data: 
                            continue
                        if datetime(anio_int, m_num, 1) > hoy: 
                            continue
                        
                        try:
                            if (periodo, ent) in local_data:
                                rutas = obtener_rutas_excel(ent, periodo)
                                if rutas:
                                    progreso.info(f"Procesando: {ent} - {m_name}")
                                    proc_cartera.procesar_archivo_calificacion(rutas, ent)
                        except Exception as e:
                            st.warning(f"Error en {ent} ({periodo}): {e}")
                            continue
                
                st.success(f"Proceso finalizado para la gestión {anio_sel}.")
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
                ico, help_t, dis = ICONOS["LOCAL"], "Archivo Descargado localmente, listo para vaciar", False
            else:
                if datetime(anio_int, m_num, 1) > hoy:
                    ico, help_t, dis = ICONOS["ESPERA"], "Futuro", True
                else:
                    ico, help_t, dis = ICONOS["NADA"], "No disponible localmente", True

            if c[j+1].button(ico, key=f"btn_cartera_{ent}_{periodo}", help=help_t, disabled=dis):
                if ico == ICONOS["LOCAL"]:
                    rutas = obtener_rutas_excel(ent, periodo)
                    if rutas:
                        with st.spinner("Subiendo a BD partes A y B..."):
                            exito, msg = proc_cartera.procesar_archivo_calificacion(rutas, ent)
                            if exito: 
                                st.success(msg)
                                st.cache_data.clear()
                                st.rerun()
                            else: 
                                st.error(msg)
    
    st.divider()
    st.markdown(f"""
        <div class="leyenda-container">
            {ICONOS['BD']} Vaciado en BD &nbsp;&nbsp; | &nbsp;&nbsp;
            {ICONOS['LOCAL']} Descargado localmente &nbsp;&nbsp; | &nbsp;&nbsp;
            {ICONOS['ASFI']} Disponible &nbsp;&nbsp; | &nbsp;&nbsp;
            {ICONOS['NADA']} No disponible &nbsp;&nbsp; | &nbsp;&nbsp;
            {ICONOS['ESPERA']} Futuro
        </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    mostrar_gestor_calificacion()