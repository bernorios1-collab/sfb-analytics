import streamlit as st
import pandas as pd
import os
import calendar
from sqlalchemy import text
from config_db import obtener_engine

MAPEO_CARPETAS = {
    "Bancos Múltiples": "BMU", 
    "Bancos PYME": "BPY",
    "Entidades Financieras de Vivienda": "EFV",
    "Cooperativas de Ahorro y Crédito": "CAC",
    "Instituciones Financieras de Desarrollo": "IFD",
    "Bancos de Desarrollo Productivo": "BDP"
}

MAPEO_URL_SIGLAS = {
    "Bancos Múltiples": "BMU",
    "Bancos PYME": "BPY",
    "Entidades Financieras de Vivienda": "EFV",
    "Cooperativas de Ahorro y Crédito": "COO",
    "Instituciones Financieras de Desarrollo": "IFD",
    "Bancos de Desarrollo Productivo": "BDR"
}

BASE_PATH = os.path.join("exceles_asfi", "PonderacionActivos")

def limpiar_texto(t):
    if not isinstance(t, str): return str(t)
    r = {'á':'a','é':'e','í':'i','ó':'o','ú':'u','ñ':'n','Á':'A','É':'E','Í':'I','Ó':'O','Ú':'U','Ñ':'N'}
    for k, v in r.items(): t = t.replace(k, v)
    return t.strip().upper()

def obtener_ruta_excel_local(grupo_nombre, periodo):
    sub = MAPEO_CARPETAS.get(grupo_nombre)
    if not sub: return None
    ruta_dir = os.path.join(BASE_PATH, sub)
    if not os.path.exists(ruta_dir):
        ruta_dir = "."
    
    anio_mes = periodo.replace("-", "")
    sigla_file = MAPEO_URL_SIGLAS.get(grupo_nombre, "")
    
    if os.path.exists(ruta_dir):
        for f in os.listdir(ruta_dir):
            if anio_mes in f and sigla_file in f and f.lower().endswith(('.xls', '.xlsx', '.xlsm')):
                return os.path.join(ruta_dir, f)
            elif anio_mes in f and f.lower().endswith(('.xls', '.xlsx', '.xlsm')):
                return os.path.join(ruta_dir, f)
    return None

def mostrar_modulo_auditoria_ponderacion():
    st.title("🔍 Auditoría Detallada Celda por Celda: Activos Ponderados y CAP")
    st.markdown("Módulo interactivo de inspección exhaustiva. Seleccione el grupo, periodo y entidad para verificar paso a paso cada celda del archivo Excel oficial frente a la Base de Datos y su recálculo normativo.")

    engine = obtener_engine()

    col1, col2, col3 = st.columns(3)
    with col1:
        grupo_sel = st.selectbox("1. Grupo Financiero", list(MAPEO_CARPETAS.keys()), key="aud_grupo_g")
    with col2:
        try:
            df_per = pd.read_sql("SELECT DISTINCT TO_CHAR(fecha_corte, 'YYYY-MM') as periodo FROM activos_riesgo_valores ORDER BY periodo DESC", engine)
            periodos = df_per['periodo'].tolist() if not df_per.empty else []
        except:
            periodos = []
        
        if periodos:
            periodo_sel = st.selectbox("2. Periodo (Fecha de Corte)", periodos, key="aud_per_g")
        else:
            st.warning("No hay periodos en la Base de Datos.")
            return
    with col3:
        try:
            df_ent = pd.read_sql(text("SELECT id_entidad, nombre_entidad FROM entidades ORDER BY nombre_entidad"), engine)
            entidades_dict = dict(zip(df_ent['nombre_entidad'], df_ent['id_entidad']))
            entidad_sel = st.selectbox("3. Entidad Financiera", list(entidades_dict.keys()), key="aud_ent_g")
            id_entidad_sel = entidades_dict.get(entidad_sel)
        except Exception as e:
            st.error(f"Error cargando entidades: {e}")
            return

    if not grupo_sel or not periodo_sel or not id_entidad_sel:
        return

    st.divider()

    anio, mes = periodo_sel.split("-")
    ultimo_dia = calendar.monthrange(int(anio), int(mes))[1]
    fecha_corte_str = f"{anio}-{mes}-{ultimo_dia}"

    ruta_excel = obtener_ruta_excel_local(grupo_sel, periodo_sel)
    
    col_info1, col_info2 = st.columns([2, 1])
    with col_info1:
        if ruta_excel and os.path.exists(ruta_excel):
            st.success(f"📂 **Archivo Físico Local Detectado:** `{ruta_excel}`")
        else:
            st.warning(f"⚠️ **Archivo físico no encontrado localmente para {grupo_sel} ({periodo_sel}).** Se auditarán los registros de la Base de Datos de forma individual.")
    with col_info2:
        st.info(f"📅 **Fecha Corte SQL:** `{fecha_corte_str}`")

    st.markdown("---")

    query_activos = """
        SELECT p.descripcion_categoria as categoria, v.valor as valor_bd, p.orden
        FROM activos_riesgo_valores v
        JOIN plan_categorias_riesgo p ON v.id_plan_cat = p.id_plan_cat
        WHERE v.id_entidad = :id_ent AND v.fecha_corte = :f
        ORDER BY p.orden
    """
    df_db_activos = pd.read_sql(text(query_activos), engine, params={"id_ent": id_entidad_sel, "f": fecha_corte_str})

    query_ratios = """
        SELECT p.codigo_ratio as ratio, v.valor as valor_bd, p.orden
        FROM ratios_regulatorios_valores v
        JOIN plan_ratios_regulatorios p ON v.id_plan_ratio = p.id_plan_ratio
        WHERE v.id_entidad = :id_ent AND v.fecha_corte = :f
        ORDER BY p.orden
    """
    df_db_ratios = pd.read_sql(text(query_ratios), engine, params={"id_ent": id_entidad_sel, "f": fecha_corte_str})

    df_excel_parseado = None
    if ruta_excel and os.path.exists(ruta_excel):
        try:
            motor = 'xlrd' if ruta_excel.lower().endswith('.xls') else 'openpyxl'
            df_raw = pd.read_excel(ruta_excel, header=None, engine=motor)
            
            fila_bancos = None
            indices_bancos = []
            for r_idx in range(min(12, len(df_raw))):
                row_test = df_raw.iloc[r_idx]
                for idx in range(1, len(row_test)):
                    banco_nom = str(row_test.iloc[idx]).strip()
                    if banco_nom.upper() not in ['NAN', 'NONE', ''] and len(banco_nom) > 1:
                        indices_bancos.append((idx, banco_nom))
                if indices_bancos:
                    fila_bancos = r_idx
                    break
            
            if fila_bancos is not None:
                col_entidad_idx = None
                for col_idx, b_nom in indices_bancos:
                    if limpiar_texto(b_nom) == limpiar_texto(entidad_sel) or limpiar_texto(entidad_sel) in limpiar_texto(b_nom):
                        col_entidad_idx = col_idx
                        break
                
                if col_entidad_idx is not None:
                    excel_rows = []
                    for r_idx in range(fila_bancos + 1, len(df_raw)):
                        glosa = df_raw.iloc[r_idx, 0]
                        if pd.notna(glosa) and str(glosa).strip() != "":
                            val = pd.to_numeric(df_raw.iloc[r_idx, col_entidad_idx], errors='coerce')
                            excel_rows.append({"categoria": str(glosa).strip(), "valor_excel": float(val) if not pd.isna(val) else 0.0})
                    df_excel_parseado = pd.DataFrame(excel_rows)
        except Exception as ex:
            st.error(f"Error al procesar el archivo físico: {ex}")

    tab_celdas, tab_norma, tab_ratios = st.tabs([
        "🔬 Comparativa Celda por Celda (Activos)", 
        "📐 Recálculo y Verificación Normativa (CAP)", 
        "📋 Ratios Regulatorios en BD"
    ])

    with tab_celdas:
        st.subheader("Inspección Detallada: Dato por Dato (Excel vs BD)")
        st.markdown("A continuación se presenta la comparación exhaustiva de cada categoría ponderada por riesgo, enfrentando el valor original de la celda en el archivo Excel frente al registro almacenado en la Base de Datos:")

        if df_excel_parseado is not None and not df_db_activos.empty:
            df_db_activos['cat_limpia'] = df_db_activos['categoria'].apply(limpiar_texto)
            df_excel_parseado['cat_limpia'] = df_excel_parseado['categoria'].apply(limpiar_texto)
            
            df_completo = pd.merge(df_excel_parseado, df_db_activos, on='cat_limpia', how='outer').fillna(0)
            if 'categoria_x' in df_completo.columns:
                df_completo['Concepto / Categoría'] = df_completo['categoria_x'].replace({0: df_completo['categoria_y']})
            else:
                df_completo['Concepto / Categoría'] = df_completo['categoria']
            
            df_completo['Diferencia (Excel - BD)'] = df_completo['valor_excel'] - df_completo['valor_bd']
            df_completo['Estado de Auditoría'] = df_completo['Diferencia (Excel - BD)'].apply(
                lambda x: "✅ Coincide" if abs(x) < 1e-4 else "❌ Discrepancia"
            )
            
            for idx, row in df_completo.iterrows():
                num_orden = row.get('orden', idx + 1)
                concepto = row['Concepto / Categoría']
                estado = row['Estado de Auditoría']
                with st.expander(f"🔹 [{num_orden}] {concepto} — {estado}"):
                    col_a, col_b, col_c = st.columns(3)
                    col_a.metric("📂 Valor Excel Físico", f"{row['valor_excel']:,.2f}")
                    col_b.metric("🛢️ Valor en Base de Datos", f"{row['valor_bd']:,.2f}")
                    col_c.metric("⚡ Diferencia", f"{row['Diferencia (Excel - BD)']:,.2f}")
        else:
            st.info("Mostrando registros de Activos de Riesgo directamente desde la Base de Datos.")
            if not df_db_activos.empty:
                for idx, row in df_db_activos.iterrows():
                    num_orden = row['orden']
                    concepto = row['categoria']
                    with st.expander(f"🔹 [{num_orden}] {concepto}"):
                        st.metric("🛢️ Valor Registrado en Base de Datos", f"{row['valor_bd']:,.2f}")

    with tab_norma:
        st.subheader("📐 Recálculo Normativo del Coeficiente de Adecuación Patrimonial (CAP)")
        st.markdown("Verificación de la fórmula regulatoria estándar: el CAP se obtiene relacionando el **Capital Regulatorio** frente a los **Activos Ponderados por Riesgo (Activos Computables)**.")
        
        if not df_db_ratios.empty:
            st.dataframe(df_db_ratios[['ratio', 'valor_bd']], use_container_width=True)
            
            cap_row = df_db_ratios[df_db_ratios['ratio'].str.contains("ADECUACION PATRIMONIAL|CAP", case=False, na=False)]
            if not cap_row.empty:
                val_bd_cap = cap_row.iloc[0]['valor_bd']
                st.success(f"✅ Ratio CAP registrado en Base de Datos: **{val_bd_cap*100:.2f}%** (Valor decimal: {val_bd_cap:.6f})")
                st.info("ℹ️ El motor normativo valida que la proporción de adecuación patrimonial se mantenga dentro de los márgenes prudenciales exigidos por la ASFI.")
            else:
                st.warning("⚠️ No se encontró el ratio CAP explícito en los registros normativos de esta entidad.")
        else:
            st.info("No hay datos de ratios regulatorios disponibles para esta entidad en el periodo seleccionado.")

    with tab_ratios:
        st.subheader("📋 Resumen General de Ratios Regulatorios")
        if not df_db_ratios.empty:
            st.dataframe(df_db_ratios[['orden', 'ratio', 'valor_bd']], use_container_width=True)
        else:
            st.info("Sin registros de ratios regulatorios.")

if __name__ == "__main__":
    mostrar_modulo_auditoria_ponderacion()