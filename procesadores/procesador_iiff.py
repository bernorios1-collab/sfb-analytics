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
    'COO': 'Cooperativas de Ahorro y Credito', 
    'IFD': 'Instituciones Financieras de Desarrollo',
    'BDR': 'Bancos de Desarrollo Productivo'
}

MAPEO_TOTAL_SISTEMA = {
    'BMU': 'TSBMU',
    'BDR': 'TSBDR',
    'BPY': 'TSBPY',
    'COO': 'TSCOO',
    'EFV': 'TSEFV',
    'IFD': 'TSIFD'
}

def limpiar_texto(t):
    if not isinstance(t, str): return str(t)
    r = {'á':'a','é':'e','í':'i','ó':'o','ú':'u','ñ':'n','Á':'A','É':'E','Í':'I','Ó':'O','Ú':'U','Ñ':'N'}
    for k, v in r.items(): t = t.replace(k, v)
    return t.strip().upper()

def procesar_archivo_indicadores(ruta_completa, sigla_detectada):
    nombre_archivo = os.path.basename(ruta_completa)
    match = re.search(r'(\d{4})(\d{2})', nombre_archivo)
    if not match: 
        return False, "Fecha no detectada en el nombre del archivo de Indicadores."
    
    gestion, mes = int(match.group(1)), int(match.group(2))
    fecha_corte = f"{gestion}-{mes:02d}-{calendar.monthrange(gestion, mes)[1]}"
    
    try:
        motor = 'xlrd' if ruta_completa.endswith('.xls') else 'openpyxl'
        df_raw = pd.read_excel(ruta_completa, header=None, engine=motor)
        
        fila_bancos = 4
        fila_datos_inicio = 6
        row_bancos = df_raw.iloc[fila_bancos]
        
        indices_bancos = []
        for idx in range(1, len(row_bancos)):
            banco_nom = str(row_bancos.iloc[idx]).strip()
            if banco_nom.upper() not in ['NAN', 'NONE', ''] and len(banco_nom) > 1:
                indices_bancos.append(idx)
                
        if not indices_bancos:
            return False, "No se detectaron columnas de entidades."
            
        lista_plan_indicadores_final = []
        registros_a_insertar_final = []
        
        total_filas = len(df_raw)
        puntero_fila = fila_datos_inicio
        
        grupo_actual_limpio = "GENERAL"
        token_grupo_actual = None
        
        with engine.begin() as conn:
            df_entidades_db = pd.read_sql("SELECT id_entidad, nombre_entidad FROM entidades", conn)
            dict_entidades = dict(zip(df_entidades_db['nombre_entidad'].apply(limpiar_texto), df_entidades_db['id_entidad']))
            
            nombre_grupo_app = MAPEO_SIGLAS.get(sigla_detectada, sigla_detectada)
            res_grupo = conn.execute(text("""
                SELECT id_grupo FROM grupos_asfi 
                WHERE TRANSLATE(UPPER(nombre_grupo), 'ÁÉÍÓÚÑ', 'AEIOUN') = :g
            """), {"g": limpiar_texto(nombre_grupo_app)}).fetchone()
            id_grupo = res_grupo[0] if res_grupo else None
            
            while puntero_fila < total_filas:
                acumulado_indicadores_seccion = []
                diccionario_notas_seccion = {}
                
                inicio_bloque_actual = puntero_fila
                fin_notas_bloque = puntero_fila
                
                idx_exploracion = inicio_bloque_actual
                while idx_exploracion < total_filas:
                    celda = df_raw.iloc[idx_exploracion, 0]
                    if pd.isna(celda) or str(celda).strip() == "":
                        if diccionario_notas_seccion:
                            fin_notas_bloque = idx_exploracion
                            break
                        idx_exploracion += 1
                        continue
                        
                    txt = str(celda).strip()
                    
                    if (txt.upper().startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.', '10.')) or "INDICADORES DE" in txt.upper()) and idx_exploracion != inicio_bloque_actual:
                        if acumulado_indicadores_seccion:
                            fin_notas_bloque = idx_exploracion
                            break
                    
                    match_def = re.match(r'^\s*\((\d+)\)\s+(.+)$', txt)
                    if match_def:
                        token_num = f"({match_def.group(1)})"
                        texto_nota = match_def.group(2).strip()
                        diccionario_notas_seccion[token_num] = texto_nota
                        fin_notas_bloque = idx_exploracion + 1
                        idx_exploracion += 1
                        continue
                    
                    valores_fila = [df_raw.iloc[idx_exploracion, c] for c in indices_bancos]
                    serie_prueba = pd.to_numeric(pd.Series(valores_fila), errors='coerce')
                    
                    if not serie_prueba.isna().all():
                        acumulado_indicadores_seccion.append((idx_exploracion, txt))
                        
                    idx_exploracion += 1
                
                if idx_exploracion >= total_filas:
                    fin_notas_bloque = total_filas
                
                for fila_idx_proc, texto_original in acumulado_indicadores_seccion:
                    for f_verif in range(inicio_bloque_actual, fila_idx_proc + 1):
                        celda_g = df_raw.iloc[f_verif, 0]
                        if pd.isna(celda_g): continue
                        txt_g = str(celda_g).strip()
                        
                        if txt_g.upper().startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.', '10.')) or "INDICADORES DE" in txt_g.upper():
                            match_ng = re.search(r'\s*(\(\d+\))\s*$', txt_g)
                            if match_ng:
                                token_grupo_actual = match_ng.group(1)
                                grupo_actual_limpio = txt_g[:match_ng.start()].strip()
                            else:
                                token_grupo_actual = None
                                grupo_actual_limpio = txt_g
                        else:
                            v_f = [df_raw.iloc[f_verif, c] for c in indices_bancos]
                            if pd.to_numeric(pd.Series(v_f), errors='coerce').isna().all() and not txt_g.startswith('('):
                                match_ns = re.search(r'\s*(\(\d+\))\s*$', txt_g)
                                if match_ns:
                                    token_grupo_actual = match_ns.group(1)
                                    grupo_actual_limpio = txt_g[:match_ns.start()].strip()
                                else:
                                    token_grupo_actual = None
                                    grupo_actual_limpio = txt_g
                    
                    match_llamada = re.search(r'\s*(\(\d+\))\s*$', texto_original)
                    if match_llamada:
                        token_indicador = match_llamada.group(1)
                        nombre_indicador_limpio = texto_original[:match_llamada.start()].strip()
                    else:
                        token_indicador = None
                        nombre_indicador_limpio = texto_original
                        
                    codigo_ind_corto = nombre_indicador_limpio[:100].strip()
                    
                    if codigo_ind_corto.upper() == "UTILIDAD NETA":
                        grupo_final_asignado = "UTILIDAD NETA"
                        nota_final = ""
                    else:
                        grupo_final_asignado = grupo_actual_limpio
                        texto_nota_grupo = diccionario_notas_seccion.get(token_grupo_actual) if token_grupo_actual else None
                        texto_nota_ind = diccionario_notas_seccion.get(token_indicador) if token_indicador else None
                        
                        if texto_nota_grupo and texto_nota_ind:
                            if texto_nota_grupo.strip() == texto_nota_ind.strip():
                                nota_final = texto_nota_grupo
                            else:
                                nota_final = f"{texto_nota_grupo} - {texto_nota_ind}"
                        elif texto_nota_grupo:
                            nota_final = texto_nota_grupo
                        elif texto_nota_ind:
                            nota_final = texto_nota_ind
                        else:
                            nota_final = ""
                        
                    lista_plan_indicadores_final.append({
                        "codigo_indicador": codigo_ind_corto,
                        "grupo_indicador": grupo_final_asignado,
                        "notes_aclaratorias": nota_final
                    })
                    
                    for col_idx in indices_bancos:
                        banco_original = str(row_bancos.iloc[col_idx]).strip()
                        
                        if banco_original.upper() in ['TOTAL SISTEMA', 'TOTAL']:
                            banco_modificado = MAPEO_TOTAL_SISTEMA.get(sigla_detectada, f"TS_{sigla_detectada}")
                        else:
                            banco_modificado = banco_original
                            
                        banco_limpio = limpiar_texto(banco_modificado)
                        
                        valor_raw = df_raw.iloc[fila_idx_proc, col_idx]
                        valor_num = pd.to_numeric(valor_raw, errors='coerce')
                        if pd.isna(valor_num): 
                            valor_num = 0.0
                        
                        if banco_limpio not in dict_entidades and id_grupo:
                            conn.execute(text("""
                                INSERT INTO entidades (nombre_entidad, id_grupo) VALUES (:e, :idg)
                                ON CONFLICT (nombre_entidad) DO NOTHING
                            """), {"e": banco_limpio, "idg": id_grupo})
                            
                            new_id = conn.execute(text("SELECT id_entidad FROM entidades WHERE nombre_entidad = :e"), {"e": banco_limpio}).fetchone()[0]
                            dict_entidades[banco_limpio] = new_id
                        
                        id_entidad = dict_entidades.get(banco_limpio)
                        if not id_entidad: 
                            continue
                        
                        registros_a_insertar_final.append({
                            "id_entidad": int(id_entidad),
                            "codigo_indicador": codigo_ind_corto,
                            "valor": float(valor_num),
                            "fecha_corte": fecha_corte
                        })
                
                if fin_notas_bloque > puntero_fila:
                    puntero_fila = fin_notas_bloque
                else:
                    puntero_fila += 1
            
            if not registros_a_insertar_final:
                return False, "No se pudieron aislar tramos secuenciales válidos."
                
            df_plan = pd.DataFrame(lista_plan_indicadores_final).drop_duplicates(subset=['codigo_indicador'])
            
            df_existentes = pd.read_sql("SELECT codigo_indicador, grupo_indicador, orden FROM plan_indicadores", conn)
            set_existentes = set(df_existentes['codigo_indicador'])
            
            max_orden_por_grupo = {}
            for _, fila_ext in df_existentes.iterrows():
                g_nom = fila_ext['grupo_indicador']
                o_val = fila_ext['orden'] if pd.notna(fila_ext['orden']) else 0
                if g_nom not in max_orden_por_grupo or o_val > max_orden_por_grupo[g_nom]:
                    max_orden_por_grupo[g_nom] = o_val

            for _, r in df_plan.iterrows():
                cod_ind = r['codigo_indicador']
                g_ind = r['grupo_indicador']
                nota_ind = r['notes_aclaratorias']
                
                if cod_ind in set_existentes:
                    conn.execute(text("""
                        UPDATE plan_indicadores 
                        SET notas_aclaratorias = CASE 
                            WHEN :fecha >= COALESCE((SELECT MAX(fecha_corte) FROM indicadores_financieros WHERE codigo_indicador = plan_indicadores.codigo_indicador), '1900-01-01'::date)
                            THEN :n 
                            ELSE notas_aclaratorias 
                        END
                        WHERE codigo_indicador = :c
                    """), {"c": cod_ind, "n": nota_ind, "fecha": fecha_corte})
                
                else:
                    if g_ind not in max_orden_por_grupo:
                        res_max = conn.execute(text("""
                            SELECT COALESCE(MAX(orden), 0) FROM plan_indicadores WHERE grupo_indicador = :g
                        """), {"g": g_ind}).fetchone()
                        max_orden_por_grupo[g_ind] = res_max[0] if res_max else 0
                    
                    nuevo_orden = max_orden_por_grupo[g_ind] + 1
                    max_orden_por_grupo[g_ind] = nuevo_orden
                    
                    conn.execute(text("""
                        INSERT INTO plan_indicadores (codigo_indicador, notas_aclaratorias, grupo_indicador, orden) 
                        VALUES (:c, :n, :g, :o)
                    """), {
                        "c": cod_ind, 
                        "n": nota_ind, 
                        "g": g_ind, 
                        "o": nuevo_orden
                    })
                    
                    set_existentes.add(cod_ind)

            df_ins = pd.DataFrame(registros_a_insertar_final)
            df_ins['id_entidad'] = df_ins['id_entidad'].astype(int)
            
            df_ins = df_ins.drop_duplicates(subset=['id_entidad', 'codigo_indicador', 'fecha_corte'], keep='first')
            
            entidades_ids = tuple(int(x) for x in df_ins['id_entidad'].unique())
            if len(entidades_ids) == 1:
                conn.execute(text("DELETE FROM indicadores_financieros WHERE fecha_corte = :f AND id_entidad = :id"), {"f": fecha_corte, "id": entidades_ids[0]})
            elif len(entidades_ids) > 1:
                conn.execute(text(f"DELETE FROM indicadores_financieros WHERE fecha_corte = :f AND id_entidad IN {entidades_ids}"), {"f": fecha_corte})
                
            df_ins.to_sql('indicadores_financieros', con=conn, if_exists='append', index=False)
            
        return True, f"🚀 Éxito relacional con salvaguarda cronológica activa: Indicadores y Total Sistema mapeados para {nombre_grupo_app}."
    except Exception as e:
        return False, f"Error en procesamiento de indicadores: {str(e)}"