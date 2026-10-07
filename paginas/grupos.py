import streamlit as st
import pandas as pd
from sqlalchemy import text
from config_db import obtener_engine

engine = obtener_engine()

def ejecutar_query(query, params=None, commit=False):
    try:
        with engine.begin() as conn:
            result = conn.execute(text(query), params or {})
            if not commit:
                return pd.DataFrame(result.fetchall(), columns=result.keys())
            return None
    except Exception as e:
        st.error(f"Error: {e}")
        return None

# --- VENTANAS DE CONFIRMACIÓN ---

@st.dialog("⚠️ Confirmar Cambio")
def confirmar_edicion(id_p, nombre_p, accion_p, notas_p):
    st.write(f"¿Desea aplicar los cambios al Grupo ID **{id_p}**?")
    st.info(f"**Nombre:** {nombre_p}\n\n**Acción:** {accion_p}\n\n**Notas:** {notas_p if notas_p else 'Sin notas'}")
    if st.button("Sí, Guardar Cambios"):
        ejecutar_query(
            "UPDATE grupos_asfi SET nombre_grupo = :n, campo_accion = :a, notas = :not WHERE id_grupo = :i",
            {"n": nombre_p, "a": accion_p, "not": notas_p if notas_p else None, "i": id_p},
            True
        )
        st.success("Actualizado correctamente.")
        st.rerun()

@st.dialog("🚨 Eliminar Registro")
def confirmar_eliminacion(id_p, nombre_p):
    st.error(f"¿Está seguro de eliminar el grupo **{nombre_p}**?")
    st.write("Esta acción es irreversible y podría afectar a las entidades asociadas.")
    if st.button("Eliminar Permanentemente"):
        ejecutar_query("DELETE FROM grupos_asfi WHERE id_grupo = :i", {"i": id_p}, True)
        st.success("Eliminado correctamente.")
        st.rerun()

# --- INTERFAZ ---

def mostrar_grupos():
    st.title("📂 Administración de Grupos (Catálogo ASFI)")
    
    st.subheader("Registros en Base de Datos")
    df = ejecutar_query("SELECT id_grupo, nombre_grupo, campo_accion, notas FROM grupos_asfi ORDER BY id_grupo ASC")
    
    # Se habilitan anchos fijos en px para forzar el scrollbar horizontal
    st.dataframe(
        df, 
        use_container_width=True, 
        hide_index=True,
        column_config={
            "id_grupo": st.column_config.NumberColumn(
                "ID Gp", 
                format="%d", 
                width=80
            ),
            "nombre_grupo": st.column_config.TextColumn(
                "Grupo ASFI", 
                width=250
            ),
            "campo_accion": st.column_config.TextColumn(
                "Campo de Acción", 
                width=250
            ),
            "notas": st.column_config.TextColumn(
                "Notas / Aclaraciones", 
                width=800  # Ancho amplio para que aparezca la barra inferior de navegación
            )
        }
    )

    tab_edit, tab_del = st.tabs(["📝 Editar Registro", "🗑️ Eliminar Registro"])

    if not df.empty:
        opciones = {f"{r['id_grupo']} - {r['nombre_grupo']}": r['id_grupo'] for _, r in df.iterrows()}
        
        with tab_edit:
            sel = st.selectbox("Seleccione grupo para editar", options=list(opciones.keys()))
            
            id_sel = opciones[sel]
            actual = df[df['id_grupo'] == id_sel].iloc[0]
            
            col1, col2 = st.columns(2)
            n_nom = col1.text_input("Nombre", value=actual['nombre_grupo'])
            n_acc = col2.text_input("Campo Acción", value=actual['campo_accion'])
            n_not = st.text_area("Notas / Aclaraciones", value=actual['notas'] if pd.notna(actual['notas']) else "", height=100)
            
            if st.button("Solicitar Modificación", type="primary"):
                confirmar_edicion(id_sel, n_nom, n_acc, n_not)

        with tab_del:
            sel_del = st.selectbox("Seleccione grupo para eliminar", options=list(opciones.keys()), key="del")
            id_del = opciones[sel_del]
            
            if st.button("Solicitar Eliminación"):
                confirmar_eliminacion(id_del, sel_del)
    else:
        st.warning("No hay datos disponibles en la tabla grupos_asfi.")

if __name__ == "__main__":
    mostrar_grupos()