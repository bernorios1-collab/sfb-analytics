import pandas as pd
from sqlalchemy import text
import os, re, calendar
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

def procesar_archivo_ponderacion(ruta_completa, sigla_detectada, limpiar_previo=True):
    nombre_archivo = os.path.basename(ruta_completa)
    match = re.search(r'(\d{4})(\d{2})', nombre_archivo)
    if not match: 
        return False, "Fecha no detectada en el nombre del archivo de Activos Ponderados."
    
    gestion, mes = int(match.group(1)), int(match.group(2))
    fecha_corte = f"{gestion}-{mes:02d}-{calendar.monthrange(gestion, mes)[1]}"
    
    try:
        motor = 'xlrd' if ruta_completa.lower().endswith('.xls') else 'openpyxl'
        df_raw = pd.read_excel(ruta_completa, header=None, engine=motor)
        
        # 1. Detectar fila de bancos de forma dinámica
        fila_bancos = None
        indices_bancos = []
        for r_idx in range(min(10, len(df_raw))):
            row_test = df_raw.iloc[r_idx]
            temp_indices = []
            for idx in range(1, len(row_test)):
                banco_nom = str(row_test.iloc[idx]).strip()
                if banco_nom.upper() not in ['NAN', 'NONE', ''] and len(banco_nom) > 1:
                    temp_indices.append(idx)
            if len(temp_indices) >= 1:
                fila_bancos = r_idx
                indices_bancos = temp_indices
                break
                
        if fila_bancos is None or not indices_bancos:
            return False, "No se detectaron columnas de entidades."
            
        fila_datos_inicio = fila_bancos + 1
        row_bancos = df_raw.iloc[fila_bancos]
        
        # 2. Extraer notas al pie al final del documento
        diccionario_notas_globales = {}
        for r_idx in range(fila_datos_inicio, len(df_raw)):
            val_celda = df_raw.iloc[r_idx, 0]
            if pd.notna(val_celda):
                txt_c = str(val_celda).strip()
                match_nota_pie = re.match(r'^\s*\((\d+)\)\s+(.+)$', txt_c)
                if match_nota_pie:
                    num_n = f"({match_nota_pie.group(1)})"
                    texto_n = match_nota_pie.group(2).strip()
                    diccionario_notas_globales[num_n] = texto_n

        activos_riesgo_rows = []
        suficiencia_pat_rows = []
        ratios_rows = []
        
        conteo_activos = 0
        conteo_pat = 0
        conteo_ratios = 0

        with engine.begin() as conn:
            df_entidades_db = pd.read_sql("SELECT id_entidad, nombre_entidad FROM entidades", conn)
            dict_entidades = dict(zip(df_entidades_db['nombre_entidad'].apply(limpiar_texto), df_entidades_db['id_entidad']))
            
            nombre_grupo_app = MAPEO_SIGLAS.get(sigla_detectada, sigla_detectada)
            res_grupo = conn.execute(text("""
                SELECT id_grupo FROM grupos_asfi 
                WHERE TRANSLATE(UPPER(nombre_grupo), 'ÁÉÍÓÚÑ', 'AEIOUN') = :g
            """), {"g": limpiar_texto(nombre_grupo_app)}).fetchone()
            id_grupo = res_grupo[0] if res_grupo else None

            # Recorrer filas de datos
            for idx in range(fila_datos_inicio, len(df_raw)):
                glosa_raw = df_raw.iloc[idx, 0]
                if pd.isna(glosa_raw) or str(glosa_raw).strip() == "":
                    continue
                
                txt_glosa = str(glosa_raw).strip()
                
                if re.match(r'^\s*\((\d+)\)\s+', txt_glosa):
                    continue

                match_llamada = re.search(r'\s*(\(\d+\))\s*$', txt_glosa)
                token_nota = None
                texto_limpio = txt_glosa
                if match_llamada:
                    token_nota = match_llamada.group(1)
                    texto_limpio = txt_glosa[:match_llamada.start()].strip()

                nota_final = diccionario_notas_globales.get(token_nota, "") if token_nota else ""
                upper_glosa = texto_limpio.upper()

                tipo_bloque = None
                if "CATEGORIA" in upper_glosa or "TOTAL ACTIVO Y CONTINGENTE" in upper_glosa or "TOTAL ACTIVO COMPUTABLE" in upper_glosa:
                    tipo_bloque = "ACTIVO_RIESGO"
                elif "COEFICIENTE" in upper_glosa:
                    tipo_bloque = "RATIO"
                else:
                    tipo_bloque = "PATRIMONIO"

                es_tot = any(k in upper_glosa for k in ["TOTAL", "CAPITAL PRIMARIO DESPUÉS DE AJUSTES", "CAPITAL SECUNDARIO DESPUÉS DE AJUSTES", "CAPITAL REGULATORIO", "EXCEDENTE"])

                if tipo_bloque == "ACTIVO_RIESGO":
                    conteo_activos += 1
                    conn.execute(text("""
                        INSERT INTO plan_categorias_riesgo (descripcion_categoria, notas_aclaratorias, es_totalizador, orden)
                        VALUES (:d, :n, :t, :o)
                        ON CONFLICT (descripcion_categoria) DO UPDATE 
                        SET notas_aclaratorias = COALESCE(NULLIF(EXCLUDED.notas_aclaratorias, ''), plan_categorias_riesgo.notas_aclaratorias)
                    """), {"d": texto_limpio, "n": nota_final, "t": es_tot, "o": conteo_activos})
                    
                    id_cat = conn.execute(text("SELECT id_plan_cat FROM plan_categorias_riesgo WHERE descripcion_categoria = :d"), {"d": texto_limpio}).fetchone()[0]

                    for col_idx in indices_bancos:
                        banco_orig = str(row_bancos.iloc[col_idx]).strip()
                        banco_mod = MAPEO_TOTAL_SISTEMA.get(sigla_detectada, f"TS_{sigla_detectada}") if banco_orig.upper() in ['TOTAL SISTEMA', 'TOTAL'] else banco_orig
                        banco_limp = limpiar_texto(banco_mod)
                        
                        val = pd.to_numeric(df_raw.iloc[idx, col_idx], errors='coerce')
                        val_num = float(val) if not pd.isna(val) else 0.0

                        if banco_limp not in dict_entidades and id_grupo:
                            conn.execute(text("INSERT INTO entidades (nombre_entidad, id_grupo) VALUES (:e, :idg) ON CONFLICT (nombre_entidad) DO NOTHING"), {"e": banco_limp, "idg": id_grupo})
                            dict_entidades[banco_limp] = conn.execute(text("SELECT id_entidad FROM entidades WHERE nombre_entidad = :e"), {"e": banco_limp}).fetchone()[0]

                        id_ent = dict_entidades.get(banco_limp)
                        if id_ent:
                            activos_riesgo_rows.append({"id_entidad": int(id_ent), "id_plan_cat": int(id_cat), "valor": val_num, "fecha_corte": fecha_corte})

                elif tipo_bloque == "RATIO":
                    conteo_ratios += 1
                    conn.execute(text("""
                        INSERT INTO plan_ratios_regulatorios (codigo_ratio, notas_aclaratorias, orden)
                        VALUES (:c, :n, :o)
                        ON CONFLICT (codigo_ratio) DO UPDATE 
                        SET notas_aclaratorias = COALESCE(NULLIF(EXCLUDED.notas_aclaratorias, ''), plan_ratios_regulatorios.notas_aclaratorias)
                    """), {"c": texto_limpio, "n": nota_final, "o": conteo_ratios})

                    id_ratio = conn.execute(text("SELECT id_plan_ratio FROM plan_ratios_regulatorios WHERE codigo_ratio = :c"), {"c": texto_limpio}).fetchone()[0]

                    for col_idx in indices_bancos:
                        banco_orig = str(row_bancos.iloc[col_idx]).strip()
                        banco_mod = MAPEO_TOTAL_SISTEMA.get(sigla_detectada, f"TS_{sigla_detectada}") if banco_orig.upper() in ['TOTAL SISTEMA', 'TOTAL'] else banco_orig
                        banco_limp = limpiar_texto(banco_mod)
                        
                        val = pd.to_numeric(df_raw.iloc[idx, col_idx], errors='coerce')
                        val_num = float(val) if not pd.isna(val) else 0.0

                        if banco_limp not in dict_entidades and id_grupo:
                            conn.execute(text("INSERT INTO entidades (nombre_entidad, id_grupo) VALUES (:e, :idg) ON CONFLICT (nombre_entidad) DO NOTHING"), {"e": banco_limp, "idg": id_grupo})
                            dict_entidades[banco_limp] = conn.execute(text("SELECT id_entidad FROM entidades WHERE nombre_entidad = :e"), {"e": banco_limp}).fetchone()[0]

                        id_ent = dict_entidades.get(banco_limp)
                        if id_ent:
                            ratios_rows.append({"id_entidad": int(id_ent), "id_plan_ratio": int(id_ratio), "valor": val_num, "fecha_corte": fecha_corte})

                else:
                    conteo_pat += 1
                    seccion = "CAPITAL_PRIMARIO" if "PRIMARIO" in upper_glosa else ("CAPITAL_SECUNDARIO" if "SECUNDARIO" in upper_glosa else "GENERAL")
                    conn.execute(text("""
                        INSERT INTO plan_suficiencia_patrimonial (codigo_cuenta, seccion_cap, notas_aclaratorias, es_totalizador, orden)
                        VALUES (:c, :s, :n, :t, :o)
                        ON CONFLICT (codigo_cuenta) DO UPDATE 
                        SET notas_aclaratorias = COALESCE(NULLIF(EXCLUDED.notas_aclaratorias, ''), plan_suficiencia_patrimonial.notas_aclaratorias)
                    """), {"c": texto_limpio, "s": seccion, "n": nota_final, "t": es_tot, "o": conteo_pat})

                    id_cap = conn.execute(text("SELECT id_plan_cap FROM plan_suficiencia_patrimonial WHERE codigo_cuenta = :c"), {"c": texto_limpio}).fetchone()[0]

                    for col_idx in indices_bancos:
                        banco_orig = str(row_bancos.iloc[col_idx]).strip()
                        banco_mod = MAPEO_TOTAL_SISTEMA.get(sigla_detectada, f"TS_{sigla_detectada}") if banco_orig.upper() in ['TOTAL SISTEMA', 'TOTAL'] else banco_orig
                        banco_limp = limpiar_texto(banco_mod)
                        
                        val = pd.to_numeric(df_raw.iloc[idx, col_idx], errors='coerce')
                        val_num = float(val) if not pd.isna(val) else 0.0

                        if banco_limp not in dict_entidades and id_grupo:
                            conn.execute(text("INSERT INTO entidades (nombre_entidad, id_grupo) VALUES (:e, :idg) ON CONFLICT (nombre_entidad) DO NOTHING"), {"e": banco_limp, "idg": id_grupo})
                            dict_entidades[banco_limp] = conn.execute(text("SELECT id_entidad FROM entidades WHERE nombre_entidad = :e"), {"e": banco_limp}).fetchone()[0]

                        id_ent = dict_entidades.get(banco_limp)
                        if id_ent:
                            suficiencia_pat_rows.append({"id_entidad": int(id_ent), "id_plan_cap": int(id_cap), "valor": val_num, "fecha_corte": fecha_corte})

            # Limpiar datos previos del grupo solo si limpiar_previo es True (primer archivo)
            if id_grupo and limpiar_previo:
                conn.execute(text("""
                    DELETE FROM activos_riesgo_valores 
                    WHERE fecha_corte = :f AND id_entidad IN (SELECT id_entidad FROM entidades WHERE id_grupo = :idg)
                """), {"f": fecha_corte, "idg": id_grupo})
                
                conn.execute(text("""
                    DELETE FROM suficiencia_patrimonial_valores 
                    WHERE fecha_corte = :f AND id_entidad IN (SELECT id_entidad FROM entidades WHERE id_grupo = :idg)
                """), {"f": fecha_corte, "idg": id_grupo})
                
                conn.execute(text("""
                    DELETE FROM ratios_regulatorios_valores 
                    WHERE fecha_corte = :f AND id_entidad IN (SELECT id_entidad FROM entidades WHERE id_grupo = :idg)
                """), {"f": fecha_corte, "idg": id_grupo})

            if activos_riesgo_rows:
                pd.DataFrame(activos_riesgo_rows).drop_duplicates(subset=['id_entidad', 'id_plan_cat', 'fecha_corte']).to_sql('activos_riesgo_valores', con=conn, if_exists='append', index=False)
            if suficiencia_pat_rows:
                pd.DataFrame(suficiencia_pat_rows).drop_duplicates(subset=['id_entidad', 'id_plan_cap', 'fecha_corte']).to_sql('suficiencia_patrimonial_valores', con=conn, if_exists='append', index=False)
            if ratios_rows:
                pd.DataFrame(ratios_rows).drop_duplicates(subset=['id_entidad', 'id_plan_ratio', 'fecha_corte']).to_sql('ratios_regulatorios_valores', con=conn, if_exists='append', index=False)

        return True, f"🚀 Procesamiento modular exitoso para {nombre_grupo_app} ({fecha_corte}) [{nombre_archivo}]."
    except Exception as e:
        return False, f"Error en procesamiento modular ({nombre_archivo}): {str(e)}"