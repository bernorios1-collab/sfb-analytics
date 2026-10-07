import pandas as pd
from sqlalchemy import text
import os, re, calendar, unicodedata
from config_db import obtener_engine

engine = obtener_engine()

MAPEO_SIGLAS_MONEDA = {
    'BMU': 'Bancos Multiples', 
    'BPY': 'Bancos PYME', 
    'IFD': 'Instituciones Financieras de Desarrollo',
    'BDR': 'Bancos de Desarrollo Productivo'
}

def normalizar_texto(t):
    if not isinstance(t, str): return ""
    t = unicodedata.normalize('NFD', t).encode('ascii', 'ignore').decode("utf-8")
    t = re.sub(r'[^\w\s]', '', t)
    return " ".join(t.strip().upper().split())

limpiar_texto = normalizar_texto

# Mapa oficial ASFI para Inversiones Temporarias, Cartera, Pasivo y Estado de Resultados
MAPEO_ASFI_OFICIAL_RAW = {
    # ACTIVOS Y DISPONIBILIDADES
    "ACTIVO": "100.00",
    "DISPONIBILIDADES": "110.00",
    "CAJA": "111.00",
    "BANCO CENTRAL DE BOLIVIA": "112.00",
    "BANCOS Y CORRESPONSALES DEL PAIS": "113.00",
    "OFICINA MATRIZ Y SUCURSALES": "114.00",
    "BANCOS Y CORRESPONSALES DEL EXTERIOR": "115.00",
    "DOCUMENTOS DE COBRO INMEDIATO Y OTRAS OPERACIONES PENDIENTES DE LIQUIDACION": "117.00",
    "PRODUCTOS DEVENGADOS POR COBRAR DISPONIBILIDADES": "118.00",
    "PREVISION PARA DISPONIBILIDADES": "119.00",
    
    # INVERSIONES TEMPORARIAS (120.00)
    "INVERSIONES TEMPORARIAS": "120.00",
    "INVERSIONES EN EL BANCO CENTRAL DE BOLIVIA": "121.00",
    "INVERSIONES EN ENTIDADES FINANCIERAS DEL PAIS": "122.00",
    "INVERSIONES EN ENTIDADES FINANCIERAS DEL EXTERIOR": "123.00",
    "INVERSIONES EN ENTIDADES PUBLICAS NO FINANCIERAS DEL PAIS": "124.00",
    "INVERSIONES EN OTRAS ENTIDADES NO FINANCIERAS": "125.00",
    "INVERSIONES DE DISPONIBILIDAD RESTRINGIDA": "127.00",
    "PRODUCTOS DEVENGADOS POR COBRAR INVERSIONES TEMPORARIAS": "128.00",
    "(PREVISION PARA INVERSIONES TEMPORARIAS)": "129.00",

    # CARTERA (130.00)
    "CARTERA": "130.00",
    "CARTERA VIGENTE TOTAL": "131.00",
    "CARTERA VIGENTE": "131.01",
    "CARTERA REPROGRAMADA O REESTRUCTURADA VIGENTE": "131.02",
    "CARTERA VENCIDA TOTAL": "133.00",
    "CARTERA VENCIDA": "133.01",
    "CARTERA REPROGRAMADA O REESTRUCTURADA VENCIDA": "133.02",
    "CARTERA EJECUCION TOTAL": "134.00",
    "CARTERA EN EJECUCION": "134.01",
    "CARTERA REPROGRAMADA O REESTRUCTURADA EN EJECUCION": "134.02",
    "PRODUCTOS DEVENGADOS POR COBRAR CARTERA": "138.00",
    "PRODUCTOS DEVENGADOS POR COBRAR CARTERA VIGENTE": "138.01",
    "PRODUCTOS DEVENGADOS POR COBRAR CARTERA REPROGRAMADA O REESTRUCTURADA VIGENTE": "138.02",
    "PRODUCTOS DEVENGADOS POR COBRAR CARTERA VENCIDA": "138.03",
    "PRODUCTOS DEVENGADOS POR COBRAR CARTERA REPROGRAMADA O REESTRUCTURADA VENCIDA": "138.04",
    "PRODUCTOS DEVENGADOS POR COBRAR CARTERA EN EJECUCION": "138.05",
    "PRODUCTOS DEVENGADOS POR COBRAR CARTERA REPROGRAMADA O REESTRUCTURADA EJECUCION": "138.06",
    "(PREVISION PARA INCOBRABILIDAD DE CARTERA)": "139.00",
    "PREVISION GENERICA POR EXCESO AL LIMITE DE OPERACIONES DE CONSUMO NO DEBIDAMENTE GARANTIZADAS": "139.11",
    "(PREVISION GENERICA POR EXCESO AL LIMITE DE OPERACIONES DE CONSUMO NO DEBIDAMENTE GARANTIZADAS)": "139.11",

    "OTRAS CUENTAS POR COBRAR": "140.00",
    "BIENES REALIZABLES": "150.00",
    "INVERSIONES PERMANENTES": "160.00",
    "BIENES DE USO": "170.00",
    "OTROS ACTIVOS": "180.00",
    "FIDEICOMISOS CONSTITUIDOS": "190.00",

    # PASIVOS (200.00) Y CAPTACIONES
    "PASIVO": "200.00",
    "OBLIGACIONES CON EL PUBLICO": "210.00",
    "OBLIGACIONES CON EL PUBLICO A LA VISTA": "211.00",
    "OBLIGACIONES CON EL PUBLICO POR CUENTAS DE AHORROS": "212.00",
    "OBLIGACIONES CON EL PUBLICO A PLAZO": "213.00",
    "DEPOSITOS A PLAZO FIJO HASTA 30 DIAS": "213.01",
    "DEPOSITOS A PLAZO FIJO A 30 DIAS": "213.01",
    "DEPOSITOS A PLAZO FIJO DE 31 A 60 DIAS": "213.02",
    "DEPOSITOS A PLAZO FIJO DE 61 A 90 DIAS": "213.03",
    "DEPOSITOS A PLAZO FIJO DE 91 A 180 DIAS": "213.04",
    "DEPOSITOS A PLAZO FIJO DE 181 A 360 DIAS": "213.05",
    "DEPOSITOS A PLAZO FIJO DE 361 A 720 DIAS": "213.06",
    "DEPOSITOS A PLAZO FIJO DE 721 A 1080 DIAS": "213.07",
    "DEPOSITOS A PLAZO FIJO MAYOR A 1080 DIAS": "213.08",
    "OBLIGACIONES CON EL PUBLICO RESTRINGIDAS": "214.00",
    "OBLIGACIONES CON EL PUBLICO A PLAZO FIJO CON ANOTACION EN CUENTA": "215.00",
    "CARGOS DEVENGADOS POR PAGAR OBLIGACIONES CON EL PUBLICO": "218.00",
    "OBLIGACIONES CON INSTITUCIONES FISCALES": "220.00",
    "OBLIGACIONES CON EMPRESAS PUBLICAS": "230.00",
    "CARGOS DEVENGADOS POR PAGAR CON EMPRESAS PUBLICAS": "238.00",
    "OBLIGACIONES CON BANCOS Y ENTIDADES DE FINANCIAMIENTO": "240.00",
    "CARGOS DEVENGADOS POR PAGAR OBLIGACIONES CON BANCOS Y ENT DE FINANCIAMIENTO": "248.00",
    "OTRAS CUENTAS POR PAGAR": "250.00",
    "PREVISIONES": "260.00",
    "PREV GENERICAS VOLUNT PARA PERDIDAS FUTURAS AUN NO IDENTIF": "253.00",
    "PREVISIONES GENERICAS VOLUNTARIAS PARA PERDIDAS FUTURAS AUN NO IDENTIFICADAS": "253.00",
    "VALORES EN CIRCULACION": "270.00",
    "OBLIGACIONES SUBORDINADAS": "280.00",
    "OBLIGSUBORDIN INSTRUMENTADAS MEDIANTE CONTRATO DE PRESTAMO": "271.00",
    "OBLIG SUBORDINADAS CON PROGRAMAS GUBERNAMENTALES DE APOYO AL SISTEMA FINANCIERO": "271.01",
    "OTRAS OBLIGSUBORDINADAS INSTRUMENTADAS MEDIANTE CONTRATO DE PRESTAMO": "271.99",

    # PATRIMONIO (300.00)
    "PATRIMONIO": "300.00",
    "CAPITAL SOCIAL": "310.00",
    "APORTES NO CAPITALIZADOS": "320.00",
    "AJUSTES AL PATRIMONIO": "330.00",
    "RESERVAS": "340.00",
    "RESULTADOS ACUMULADOS": "350.00",
    "UTILIDADES PERDIDAS ACUMULADAS": "351.00",
    "UTILIDADES ACUMULADAS": "351.00",
    "PERDIDAS ACUMULADAS": "353.00",
    "UTILIDADES PERDIDAS DEL PERIODO O GESTION": "352.00",
    "UTILIDADES DEL PERIODO O GESTION": "352.00",
    "PERDIDAS DEL PERIODO O GESTION": "354.00",
    "PASIVO PATRIMONIO": "C00.20",
    "PASIVO Y PATRIMONIO": "C00.20",

    # CUENTAS CONTINGENTES Y DE ORDEN
    "CUENTAS CONTINGENTES DEUDORAS": "600.00",
    "CUENTAS DE ORDEN DEUDORAS": "700.00",
    "ADMIN DE TRASPASO DE CTAS DE ENCAJE LEGAL DE ENT DE INTERM FINANC": "824.00",
    "ADMINISTRACION DE TRASPASO DE CUENTAS DE ENCAJE LEGAL DE ENTIDADES DE INTERMEDIACION FINANCIERA": "824.00",
    "CUENTAS DE REGISTRO DIVERSAS": "869.00",

    # PATRIMONIOS AUTÓNOMOS - RECURSOS PRIVADOS (GRUPO 870)
    "CUENTAS DEUDORAS DE LOS PATRIMONIOS AUTONOMOS CONSTITUIDOS CON RECURSOS PRIVADOS": "870.00",

    # PATRIMONIOS AUTÓNOMOS - RECURSOS DEL ESTADO (GRUPO 880)
    "CUENTAS DEUDORAS DE LOS PATRIMONIOS AUTONOMOS CONSTITUIDOS CON RECURSOS DEL ESTADO": "880.00",

    # ESTADO DE RESULTADOS
    "INGRESOS FINANCIEROS": "510.00",
    "PRODUCTOS DE CARTERA VIGENTE": "513.01",
    "PRODUCTOS DE CARTERA VENCIDA": "513.02",
    "PRODUCTOS DE CARTERA EN EJECUCION": "513.03",
    "GASTOS FINANCIEROS": "410.00",
    "RESULTADO FINANCIERO BRUTO": "CC0.00",
    "OTROS INGRESOS OPERATIVOS": "540.00",
    "ABONOS POR DIFERENCIA DE CAMBIO": "521.00",
    "ABONOS POR MANTENIMIENTO DE VALOR": "522.00",
    "DISMINPREV CART PREVGENEXCLIMCONSNO DEBGARANT PREV GENCICLICA Y OTCTAS PCOB": "532.00",
    "DISMIN PREV CART PREV GEN EXC LIM CONS NO DEB GARANT PREV GEN CICLICA Y OT CTAS P COB": "532.00",
    "OTROS GASTOS OPERATIVOS": "430.00",
    "CARGOS POR DIFERENCIA DE CAMBIO": "421.00",
    "CARGOS POR MANTENIMIENTO DE VALOR": "422.00",
    "PERDPINCOBCRED PREV GENCICLICA PREVGENEXCLIMCONSNO DEBGARANT Y OTCTAS PCOB": "431.00",
    "PERD PINCOB CRED PREV GEN CICLICA PREV GEN EXC LIM CONS NO DEB GARANT Y OT CTAS P COB": "431.00",
    "RESULTADO DE OPERACION BRUTO": "CC0.01",
    "RESULTADO OPERATIVO BRUTO": "CC0.01",
    "RESULTADO DE OPERACION DESPUES DE INCOBRABLES": "CC0.02",
    "GASTOS DE ADMINISTRACION": "440.00",
    "RESULTADO DE OPERACION NETO": "CC0.03",
    "RESULTADO DESPUES DE AJUSTE POR DIFERENCIA DE CAMBIO Y MANTENIMIENTO DE VALOR": "CC0.04",
    "INGRESOS GASTOS EXTRAORDINARIOS": "570.00",
    "RESULTADO NETO DEL EJERCICIO ANTES DE AJUSTES DE GESTIONES ANTERIORES": "CC0.05",
    "RESULTADO DE OPERACION ANTES DE AJUSTES DE GESTIONES ANTERIORES": "CC0.05",
    "INGRESOS GASTOS DE GESTIONES ANTERIORES": "580.00",
    "RESULTADO ANTES DE IMPUESTOS Y AJUSTE CONTABLE POR EFECTO DE INFLACION": "CC0.06",
    "RESULTADO ANTES DE IMPUESTOS Y AJUSTE CONTABLE POR EFECTO DE LA INFLACION": "CC0.06",
    "AJUSTE CONTABLE POR EFECTO DE LA INFLACION": "499.00",
    "AJUSTE CONTABLE POR EFECTO DE INFLACION": "499.00",
    "RESULTADO ANTES DE IMPUESTOS": "CC0.08",
    "RESULTADO NETO DE LA GESTION": "CC0.07"
}

# Mapa específico exclusivo para INVERSIONES PERMANENTES (160.00)
MAPEO_PERMANENTES_RAW = {
    "INVERSIONES EN EL BANCO CENTRAL DE BOLIVIA": "161.00",
    "INVERSIONES EN ENTIDADES FINANCIERAS DEL PAIS": "162.00",
    "INVERSIONES EN ENTIDADES FINANCIERAS DEL EXTERIOR": "163.00",
    "INVERSIONES EN ENTIDADES PUBLICAS NO FINANCIERAS DEL PAIS": "164.00",
    "PARTICIPACION EN ENTIDADES FINANCIERAS Y AFINES": "165.00",
    "INVERSIONES EN OTRAS ENTIDADES NO FINANCIERAS": "166.00",
    "INVERSIONES DE DISPONIBILIDAD RESTRINGIDA": "167.00",
    "PRODUCTOS DEVENGADOS POR COBRAR INVERSIONES PERMANENTES": "168.00",
    "PREVISION PARA INVERSIONES PERMANENTES": "169.00",
    "(PREVISION PARA INVERSIONES PERMANENTES)": "169.00"
}

# Indexación normalizada
MAPEO_ASFI_OFICIAL = {normalizar_texto(k): v for k, v in MAPEO_ASFI_OFICIAL_RAW.items()}
MAPEO_PERMANENTES = {normalizar_texto(k): v for k, v in MAPEO_PERMANENTES_RAW.items()}

def calcular_nivel(texto_raw):
    if not isinstance(texto_raw, str): return 3
    espacios = len(texto_raw) - len(texto_raw.lstrip())
    if espacios in [0, 1]: return 1
    elif espacios <= 3: return 2
    elif espacios <= 6: return 3
    elif espacios <= 8: return 4
    else: return 5

def cargar_plan_cuentas_db_dict():
    try:
        df_plan = pd.read_sql("SELECT codigo_cuenta, descripcion_cuenta FROM plan_cuentas", engine)
        plan_dict = {}
        for _, r in df_plan.iterrows():
            cod_candidate = str(r['codigo_cuenta']).strip()
            if len(cod_candidate) <= 20 and not cod_candidate.startswith('0.'):
                norm = normalizar_texto(r['descripcion_cuenta'])
                if norm and norm not in plan_dict:
                    plan_dict[norm] = cod_candidate
        return plan_dict
    except Exception:
        return {}

def procesar_archivo_moneda_especifico(ruta_completa):
    nombre_archivo = os.path.basename(ruta_completa)
    match = re.search(r'(\d{4})(\d{2})', nombre_archivo)
    if not match: return False, "Fecha no detectada en el nombre del archivo."
    
    gestion, mes = int(match.group(1)), int(match.group(2))
    fecha_corte = f"{gestion}-{mes:02d}-{calendar.monthrange(gestion, mes)[1]}"
    
    sigla_archivo = next((s for s in MAPEO_SIGLAS_MONEDA if s in nombre_archivo.upper()), None)
    if not sigla_archivo: return False, "Sigla de grupo no reconocida."
    nombre_grupo_app = MAPEO_SIGLAS_MONEDA[sigla_archivo]

    try:
        motor = 'xlrd' if ruta_completa.endswith('.xls') else 'openpyxl'
        df_raw = pd.read_excel(ruta_completa, header=None, engine=motor)

        dict_plan_db = cargar_plan_cuentas_db_dict()

        fila_datos = 6
        data_list = []
        codigos_usados = set()
        padres_por_nivel = {}
        seccion_activa = ""

        for i in range(fila_datos, len(df_raw)):
            raw_text = df_raw.iloc[i, 0]
            if pd.isna(raw_text) or str(raw_text).strip().upper() in ['NAN', 'NONE', '']:
                continue

            desc_raw_str = str(raw_text).strip()
            desc_limpia = re.sub(r'\s+', ' ', desc_raw_str).upper()
            desc_norm = normalizar_texto(desc_raw_str)
            nivel = calcular_nivel(str(raw_text))

            # Detectar cambio de sección activa
            if desc_norm in ["INVERSIONES TEMPORARIAS", "12000"]:
                seccion_activa = "120.00"
            elif desc_norm in ["INVERSIONES PERMANENTES", "16000"]:
                seccion_activa = "160.00"
            elif desc_norm in ["BIENES DE USO", "17000"]:
                seccion_activa = "170.00"
            elif desc_norm in ["PASIVO", "20000"]:
                seccion_activa = "200.00"
            elif desc_norm in ["CUENTAS DEUDORAS DE LOS PATRIMONIOS AUTONOMOS CONSTITUIDOS CON RECURSOS PRIVADOS", "87000"]:
                seccion_activa = "870.00"
            elif desc_norm in ["CUENTAS DEUDORAS DE LOS PATRIMONIOS AUTONOMOS CONSTITUIDOS CON RECURSOS DEL ESTADO", "88000"]:
                seccion_activa = "880.00"

            # Determinar código base evaluando reglas de contexto
            codigo_base = None
            
            if seccion_activa == "160.00" and desc_norm in MAPEO_PERMANENTES:
                codigo_base = MAPEO_PERMANENTES[desc_norm]
            elif seccion_activa == "870.00" and desc_norm in ["ACTIVOS DE LOS PATRIMONIOS AUTONOMOS"]:
                codigo_base = "870.00.01"
            elif seccion_activa == "870.00" and desc_norm in ["GASTOS", "GASTOS DE LOS PATRIMONIOS AUTONOMOS"]:
                codigo_base = "879.00"
            elif seccion_activa == "880.00" and desc_norm in ["ACTIVOS DE LOS PATRIMONIOS AUTONOMOS"]:
                codigo_base = "880.00.01"
            elif seccion_activa == "880.00" and desc_norm in ["GASTOS", "GASTOS DE LOS PATRIMONIOS AUTONOMOS"]:
                codigo_base = "889.00"
            elif desc_norm in MAPEO_ASFI_OFICIAL:
                codigo_base = MAPEO_ASFI_OFICIAL[desc_norm]
            elif desc_norm in dict_plan_db:
                codigo_base = dict_plan_db[desc_norm]
            else:
                codigo_padre = padres_por_nivel.get(nivel - 1, "100.00")
                if codigo_padre.startswith('0.'):
                    codigo_padre = "100.00"
                codigo_base = codigo_padre

            if len(codigo_base) > 15:
                codigo_base = codigo_base[:15]

            # Garantizar unicidad de códigos
            codigo_final = codigo_base
            sufijo = 1
            while codigo_final in codigos_usados:
                codigo_final = f"{codigo_base}.{sufijo:02d}"
                if len(codigo_final) > 20:
                    codigo_final = codigo_final[:20]
                sufijo += 1

            codigos_usados.add(codigo_final)
            padres_por_nivel[nivel] = codigo_final

            m_mn = pd.to_numeric(df_raw.iloc[i, 1], errors='coerce')
            m_me = pd.to_numeric(df_raw.iloc[i, 2], errors='coerce')
            m_mnmv = pd.to_numeric(df_raw.iloc[i, 3], errors='coerce')
            m_mnufv = pd.to_numeric(df_raw.iloc[i, 4], errors='coerce')
            m_total = pd.to_numeric(df_raw.iloc[i, 5], errors='coerce')

            data_list.append({
                'codigo_cuenta': codigo_final,
                'descripcion_cuenta': desc_limpia,
                'nivel': nivel,
                'monto_mn': m_mn if not pd.isna(m_mn) else 0.0,
                'monto_me': m_me if not pd.isna(m_me) else 0.0,
                'monto_mnmv': m_mnmv if not pd.isna(m_mnmv) else 0.0,
                'monto_mnufv': m_mnufv if not pd.isna(m_mnufv) else 0.0,
                'monto_total': m_total if not pd.isna(m_total) else 0.0
            })

        df_final = pd.DataFrame(data_list)
        if df_final.empty: return False, "El archivo no contiene datos procesables."

        with engine.begin() as conn:
            # 1. Registrar cuentas en plan_cuentas_moneda
            plan_moneda = df_final[['codigo_cuenta', 'descripcion_cuenta', 'nivel']].drop_duplicates(subset=['codigo_cuenta'])
            for _, r in plan_moneda.iterrows():
                conn.execute(text("""
                    INSERT INTO plan_cuentas_moneda (codigo_cuenta, descripcion_cuenta, nivel)
                    VALUES (:c, :d, :n)
                    ON CONFLICT (codigo_cuenta) DO UPDATE SET descripcion_cuenta = EXCLUDED.descripcion_cuenta
                """), {"c": r['codigo_cuenta'], "d": r['descripcion_cuenta'], "n": r['nivel']})

            # 2. Obtener id_grupo de grupos_asfi
            res_grupo = conn.execute(text("""
                SELECT id_grupo FROM grupos_asfi 
                WHERE TRANSLATE(UPPER(nombre_grupo), 'ÁÉÍÓÚÑ', 'AEIOUN') = :g
            """), {"g": normalizar_texto(nombre_grupo_app)}).fetchone()
            
            if not res_grupo: return False, f"Grupo '{nombre_grupo_app}' no encontrado en DB."
            id_grupo = res_grupo[0]

            # 3. Validar si ya existen registros cargados para esa fecha
            check = conn.execute(text("""
                SELECT COUNT(*) FROM estados_financieros_moneda
                WHERE fecha_corte = :f AND id_grupo = :idg
            """), {"f": fecha_corte, "idg": id_grupo}).scalar()

            if check > 0:
                return False, f"⚠️ Datos de moneda ya existentes para {nombre_grupo_app} en {fecha_corte}."

            # 4. Insertar saldos en estados_financieros_moneda
            df_to_db = df_final[['codigo_cuenta', 'monto_mn', 'monto_me', 'monto_mnmv', 'monto_mnufv', 'monto_total']].copy()
            df_to_db['id_grupo'] = id_grupo
            df_to_db['fecha_corte'] = fecha_corte

            df_to_db.to_sql('estados_financieros_moneda', conn, if_exists='append', index=False)

        return True, f"Éxito: EEFF por Moneda ({nombre_grupo_app} - {fecha_corte}) cargados correctamente con contexto ASFI."
    except Exception as e:
        return False, f"Error en el procesamiento: {str(e)}"