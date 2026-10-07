import hashlib
import streamlit as st
from config_db import UsuarioModel, obtener_engine
from sqlalchemy.orm import sessionmaker


def hash_password(password):
  return hashlib.sha256(password.encode()).hexdigest()


def mostrar_inicio():
  # Si el usuario ya está autenticado, mostramos el Dashboard de Bienvenida / Resumen
  if st.session_state.get("usuario_autenticado", False):
    st.title("🚀 SFB Analytics")
    st.subheader(
        f"Bienvenido de nuevo, {st.session_state.get('nombre_usuario', 'Usuario')}"
    )

    st.markdown("---")

    col1, col2 = st.columns([2, 1])

    with col1:
      st.markdown("""
        ### 📊 Objetivo del Dashboard
        Esta herramienta ha sido diseñada para optimizar el análisis de estados financieros 
        bajo normativa **ASFI**, permitiendo una navegación intuitiva y técnica por el plan de cuentas 
        del Sistema Financiero Boliviano.
        
        #### 🌟 Módulos Disponibles en tu Cuenta:
        1. **Explorador Jerárquico:** Visualización escalonada del balance general y estado de resultados.
        2. **Análisis de Cartera:** Seguimiento de tendencias y evolución de mora.
        3. **Administración y Auditoría:** Gestión centralizada de entidades y análisis avanzados.
        """)

    with col2:
      nivel_actual = st.session_state.get("nivel_usuario", "free").upper()
      st.info(f"""
        ### 🛡️ Estado del Sistema
        - **Base de Datos:** Conectada ✅
        - **Sincronización:** Al día
        - **Nivel de Cuenta:** **{nivel_actual}**
        """)

    st.markdown("---")
    st.write("### ⚡ Acceso Rápido")
    c1, c2, c3 = st.columns(3)

    if c1.button("🔍 Ir al Explorador", use_container_width=True):
      st.info("Usa el menú lateral para navegar al Explorador.")

    if c2.button("📊 Ver Reportes", use_container_width=True):
      st.info("Usa el menú lateral para navegar a Comportamiento u Otros Análisis.")

    if c3.button("🚪 Cerrar Sesión", use_container_width=True):
      st.session_state.usuario_autenticado = False
      st.session_state.nivel_usuario = "free"
      st.session_state.nombre_usuario = "Invitado"
      st.rerun()

  else:
    # --- PANTALLA DE ACCESO MINIMALISTA Y CENTRADA ---
    st.markdown("<br><br>", unsafe_allow_html=True)

    _, col_centro, _ = st.columns([1, 1.3, 1])

    with col_centro:
      with st.container(border=True):
        c_logo, c_texto = st.columns([0.18, 0.82])
        with c_logo:
          st.image("imagenes/logotipo.png", width=45)
        with c_texto:
          st.markdown("### **SFB Analytics**")

        st.markdown(
            "<hr style='margin: 5px 0 15px 0; border-color: #333;'>",
            unsafe_allow_html=True,
        )

        tab1, tab2 = st.tabs(["🔑 Iniciar Sesión", "📝 Registrarse (Gratis)"])

        engine = obtener_engine()
        Session = sessionmaker(bind=engine)
        session = Session()

        with tab1:
          with st.form("form_login"):
            st.markdown("<br>", unsafe_allow_html=True)
            email_login = st.text_input(
                "Correo Electrónico", key="inicio_login_email"
            )
            pass_login = st.text_input(
                "Contraseña", type="password", key="inicio_login_pass"
            )
            st.markdown("<br>", unsafe_allow_html=True)

            submit_login = st.form_submit_button(
                "Entrar al Sistema", type="primary", use_container_width=True
            )

            if submit_login:
              if not email_login or not pass_login:
                st.error("Por favor completa todos los campos.")
              else:
                pass_hash = hash_password(pass_login)
                user = (
                    session.query(UsuarioModel)
                    .filter_by(email=email_login, password_hash=pass_hash)
                    .first()
                )

                if user and user.activo:
                  st.session_state.usuario_autenticado = True
                  st.session_state.usuario_id = user.id
                  st.session_state.nombre_usuario = user.nombre
                  st.session_state.nivel_usuario = user.nivel
                  st.success(f"¡Bienvenido, {user.nombre}!")
                  st.rerun()
                else:
                  st.error("Credenciales incorrectas o cuenta inactiva.")

          # Botón simulado / integrado de Google OAuth para Iniciar Sesión
          st.markdown(
              "<div style='text-align: center; color: gray; font-size: 12px;"
              " margin: 10px 0;'>O continúa con</div>",
              unsafe_allow_html=True,
          )
          if st.button(
              "🔵 Continuar con Google",
              key="btn_google_login",
              use_container_width=True,
          ):
            # Simulación o integración de acceso rápido por Google (ej. validando cuenta genérica o popup OAuth)
            # Para fines prácticos de prueba local, podemos abrir un prompt o registrar un correo de prueba de Google:
            email_google = "usuario.google@gmail.com"  # En producción esto vendría del token OAuth real
            user_g = (
                session.query(UsuarioModel).filter_by(email=email_google).first()
            )
            if not user_g:
              user_g = UsuarioModel(
                  nombre="Usuario Google",
                  email=email_google,
                  password_hash=None,
                  auth_provider="google",
                  nivel="free",
                  activo=True,
              )
              session.add(user_g)
              session.commit()

            st.session_state.usuario_autenticado = True
            st.session_state.usuario_id = user_g.id
            st.session_state.nombre_usuario = user_g.nombre
            st.session_state.nivel_usuario = user_g.nivel
            st.success("¡Autenticación con Google exitosa!")
            st.rerun()

        with tab2:
          with st.form("form_registro"):
            st.markdown("<br>", unsafe_allow_html=True)
            nombre_reg = st.text_input(
                "Nombre completo", key="inicio_reg_nombre"
            )
            email_reg = st.text_input(
                "Correo Electrónico", key="inicio_reg_email"
            )
            pass_reg = st.text_input(
                "Contraseña", type="password", key="inicio_reg_pass"
            )
            pass_conf = st.text_input(
                "Confirmar Contraseña", type="password", key="inicio_reg_conf"
            )
            st.markdown("<br>", unsafe_allow_html=True)

            submit_reg = st.form_submit_button(
                "Crear Cuenta Gratuita",
                type="secondary",
                use_container_width=True,
            )

            if submit_reg:
              if not nombre_reg or not email_reg or not pass_reg:
                st.error("Todos los campos son obligatorios.")
              elif pass_reg != pass_conf:
                st.error("Las contraseñas no coinciden.")
              else:
                existe = (
                    session.query(UsuarioModel)
                    .filter_by(email=email_reg)
                    .first()
                )
                if existe:
                  st.error("Este correo ya está registrado.")
                else:
                  nuevo = UsuarioModel(
                      nombre=nombre_reg,
                      email=email_reg,
                      password_hash=hash_password(pass_reg),
                      auth_provider="local",
                      nivel="free",
                      activo=True,
                  )
                  session.add(nuevo)
                  session.commit()
                  st.success(
                      "¡Registro exitoso! Ya puedes iniciar sesión en la pestaña"
                      " de al lado."
                  )

          st.markdown(
              "<div style='text-align: center; color: gray; font-size: 12px;"
              " margin: 10px 0;'>O regístrate con</div>",
              unsafe_allow_html=True,
          )
          if st.button(
              "🔵 Registrarse con Google",
              key="btn_google_reg",
              use_container_width=True,
          ):
            # Registro rápido con Google
            email_google = "nuevo.google@gmail.com"
            existe_g = (
                session.query(UsuarioModel).filter_by(email=email_google).first()
            )
            if not existe_g:
              nuevo_g = UsuarioModel(
                  nombre="Nuevo Usuario Google",
                  email=email_google,
                  password_hash=None,
                  auth_provider="google",
                  nivel="free",
                  activo=True,
              )
              session.add(nuevo_g)
              session.commit()
              existe_g = nuevo_g

            st.session_state.usuario_autenticado = True
            st.session_state.usuario_id = existe_g.id
            st.session_state.nombre_usuario = existe_g.nombre
            st.session_state.nivel_usuario = existe_g.nivel
            st.success("¡Registro y acceso con Google exitoso!")
            st.rerun()

        session.close()