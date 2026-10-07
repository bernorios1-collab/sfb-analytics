import streamlit as st
from config_db import UsuarioModel, obtener_engine
from sqlalchemy.orm import sessionmaker


def mostrar_gestion_usuarios():
  st.title("👥 Gestión y Control de Usuarios")
  st.write(
      "Administra las cuentas registradas en SFB Analytics y actualiza sus"
      " niveles de acceso comercial."
  )
  st.markdown("---")

  # Verificar si el usuario actual es administrador
  nivel_actual = st.session_state.get("nivel_usuario", "free")
  if nivel_actual != "admin":
    st.error(
        "🔒 **Acceso Denegado:** Este módulo es exclusivo para administradores"
        " del sistema."
    )
    return

  engine = obtener_engine()
  Session = sessionmaker(bind=engine)
  session = Session()

  # Consultar todos los usuarios
  usuarios = session.query(UsuarioModel).all()

  if not usuarios:
    st.info("No hay usuarios registrados en la base de datos.")
    session.close()
    return

  st.subheader(f"Listado General de Usuarios ({len(usuarios)})")

  niveles_disponibles = ["free", "premium", "ultra", "admin"]

  for u in usuarios:
    with st.container(border=True):
      c1, c2, c3, c4 = st.columns([2, 2, 1.5, 1.5])

      with c1:
        st.markdown(f"**Nombre:** {u.nombre}")
        st.markdown(
            f"<span style='color: gray; font-size: 12px;'>ID: {u.id}</span>",
            unsafe_allow_html=True,
        )

      with c2:
        st.markdown(f"**Correo:** {u.email}")
        estado_txt = "✅ Activo" if u.activo else "❌ Inactivo"
        st.markdown(f"**Estado:** {estado_txt}")

      with c3:
        idx_actual = (
            niveles_disponibles.index(u.nivel)
            if u.nivel in niveles_disponibles
            else 0
        )
        nuevo_nivel = st.selectbox(
            f"Nivel ({u.nombre})",
            niveles_disponibles,
            index=idx_actual,
            key=f"niv_{u.id}",
            label_visibility="collapsed",
        )

      with c4:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Actualizar", key=f"btn_upd_{u.id}", use_container_width=True):
          if nuevo_nivel != u.nivel:
            u.nivel = nuevo_nivel
            session.commit()
            st.success(f"¡Nivel de {u.nombre} actualizado a {nuevo_nivel}!")
            st.rerun()
          else:
            st.info("El nivel es el mismo.")

  session.close()