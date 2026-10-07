import pandas as pd
import re
import os
from datetime import datetime
from sqlalchemy import text
from config_db import obtener_engine

FACTOR_ESCALA_EXCEL = 1000.0  # Convierte de "Miles de Bs" a "Bs exactos"

def limpiar_texto(t):
    if not isinstance(t, str): return str(t)
    r = {'á':'a','é':'e','í':'i','ó':'o','ú':'u','ñ':'n','Á':'A','É':'E','Í':'I','Ó':'O','Ú':'U','Ñ':'N'}
    for k, v in r.items(): t = t.replace(k, v)
    return t.strip().upper()

def limpiar_sigla(s):
    if not isinstance(s, str): return ""
    s_limpio = s.strip().upper()
    s_limpio = re.sub(r"['\"()\[\]]", "", s_limpio)
    return s_limpio.strip()

def extraer_fecha_corte(df: pd.DataFrame) -> str:
    meses = {
        "ENERO": "01", "FEBRERO": "02", "MARZO": "03", "ABRIL": "04",
        "MAYO": "05", "JUNIO": "06", "JULIO": "07", "AGOSTO": "08",
        "SEPTIEMBRE": "09", "OCTUBRE": "10", "NOVIEMBRE": "11", "DICIEMBRE": "12"
    }
    for r in range(min(10, len(df))):
        val = limpiar_texto(str(df.iloc[r, 0]))
        match = re.search(r'AL\s+(\d{1,2})\s+DE\s+([A-Z]+)\s+DE\s+(\d{4})', val)
        if match:
            dia, mes_str, anio = match.groups()
            if mes_str in meses:
                return f"{anio}-{meses[mes_str]}-{int(dia):02d}"
    raise ValueError("No se pudo extraer la fecha de corte en las primeras filas.")

def obtener_ids_catalogo(engine, nombre_grupo_interfaz: str) -> tuple[int, dict]:
    with engine.connect() as conn:
        q_grupo = text("""
            SELECT id_grupo FROM grupos_asfi 
            WHERE TRANSLATE(UPPER(nombre_grupo), 'ÁÉÍÓÚÑ', 'AEIOUN') = TRANSLATE(UPPER(:nombre), 'ÁÉÍÓÚÑ', 'AEIOUN')
            LIMIT 1
        """)
        res_g = conn.execute(q_grupo, {"nombre": nombre_grupo_interfaz}).fetchone()
        if not res_g:
            raise ValueError(f"No se encontró id_grupo para '{nombre_grupo_interfaz}'")
        id_grupo = res_g[0]

        q_ent = text("SELECT id_entidad, nombre_entidad, nombre_completo FROM entidades WHERE id_grupo = :id_grupo")
        res_e = conn.execute(q_ent, {"id_grupo": id_grupo}).fetchall()
        
        mapa_entidades = {}
        for row in res_e:
            id_e, sigla_e, nombre_comp = row[0], limpiar_sigla(row[1]), limpiar_texto(row[2] or "")
            if sigla_e:
                mapa_entidades[sigla_e] = id_e
            
            match_sigla_paren = re.search(r'\(([A-Z0-9]+)\)', nombre_comp)
            if match_sigla_paren:
                mapa_entidades[match_sigla_paren.group(1)] = id_e

            if "TOTAL SISTEMA" in nombre_comp or sigla_e.startswith("TS"):
                mapa_entidades["TOTAL SISTEMA"] = id_e

        return id_grupo, mapa_entidades

def procesar_archivo_calificacion(rutas_excel, grupo_interfaz: str) -> tuple[bool, str]:
    """Procesa uno o varios archivos Excel (ej. Parte A y Parte B para Cooperativas)."""
    try:
        if isinstance(rutas_excel, str):
            rutas_excel = [rutas_excel]

        engine = obtener_engine()
        id_grupo, mapa_entidades = obtener_ids_catalogo(engine, grupo_interfaz)

        mapa_filas = {
            "CATEGORÍA A": "categoria_a",
            "PREVISIÓN CONFORME A (2)": "prevision_a",
            "CATEGORÍA B": "categoria_b",
            "PREVISIÓN CONFORME A (3)": "prevision_b",
            "CATEGORÍA C": "categoria_c",
            "PREVISIÓN 20%": "prevision_c",
            "CATEGORÍA D": "categoria_d",
            "PREVISIÓN 50%": "prevision_d",
            "CATEGORÍA E": "categoria_e",
            "PREVISIÓN 80%": "prevision_e",
            "CATEGORÍA F": "categoria_f",
            "PREVISIÓN 100%": "prevision_f",
            "TOTAL CARTERA Y CONTINGENTE (4)": "total_cartera",
            "TOTAL PREVISIÓN ESPECÍFICA": "total_prevision",
            "PORCENTAJE": "porcentaje_participacion"
        }

        registros_acumulados = {}
        fecha_corte_global = None
        total_notas_acumuladas = []

        for ruta_excel in rutas_excel:
            if not os.path.exists(ruta_excel):
                continue
                
            xls = pd.ExcelFile(ruta_excel)
            df = pd.read_excel(xls, sheet_name=0, header=None)
            fecha_corte = extraer_fecha_corte(df)
            
            if not fecha_corte_global:
                fecha_corte_global = fecha_corte

            mapeo_columnas_validas = {}
            fila_siglas_idx = None

            for r_idx in range(min(12, len(df))):
                for c_idx in range(1, len(df.columns)):
                    val_celda = limpiar_sigla(str(df.iloc[r_idx, c_idx]))
                    if val_celda and val_celda in mapa_entidades:
                        mapeo_columnas_validas[c_idx] = mapa_entidades[val_celda]
                        if fila_siglas_idx is None:
                            fila_siglas_idx = r_idx

            if not mapeo_columnas_validas:
                continue

            if fila_siglas_idx is None:
                fila_siglas_idx = 5

            registros_archivo = {}
            for col_idx, id_entidad in mapeo_columnas_validas.items():
                registros_archivo[col_idx] = {
                    "id_entidad": id_entidad,
                    "id_grupo": id_grupo,
                    "fecha_corte": fecha_corte
                }

            fila_fin_datos = fila_siglas_idx + 13
            for idx in range(fila_siglas_idx + 1, min(len(df), fila_siglas_idx + 30)):
                etiqueta = limpiar_texto(str(df.iloc[idx, 0]))
                
                col_target = None
                for clave_mapa, col_bd in mapa_filas.items():
                    # Comparamos ambas partes normalizadas sin tildes para evitar errores
                    if limpiar_texto(clave_mapa) in etiqueta:
                        col_target = col_bd
                        break
                        
                if not col_target:
                    continue

                fila_fin_datos = max(fila_fin_datos, idx)
                for col_idx, datos_ent in registros_archivo.items():
                    val = df.iloc[idx, col_idx]
                    try:
                        monto_num = float(val) if pd.notnull(val) else 0.0
                        if col_target == "porcentaje_participacion":
                            registros_archivo[col_idx][col_target] = monto_num
                        else:
                            registros_archivo[col_idx][col_target] = monto_num * FACTOR_ESCALA_EXCEL
                    except ValueError:
                        registros_archivo[col_idx][col_target] = 0.0

            for col_idx, datos in registros_archivo.items():
                # Si ya existe la entidad en registros acumulados (por ejemplo, parte A), actualizamos sus campos
                id_ent = datos["id_entidad"]
                if id_ent not in registros_acumulados:
                    registros_acumulados[id_ent] = {
                        "id_entidad": id_ent,
                        "id_grupo": id_grupo,
                        "fecha_corte": fecha_corte
                    }
                
                for col_bd in mapa_filas.values():
                    if col_bd in datos:
                        registros_acumulados[id_ent][col_bd] = datos[col_bd]

            for idx in range(fila_fin_datos + 1, len(df)):
                texto_fila = str(df.iloc[idx, 0]).strip()
                match_nota = re.match(r'^\((\d+)\)\s*(.*)', texto_fila)
                if match_nota:
                    num_nota, texto_contenido = match_nota.groups()
                    nota_obj = {
                        "id_grupo": id_grupo,
                        "fecha_corte": fecha_corte,
                        "numero_nota": int(num_nota),
                        "texto_nota": texto_contenido
                    }
                    if nota_obj not in total_notas_acumuladas:
                        total_notas_acumuladas.append(nota_obj)

        if not fecha_corte_global:
            return False, "No se pudo determinar la fecha de corte en los archivos provistos."

        df_resultado = pd.DataFrame(list(registros_acumulados.values()))
        df_notas = pd.DataFrame(total_notas_acumuladas)

        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM calificacion_cartera WHERE fecha_corte = :fecha AND id_grupo = :grupo"),
                {"fecha": fecha_corte_global, "grupo": id_grupo}
            )
            conn.execute(
                text("DELETE FROM calificacion_notas WHERE fecha_corte = :fecha AND id_grupo = :grupo"),
                {"fecha": fecha_corte_global, "grupo": id_grupo}
            )
            
            if not df_resultado.empty:
                df_resultado.to_sql("calificacion_cartera", con=conn, if_exists="append", index=False)
                
            if not df_notas.empty:
                df_notas.to_sql("calificacion_notas", con=conn, if_exists="append", index=False)

        return True, f"Procesados con éxito {len(df_resultado)} entidades y {len(df_notas)} notas ({fecha_corte_global})."

    except Exception as e:
        return False, f"Error al procesar calificación: {str(e)}"