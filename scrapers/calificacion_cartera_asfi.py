import os
import requests
import zipfile

# Plantilla de URL oficial de la ASFI
URL_BASE = "https://www.asfi.gob.bo/sites/default/files/estadisticaif/{grupo_url}/{anio}/{mes}/{periodo_num}_{sigla}_CalificacionCartera.zip"

MAPEO_URL_CARTERA = {
    "Bancos Múltiples": ("bancos_multiples", "BMU"),
    "Bancos PYME": ("bancos_pymes", "BPY"),
    "Entidades Financieras de Vivienda": ("ent_fin_vivienda", "EFV"),
    "Cooperativas de Ahorro y Crédito": ("cooperativas", "COO"),
    "Instituciones Financieras de Desarrollo": ("int_fin_des", "IFD"),
    "Bancos de Desarrollo Productivo": ("ban_des_pro", "BDR")
}

def construir_url_cartera(entidad: str, periodo: str) -> str:
    """Construye la URL parametrizada para la descarga desde la ASFI."""
    anio, mes = periodo.split("-")
    grupo_url, sigla = MAPEO_URL_CARTERA[entidad]
    periodo_num = f"{anio}{mes}"
    return URL_BASE.format(grupo_url=grupo_url, anio=anio, mes=mes, periodo_num=periodo_num, sigla=sigla)

def verificar_disponibilidad_cartera(entidad: str, periodo: str) -> bool:
    """Verifica si el archivo comprimido existe en el servidor de la ASFI."""
    url = construir_url_cartera(entidad, periodo)
    try:
        r = requests.head(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        return r.status_code == 200
    except Exception:
        return False

def descargar_y_preparar_cartera(entidad: str, periodo: str, destino_folder: str) -> tuple[bool, str]:
    """Descarga el ZIP de ASFI y extrae ÚNICAMENTE el archivo Excel (.xls/.xlsx), descartando .ods o duplicados."""
    url = construir_url_cartera(entidad, periodo)
    os.makedirs(destino_folder, exist_ok=True)
    
    zip_path = os.path.join(destino_folder, f"temp_{periodo}.zip")
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return False, f"Error HTTP {r.status_code}"
            
        with open(zip_path, "wb") as f:
            f.write(r.content)
            
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Filtrar solo los archivos que terminan en .xls o .xlsx (excluyendo .ods)
            archivos_excel = [f for f in zip_ref.namelist() if f.lower().endswith(('.xls', '.xlsx'))]
            
            if not archivos_excel:
                os.remove(zip_path)
                return False, "No se encontró ningún archivo Excel (.xls/.xlsx) dentro del ZIP."
            
            # Extraer solo el archivo Excel relevante
            for archivo in archivos_excel:
                zip_ref.extract(archivo, destino_folder)
            
        if os.path.exists(zip_path):
            os.remove(zip_path)
            
        return True, "Archivo Excel extraído correctamente (descartados duplicados/ODS)."
    except Exception as e:
        if os.path.exists(zip_path):
            os.remove(zip_path)
        return False, f"Error en descarga: {e}"