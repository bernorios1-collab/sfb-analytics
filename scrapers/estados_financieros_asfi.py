import requests
import os
import streamlit as st
import zipfile

@st.cache_data(ttl=3600)
def verificar_disponibilidad_asfi(sigla_url, sigla_file, periodo):
    anio, mes = periodo.split("-")
    nombre_zip = f"{anio}{mes}_{sigla_file}_EstadosFinancierosDesagregados.zip"
    url = f"https://www.asfi.gob.bo/sites/default/files/estadisticaif/{sigla_url}/{anio}/{mes}/{nombre_zip}"
    
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.head(url, headers=headers, timeout=10)
        return response.status_code == 200
    except:
        return False

def descargar_y_preparar_asfi(entidad, periodo, ruta_base):
    mapeo_asfi = {
        "Bancos Múltiples": ("bancos_multiples", "BMU"),
        "Bancos PYME": ("bancos_pymes", "BPY"),
        "Entidades Financieras de Vivienda": ("ent_fin_vivienda", "EFV"),
        "Cooperativas de Ahorro y Crédito": ("cooperativas", "COO"),  # Actualizado sin "Abiertas"
        "Instituciones Financieras de Desarrollo": ("int_fin_des", "IFD"),
        "Bancos de Desarrollo Productivo": ("ban_des_pro", "BDR")
    }
    
    sigla_url, sigla_file = mapeo_asfi[entidad]
    anio, mes = periodo.split("-")
    nombre_zip = f"{anio}{mes}_{sigla_file}_EstadosFinancierosDesagregados.zip"
    url = f"https://www.asfi.gob.bo/sites/default/files/estadisticaif/{sigla_url}/{anio}/{mes}/{nombre_zip}"
    
    try:
        if not os.path.exists(ruta_base): 
            os.makedirs(ruta_base, exist_ok=True)
            
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            zip_path = os.path.join(ruta_base, nombre_zip)
            with open(zip_path, 'wb') as f:
                f.write(response.content)
            
            try:
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(ruta_base)
                
                # Eliminar formatos redundantes (ej. .ods) y conservar solo Excel
                for archivo in os.listdir(ruta_base):
                    ruta_archivo = os.path.join(ruta_base, archivo)
                    if os.path.isfile(ruta_archivo):
                        if f"{anio}{mes}" in archivo and not archivo.lower().endswith(('.xls', '.xlsx', '.xlsm')):
                            try:
                                os.remove(ruta_archivo)
                            except:
                                pass

                # Eliminar el archivo ZIP de forma segura validando su existencia
                if os.path.exists(zip_path):
                    os.remove(zip_path)
                    
                return True, f"✅ {entidad} ({periodo}) descargado y preparado limpiamente."
            except Exception as ez:
                return False, f"Error al descomprimir ZIP: {ez}"
        else:
            return False, f"No se encontró el archivo en ASFI (Status: {response.status_code})."
    except Exception as e:
        return False, f"Error de conexión: {e}"