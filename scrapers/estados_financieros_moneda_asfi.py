import requests
import os
import streamlit as st
import zipfile
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

@st.cache_data(ttl=300)
def verificar_disponibilidad_moneda_asfi(sigla_url, sigla_file, periodo):
    anio, mes = periodo.split("-")
    nombre_zip = f"{anio}{mes}_{sigla_file}_EstadosFinancierosMoneda.zip"
    url = f"https://www.asfi.gob.bo/sites/default/files/estadisticaif/{sigla_url}/{anio}/{mes}/{nombre_zip}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=8, stream=True, verify=False)
        return response.status_code == 200
    except Exception:
        return False

def descargar_y_preparar_moneda_asfi(entidad, periodo, ruta_base):
    mapeo_asfi = {
        "Bancos Múltiples": ("bancos_multiples", "BMU"),
        "Bancos PYME": ("bancos_pymes", "BPY"),
        "Instituciones Financieras de Desarrollo": ("int_fin_des", "IFD"),
        "Bancos de Desarrollo Productivo": ("ban_des_pro", "BDR")
    }
    
    if entidad not in mapeo_asfi:
        return False, f"La entidad '{entidad}' no publica reporte por moneda."

    sigla_url, sigla_file = mapeo_asfi[entidad]
    anio, mes = periodo.split("-")
    nombre_zip = f"{anio}{mes}_{sigla_file}_EstadosFinancierosMoneda.zip"
    url = f"https://www.asfi.gob.bo/sites/default/files/estadisticaif/{sigla_url}/{anio}/{mes}/{nombre_zip}"
    zip_path = os.path.join(ruta_base, nombre_zip)
    
    try:
        if not os.path.exists(ruta_base): 
            os.makedirs(ruta_base, exist_ok=True)
            
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=30, verify=False)
        
        if response.status_code == 200:
            with open(zip_path, 'wb') as f:
                f.write(response.content)
            
            # Descompresión y extracción de datos
            zip_obj = zipfile.ZipFile(zip_path, 'r')
            try:
                archivos_excel = [f for f in zip_obj.namelist() if f.lower().endswith(('.xls', '.xlsx')) and not f.startswith('__MACOSX')]
                
                if archivos_excel:
                    for member in archivos_excel:
                        filename = os.path.basename(member)
                        if not filename:
                            continue
                        
                        source = zip_obj.open(member)
                        target_path = os.path.join(ruta_base, filename)
                        with open(target_path, "wb") as target:
                            target.write(source.read())
                        source.close()
                else:
                    zip_obj.extractall(ruta_base)
            finally:
                # Cierre forzado del manipulador de archivo ZIP
                zip_obj.close()

            # Borrado del ZIP ya procesado
            if os.path.exists(zip_path):
                try:
                    os.remove(zip_path)
                except Exception:
                    pass

            # Barrido preventivo para eliminar cualquier archivo .zip residual en el directorio
            for item in os.listdir(ruta_base):
                if item.lower().endswith('.zip'):
                    try:
                        os.remove(os.path.join(ruta_base, item))
                    except Exception:
                        pass

            return True, f"✅ {entidad} ({periodo}) descargado y extraído (ZIP eliminado) correctamente."
        else:
            return False, f"No se encontró el archivo en ASFI (Status: {response.status_code})."
    except Exception as e:
        return False, f"Error de conexión: {e}"