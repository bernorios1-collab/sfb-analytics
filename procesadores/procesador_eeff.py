import pandas as pd
from sqlalchemy import text
import os, re, calendar
import numpy as np
from config_db import obtener_engine

engine = obtener_engine()

MAPEO_SIGLAS = {
    'BMU': 'Bancos Multiples', 
    'BPY': 'Bancos PYME', 
    'EFV': 'Entidades Financieras de Vivienda',
    'COO': 'Cooperativas de Ahorro y Credito',  # Actualizado sin "Abiertas"
    'IFD': 'Instituciones Financieras de Desarrollo',
    'BDR': 'Bancos de Desarrollo Productivo'
}

def limpiar_texto(t):
    if not isinstance(t, str): return str(t)
    r = {'á':'a','é':'e','í':'i','ó':'o','ú':'u','ñ':'n','Á':'A','É':'E','Í':'I','Ó':'O','Ú':'U','Ñ':'N'}
    for k, v in r.items(): t = t.replace(k, v)
    return t.strip().upper()

def procesar_archivo_especifico(ruta_completa):
    nombre_archivo = os.path.basename(ruta_completa)
    match = re.search(r'(\d{4})(\d{2})', nombre_archivo)
    if not match: return False, "Fecha no detectada."
    
    gestion, mes = int(match.group(1)), int(match.group(2))
    fecha_corte = f"{gestion}-{mes:02d}-{calendar.monthrange(gestion, mes)[1]}"
    
    sigla_archivo = next((s for s in MAPEO_SIGLAS if s in nombre_archivo.upper()), None)
    if not sigla_archivo: return False, "Sigla no reconocida."
    nombre_grupo_app = MAPEO_SIGLAS[sigla_archivo]

    try:
        motor = 'xlrd' if ruta_completa.endswith('.xls') else 'openpyxl'
        df_raw = pd.read_excel(ruta_completa, header=None, engine=motor)

        # Coordenadas ASFI: Fila 5 nombres, Fila 7 en adelante datos numéricos
        fila_nombres, fila_datos, col_codigo, col_inicio_bancos = 5, 7, 1, 3
        row_nombres = df_raw.iloc[fila_nombres]
        
        # 1. Identificar columnas candidatas (que tengan algún nombre)
        indices_candidatos = []
        for i in range(col_inicio_bancos, len(row_nombres)):
            val = str(row_nombres[i]).strip().upper()
            if val not in ['NAN', 'NONE', '', '||'] and len(val) > 1:
                indices_candidatos.append(i)

        if not indices_candidatos: return False, "No se detectaron columnas de entidades."

        # --- LÓGICA DE VALIDACIÓN ARITMÉTICA Y ASIGNACIÓN DE TOTAL SISTEMA ---
        ultima_col = indices_candidatos[-1]
        
        MAPEO_TOTAL_SISTEMA = {
            'BMU': 'TSBMU',
            'BDR': 'TSBDR',
            'BPY': 'TSBPY',
            'COO': 'TSCOO',
            'EFV': 'TSEFV',
            'IFD': 'TSIFD'
        }
        
        es_totalizador = False
        for r_idx in range(fila_datos, min(fila_datos + 50, len(df_raw))): 
            fila_prueba = pd.to_numeric(df_raw.iloc[r_idx, indices_candidatos], errors='coerce').fillna(0)
            
            suma_entidades = fila_prueba.iloc[:-1].sum()
            valor_totalizador = fila_prueba.iloc[-1]
            
            if abs(suma_entidades - valor_totalizador) < 1.0 and valor_totalizador != 0:
                es_totalizador = True
                break
        
        # Clonamos la fila de nombres para poder mutarla sin afectar el dataframe original
        row_nombres_procesado = row_nombres.copy()
        
        if es_totalizador:
            nombre_total_sistema = MAPEO_TOTAL_SISTEMA.get(sigla_archivo, f"TS_{sigla_archivo}")
            row_nombres_procesado[ultima_col] = nombre_total_sistema
            print(f"INFO: Se detectó columna totalizadora y se renombró a: {nombre_total_sistema}")
            
            # Incluimos todas las columnas (incluyendo el totalizador ahora renombrado)
            indices_finales = indices_candidatos
        else:
            indices_finales = indices_candidatos

        # --- PROCESAMIENTO DE DATOS ---
        data_list = []
        for i in range(fila_datos, len(df_raw)):
            codigo = str(df_raw.iloc[i, col_codigo]).strip()
            if not re.match(r'^[0-9C]', codigo, re.IGNORECASE): continue
            
            descripcion = str(df_raw.iloc[i, 2]).strip() 
            
            for idx in indices_finales:
                nombre_ent = str(row_nombres_procesado[idx]).strip()
                monto = pd.to_numeric(df_raw.iloc[i, idx], errors='coerce')
                data_list.append({
                    'entidad': nombre_ent, 
                    'codigo': codigo, 
                    'descripcion': descripcion,
                    'monto': monto if not pd.isna(monto) else 0
                })

        df_final = pd.DataFrame(data_list)
        if df_final.empty: return False, "Sin datos procesables."

        with engine.begin() as conn:
            res_grupo = conn.execute(text("""
                SELECT id_grupo FROM grupos_asfi 
                WHERE TRANSLATE(UPPER(nombre_grupo), 'ÁÉÍÓÚÑ', 'AEIOUN') = :g
            """), {"g": limpiar_texto(nombre_grupo_app)}).fetchone()
            
            if not res_grupo: return False, "Grupo no encontrado en DB."
            id_grupo = res_grupo[0]

            check = conn.execute(text("""
                SELECT COUNT(*) FROM estados_financieros ef
                JOIN entidades e ON ef.entidad = e.nombre_entidad
                WHERE ef.fecha_corte = :f AND e.id_grupo = :idg
            """), {"f": fecha_corte, "idg": id_grupo}).scalar()

            if check > 0:
                return False, f"⚠️ Datos ya existentes para {nombre_grupo_app} en {fecha_corte}."

            for ent in df_final['entidad'].unique():
                conn.execute(text("""
                    INSERT INTO entidades (nombre_entidad, id_grupo) VALUES (:e, :idg) 
                    ON CONFLICT (nombre_entidad) DO UPDATE SET id_grupo = EXCLUDED.id_grupo
                """), {"e": limpiar_texto(ent), "idg": id_grupo})
            
            plan = df_final[['codigo', 'descripcion']].drop_duplicates(subset=['codigo'])
            for _, r in plan.iterrows():
                conn.execute(text("""
                    INSERT INTO plan_cuentas (codigo_cuenta, descripcion_cuenta) VALUES (:c, :d) 
                    ON CONFLICT (codigo_cuenta) DO NOTHING
                """), {"c": r['codigo'], "d": limpiar_texto(r['descripcion'])})

            df_to_db = df_final[['entidad', 'codigo', 'monto']].copy()
            df_to_db.columns = ['entidad', 'codigo_cuenta', 'monto']
            df_to_db['fecha_corte'] = fecha_corte
            df_to_db['entidad'] = df_to_db['entidad'].apply(limpiar_texto)
            df_to_db.to_sql('estados_financieros', conn, if_exists='append', index=False)

        return True, f"Éxito: {len(indices_finales)} entidades cargadas."
    except Exception as e:
        return False, f"Error: {str(e)}"