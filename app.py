import os
import sys

root_path = os.path.dirname(os.path.abspath(__file__))
if root_path not in sys.path:
  sys.path.insert(0, root_path)

import streamlit as st
from streamlit_option_menu import option_menu

from config_db import inicializar_tabla_usuarios

# Inicializar tabla de usuarios en BD al arrancar
try:
  inicializar_tabla_usuarios()
except Exception as e:
  pass

st.set_page_config(page_title="SFB Analytics", page_icon="🏦", layout="wide")

# --- INICIALIZAR VARIABLES DE SESIÓN ---
if "usuario_autenticado" not in st.session_state:
  st.session_state.usuario_autenticado = False
  st.session_state.nivel_usuario = "free"
  st.session_state.nombre_usuario = "Invitado"

try:
  from Auditoria.auditoria_activos_ponderados_CAP import (
      mostrar_modulo_auditoria_ponderacion,
  )
  from paginas.analizador_cartera import mostrar_analizador_cartera
  from paginas.calificacion_grupo import mostrar_calificacion_grupo
  from paginas.calidad_activos_grupo import mostrar_calidad_activos_grupo
  from paginas.comportamiento_calificacion import (
      mostrar_comportamiento_calificacion,
  )
  from paginas.comportamiento_cuentas import mostrar_comportamiento
  from paginas.comportamiento_cuentas_moneda import (
      mostrar_comportamiento_moneda,
  )
  from paginas.comportamiento_indicadores import (
      mostrar_comportamiento_indicadores,
  )
  from paginas.comportamiento_ponderacion import (
      mostrar_comportamiento_ponderacion,
  )
  from paginas.EEFFGrupoEntidad import mostrar_eeff_grupo
  from paginas.entidades import mostrar_entidades
  from paginas.explorador import mostrar_explorador
  from paginas.explorador_calificacion import mostrar_explorador_calificacion
  from paginas.explorador_moneda import mostrar_explorador_moneda
  from paginas.explorador_ponderacion import mostrar_explorador_ponderacion
  from paginas.gestion_usuarios import mostrar_gestion_usuarios
  from paginas.gestor_datos import mostrar_gestor_datos
  from paginas.gestor_datos_calificacion import mostrar_gestor_calificacion
  from paginas.gestor_datos_moneda import mostrar_gestor_datos_moneda
  from paginas.gestor_datos_ponderacion import mostrar_gestor_ponderacion
  from paginas.gestor_indicadores import mostrar_gestor_indicadores
  from paginas.grupos import mostrar_grupos
  from paginas.IIFFGrupoEntidad import mostrar_iiff_grupo
  from paginas.indicadores_entidad import mostrar_iiff_entidad
  from paginas.inicio import mostrar_inicio
  from paginas.monitor_dolarizacion import mostrar_monitor_dolarizacion
  from paginas.ponderacionCAP_grupo import mostrar_ponderacion_grupo
  from paginas.ranking_carterabruta import mostrar_ranking_cartera
  from paginas.ranking_indicadormora import mostrar_ranking_mora
  from paginas.reporte_topn_carterabruta import mostrar_reporte_topn_cartera
except Exception as e:
  st.error(f"Error cargando módulos: {e}")

if "sub_seleccion" not in st.session_state:
  st.session_state.sub_seleccion = "Inicio"
if "menu_abierto" not in st.session_state:
  st.session_state.menu_abierto = "🏠 Bienvenida"

JERARQUIA = {
    "🏠 Bienvenida": ["Inicio"],
    "📊 Información a Corte": [
        "Estados Financieros por Entidad",
        "Estados Financieros por Grupo",
        "Estados Financieros por Moneda",
        "Calificación de Cartera y Contingente por Entidad",
        "Calificación de Cartera y Contingente por Grupo",
        "Indicadores Financieros por Entidad",
        "Indicadores Financieros por Grupo",
        "Ponderación de Activos y CAP por Entidad",
        "Ponderación de Activos y CAP por Grupo",
    ],
    "📈 Comportamiento Histórico": [
        "Estados Financieros por Entidad",
        "Estados Financieros por Moneda",
        "Calificación de Cartera y Contingente por Entidad",
        "Indicadores Financieros por Entidad",
        "Ponderación de Activos y CAP",
    ],
    "🔀 Otros Análisis": [
        "Monitor de Dolarización y R. Cambiario",
        "Ranking de Cartera Bruta",
        "Ranking de Indicador de Morosidad",
        "Analizador Detallado de Cartera",
        "Reporte Top N Cartera Bruta",
        "Calidad de Activos por Grupo",
    ],
    "📂 Gestión y Carga de Datos": [
        "EEFF Desagregados",
        "EEFF por Moneda",
        "Calificación de Cartera y Contingente",
        "Indicadores Financieros",
        "Ponderación de Activos y CAP",
        "PAFs y Empleados",
    ],
    "🏛️ Administración": [
        "Grupos de Entidades",
        "Entidades Financieras",
        "Control de Usuarios",
    ],
    "🔍 Auditoría": ["Auditoria - Ponderación de Activos y CAP"],
}

st.markdown(
    """
    <style>
        [data-testid="stSidebarNav"] {display: none;}
        [data-testid="stSidebar"] div.stButton > button {
            text-align: left !important;
            justify-content: flex-start !important;
            width: 100% !important;
            padding-left: 15px !important;
        }
        [data-testid="stSidebar"] div.stButton > button p {
            text-align: left !important;
        }
        .nav-link { text-align: left !important; padding-left: 25px !important; }
    </style>
""",
    unsafe_allow_html=True,
)


# --- FUNCIÓN DE VERIFICACIÓN DE PERMISOS ---
def validar_acceso_modulo(macro, op=None):
  nivel = st.session_state.get("nivel_usuario", "free")

  # El administrador tiene acceso absoluto a todo
  if nivel == "admin":
    return True

  # 1. Bienvenida e Información a Corte (Accesible para Free, Premium, Ultra)
  if macro in ["🏠 Bienvenida", "📊 Información a Corte"]:
    return True

  # 2. Comportamiento Histórico (Requiere al menos nivel Premium)
  if macro == "📈 Comportamiento Histórico":
    return nivel in ["premium", "ultra"]

  # 3. Otros Análisis (Requiere nivel Ultra)
  if macro == "🔀 Otros Análisis":
    return nivel == "ultra"

  # 4. Gestión de Datos, Administración y Auditoría (Exclusivo Administrador)
  if macro in ["📂 Gestión y Carga de Datos", "🏛️ Administración", "🔍 Auditoría"]:
    return False

  return False


with st.sidebar:
  # --- CONTROL DE SESIÓN Y USUARIO AL MISMO NIVEL ARRIBA DEL LOGOTIPO ---
  if st.session_state.usuario_autenticado:
    col_info, col_btn = st.columns([0.68, 0.32], vertical_alignment="center")

    with col_info:
      st.markdown(
          f"<p style='font-size: 11.5px; margin: 0; line-height: 1.2;'>👤"
          f" <b>{st.session_state.nombre_usuario}</b><br><span"
          f" style='color: #0066cc; font-weight: bold;'>{st.session_state.nivel_usuario.upper()}</span></p>",
          unsafe_allow_html=True,
      )

    with col_btn:
      if st.button("Salir", key="btn_logout_mini", use_container_width=True):
        st.session_state.usuario_autenticado = False
        st.session_state.nivel_usuario = "free"
        st.session_state.nombre_usuario = "Invitado"
        st.session_state.menu_abierto = "🏠 Bienvenida"
        st.session_state.sub_seleccion = "Inicio"
        st.rerun()

    st.markdown(
        "<hr style='margin: 8px 0 12px 0; border-color: rgba(128,128,128,0.3);'>",
        unsafe_allow_html=True,
    )

  st.image("imagenes/logotipo.png", use_container_width=True)
  st.markdown("---")

  # Menú de navegación condicional
  if st.session_state.usuario_autenticado:
    for macro, subs in JERARQUIA.items():
      # Ocultar secciones exclusivas de Admin para usuarios comunes
      if (
          macro
          in [
              "📂 Gestión y Carga de Datos",
              "🏛️ Administración",
              "🔍 Auditoría",
          ]
          and st.session_state.get("nivel_usuario") != "admin"
      ):
        continue

      if st.button(macro, key=f"btn_{macro}"):
        st.session_state.menu_abierto = macro
        if macro == "🏠 Bienvenida":
          st.session_state.sub_seleccion = "Inicio"
        elif st.session_state.sub_seleccion not in subs:
          st.session_state.sub_seleccion = subs[0]
        st.rerun()

      if st.session_state.menu_abierto == macro and macro != "🏠 Bienvenida":
        try:
          idx = subs.index(st.session_state.sub_seleccion)
        except ValueError:
          idx = 0

        sel = option_menu(
            None,
            subs,
            icons=["caret-right"] * len(subs),
            default_index=idx,
            key=f"sub_{macro}",
            styles={
                "nav-link": {"text-align": "left", "font-size": "14px"},
                "nav-link-selected": {"background-color": "#004a99"},
            },
        )
        if sel != st.session_state.sub_seleccion:
          st.session_state.sub_seleccion = sel
          st.rerun()
  else:
    st.info("⚠️ Inicia sesión para habilitar el menú de navegación.")

macro = st.session_state.menu_abierto
op = st.session_state.sub_seleccion

# --- ENRUTADOR PRINCIPAL Y CONTROL DE RESTRICCIONES ---
if not st.session_state.usuario_autenticado:
  mostrar_inicio()
else:
  if not validar_acceso_modulo(macro, op):
    st.error(
        "🔒 **Acceso Denegado:** Tu cuenta nivel"
        f" **{st.session_state.nivel_usuario.upper()}** no tiene permisos para"
        f" acceder a la sección *{macro} / {op}*."
    )
    st.info(
        "💡 Actualiza tu suscripción a un nivel superior para desbloquear este"
        " contenido."
    )
  else:
    if op == "Inicio":
      mostrar_inicio()

    elif macro == "📊 Información a Corte":
      if op == "Estados Financieros por Entidad":
        mostrar_explorador()
      elif op == "Estados Financieros por Grupo":
        mostrar_eeff_grupo()
      elif op == "Estados Financieros por Moneda":
        mostrar_explorador_moneda()
      elif op == "Calificación de Cartera y Contingente por Entidad":
        mostrar_explorador_calificacion()
      elif op == "Calificación de Cartera y Contingente por Grupo":
        mostrar_calificacion_grupo()
      elif op == "Indicadores Financieros por Entidad":
        mostrar_iiff_entidad()
      elif op == "Indicadores Financieros por Grupo":
        mostrar_iiff_entidad()
      elif op == "Ponderación de Activos y CAP por Entidad":
        mostrar_explorador_ponderacion()
      elif op == "Ponderación de Activos y CAP por Grupo":
        mostrar_ponderacion_grupo()

    elif macro == "📈 Comportamiento Histórico":
      if op == "Estados Financieros por Entidad":
        mostrar_comportamiento()
      elif op == "Estados Financieros por Moneda":
        mostrar_comportamiento_moneda()
      elif op == "Calificación de Cartera y Contingente por Entidad":
        mostrar_comportamiento_calificacion()
      elif op == "Indicadores Financieros por Entidad":
        mostrar_comportamiento_indicadores()
      elif op == "Ponderación de Activos y CAP":
        mostrar_comportamiento_ponderacion()

    elif macro == "🔀 Otros Análisis":
      if op == "Monitor de Dolarización y R. Cambiario":
        mostrar_monitor_dolarizacion()
      elif op == "Ranking de Cartera Bruta":
        mostrar_ranking_cartera()
      elif op == "Ranking de Indicador de Morosidad":
        mostrar_ranking_mora()
      elif op == "Analizador Detallado de Cartera":
        mostrar_analizador_cartera()
      elif op == "Reporte Top N Cartera Bruta":
        mostrar_reporte_topn_cartera()
      elif op == "Calidad de Activos por Grupo":
        mostrar_calidad_activos_grupo()

    elif macro == "📂 Gestión y Carga de Datos":
      if op == "EEFF Desagregados":
        mostrar_gestor_datos()
      elif op == "EEFF por Moneda":
        mostrar_gestor_datos_moneda()
      elif op == "Calificación de Cartera y Contingente":
        mostrar_gestor_calificacion()
      elif op == "Indicadores Financieros":
        mostrar_gestor_indicadores()
      elif op == "Ponderación de Activos y CAP":
        mostrar_gestor_ponderacion()
      elif op == "PAFs y Empleados":
        st.info(
            "🚧 **Módulo en desarrollo:** Carga de PAFs y Empleados próximamente."
        )

    elif macro == "🏛️ Administración":
      if op == "Grupos de Entidades":
        mostrar_grupos()
      elif op == "Entidades Financieras":
        mostrar_entidades()
      elif op == "Control de Usuarios":
        mostrar_gestion_usuarios()

    elif macro == "🔍 Auditoría":
      if op == "Auditoria - Ponderación de Activos y CAP":
        mostrar_modulo_auditoria_ponderacion()