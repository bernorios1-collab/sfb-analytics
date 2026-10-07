import requests
from bs4 import BeautifulSoup
import re

def obtener_indicadores_bcb():
    """
    Obtiene los indicadores vigentes de bcb.gob.bo de forma precisa.
    Retorna única y exclusivamente las opciones de Bs (Bolivianos) y USD (Dólares)
    si existe conectividad con el portal oficial del BCB.
    """
    url = "https://www.bcb.gob.bo/"
    # Inicializamos únicamente con la moneda base garantizada
    indicadores = {"Bs (Bolivianos)": 1.0}
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=8)
        
        if response.status_code != 200:
            return indicadores
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        def limpiar_valor(texto):
            if not texto:
                return None
            res = "".join(c for c in texto if c.isdigit() or c in [',', '.'])
            return float(res.replace(',', '.')) if res else None

        val_tc_oficial = None

        # ---------------------------------------------------------------------
        # EXTRACCIÓN EXCLUSIVA DEL TIPO DE CAMBIO OFICIAL (USD)
        # ---------------------------------------------------------------------
        nodo_tc = soup.find(string=re.compile(r'TIPO\s+DE\s+CAMBIO\s+OFICIAL', re.IGNORECASE))
        if nodo_tc:
            # Buscamos de forma continua en todos los elementos de texto siguientes
            for texto_siguiente in nodo_tc.find_all_next(string=True):
                txt_limpio = texto_siguiente.strip()
                # Buscamos el primer patrón numérico decimal (ej. 10.24 o 10,24)
                if txt_limpio and re.search(r'^\d+[\.,]\d+$', txt_limpio):
                    val_tc_oficial = limpiar_valor(txt_limpio)
                    if val_tc_oficial:
                        break

        # ---------------------------------------------------------------------
        # ARMADO DEL DICCIONARIO (Solo Bolivianos y Dólares)
        # ---------------------------------------------------------------------
        # La opción en dólares aparece única y exclusivamente si se extrajo el valor real del portal
        if val_tc_oficial:
            indicadores[f"USD (Dólares - Tipo de Cambio Oficial: {val_tc_oficial:.2f})"] = val_tc_oficial

        return indicadores

    except Exception:
        return indicadores