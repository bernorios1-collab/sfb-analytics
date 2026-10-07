import streamlit as st
import pandas as pd
from sqlalchemy import text
from config_db import obtener_engine

engine = obtener_engine()

# --- FUNCIONES TÉCNICAS ---
def ejecutar_query(query, params=None, commit=False):
    """Función auxiliar para manejar consultas SQL"""
    try:
        with engine.begin() as conn:
            result = conn.execute(text(query), params or {})
            if not commit:
                return pd.DataFrame(result.fetchall(), columns=result.keys())
            return None
    except Exception as e:
        raise e

# --- CUADROS DE DIÁLOGO (CONFIRMACIÓN) ---
@st.dialog("Confirmar Operación")
def confirmar_accion(operacion, datos):
    st.write(f"⚠️ **¿Estás seguro de que deseas {operacion.lower()}?**")
    
    if operacion == "Eliminar Entidad":
        st.error(f"Se eliminará permanentemente la entidad: {datos['s']}")
    else:
        st.info(f"Sigla: {datos['s']}\n\nNombre: {datos['n']}\n\nNotas: {datos['not'] if datos['not'] else 'Sin notas'}")

    c1, c2 = st.columns(2)
    if c1.button("Sí, ejecutar", use_container_width=True, type="primary"):
        try:
            if operacion == "Nuevo Registro":
                ejecutar_query(
                    "INSERT INTO entidades (nombre_entidad, nombre_completo, id_grupo, notas) VALUES (:s, :n, :g, :not)",
                    datos, True
                )
            elif operacion == "Actualizar Datos":
                ejecutar_query(
                    "UPDATE entidades SET nombre_completo = :n, id_grupo = :g, notas = :not WHERE nombre_entidad = :s",
                    datos, True
                )
            elif operacion == "Eliminar Entidad":
                ejecutar_query("DELETE FROM entidades WHERE nombre_entidad = :s", {"s": datos['s']}, True)
            
            st.success("✅ Operación realizada con éxito.")
            st.rerun()
        except Exception as e:
            error_str = str(e).lower()
            if "unique" in error_str or "duplicate" in error_str:
                st.error(f"❌ Error: La sigla '{datos['s']}' ya existe en la base de datos.")
            elif "foreign key" in error_str:
                st.error("❌ Error: No se puede eliminar la entidad porque tiene estados financieros u otros registros asociados.")
            else:
                st.error(f"❌ Error técnico: {e}")

    if c2.button("Cancelar", use_container_width=True):
        st.rerun()

# --- VISTA PRINCIPAL ---
def mostrar_entidades():
    st.title("🏛️ Gestión de Entidades Financieras")

    # 1. Obtener Grupos
    df_grupos = ejecutar_query("SELECT id_grupo, nombre_grupo, campo_accion FROM grupos_asfi ORDER BY id_grupo ASC")
    
    if df_grupos.empty:
        st.warning("⚠️ El catálogo de grupos está vacío.")
        return

    # 2. Listado de Entidades
    query_listado = """
        SELECT 
            g.id_grupo as "ID Gp",
            e.nombre_entidad as "Sigla", 
            e.nombre_completo as "Entidad Financiera", 
            g.nombre_grupo as "Categoría Grupo",
            e.notas as "Notas"
        FROM entidades e 
        JOIN grupos_asfi g ON e.id_grupo = g.id_grupo
        ORDER BY g.id_grupo ASC, e.nombre_completo ASC
    """
    df_entidades = ejecutar_query(query_listado)

    st.subheader("Listado Oficial (Ordenado por Jerarquía de Grupo)")
    busqueda = st.text_input("🔍 Filtrar entidad por sigla o nombre...")
    
    if busqueda and not df_entidades.empty:
        df_entidades = df_entidades[
            df_entidades['Sigla'].str.contains(busqueda, case=False) | 
            df_entidades['Entidad Financiera'].str.contains(busqueda, case=False)
        ]
    
    # Anchos explícitos en píxeles para activar la barra de desplazamiento horizontal
    st.dataframe(
        df_entidades, 
        use_container_width=True, 
        hide_index=True,
        column_config={
            "ID Gp": st.column_config.NumberColumn("ID Gp", format="%d", width=70),
            "Sigla": st.column_config.TextColumn("Sigla", width=100),
            "Entidad Financiera": st.column_config.TextColumn("Entidad Financiera", width=300),
            "Categoría Grupo": st.column_config.TextColumn("Categoría Grupo", width=250),
            "Notas": st.column_config.TextColumn("Notas / Observaciones", width=800)
        }
    )

    # 3. Formulario de Administración
    st.markdown("---")
    st.subheader("📝 Acciones de Mantenimiento")
    
    with st.form("form_gestion_entidades", clear_on_submit=False):
        c1, c2 = st.columns([1, 2])
        sigla_input = c1.text_input("Sigla de la Entidad (Identificador)")
        
        mapa_grupos = {f"{r['id_grupo']} - {r['nombre_grupo']}": r['id_grupo'] for _, r in df_grupos.iterrows()}
        grupo_sel = c2.selectbox("Asignar/Mover a Grupo:", options=list(mapa_grupos.keys()))
        
        nombre_input = st.text_input("Nombre Completo de la Institución")
        notas_input = st.text_area("Notas / Aclaraciones (Opcional)", height=80)
        
        c_radio, c_btn = st.columns([2, 1])
        accion_radio = c_radio.radio("Tipo de operación:", ["Nuevo Registro", "Actualizar Datos", "Eliminar Entidad"], horizontal=True)
        submit_btn = c_btn.form_submit_button("Solicitar Ejecución", use_container_width=True, type="primary")
        
        if submit_btn:
            s = sigla_input.upper().strip()
            n = nombre_input.strip()
            not_str = notas_input.strip() if notas_input.strip() else None
            g_id = mapa_grupos[grupo_sel]
            
            if not s:
                st.error("La sigla es obligatoria.")
            elif accion_radio != "Eliminar Entidad" and not n:
                st.error("El nombre es obligatorio para esta operación.")
            else:
                confirmar_accion(accion_radio, {"s": s, "n": n, "g": g_id, "not": not_str})

if __name__ == "__main__":
    mostrar_entidades()