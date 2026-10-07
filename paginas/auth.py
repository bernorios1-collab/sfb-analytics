import streamlit as st
import hashlib
from config_db import obtener_engine, UsuarioModel
from sqlalchemy.orm import sessionmaker

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def mostrar_modulo_auth():
    st.title("🔐 Acceso a SFB Analytics")
    st.write("Inicia sesión o regístrate para acceder a los niveles Premium y Ultra.")
    
    tab1, tab2 = st.tabs(["🔑 Iniciar Sesión", "📝 Registrarse"])
    
    engine = obtener_engine()
    Session = sessionmaker(bind=engine)
    session = Session()
    
    with tab1:
        st.subheader("Iniciar Sesión")
        email = st.text_input("Correo electrónico", key="login_email")
        password = st.text_input("Contraseña", type="password", key="login_pass")
        
        if st.button("Entrar", type="primary"):
            if not email or not password:
                st.error("Completa todos los campos.")
            else:
                pass_hash = hash_password(password)
                user = session.query(UsuarioModel).filter_by(email=email, password_hash=pass_hash).first()
                
                if user and user.activo:
                    st.session_state.usuario_autenticado = True
                    st.session_state.nombre_usuario = user.nombre
                    st.session_state.nivel_usuario = user.nivel # 'free', 'premium', 'ultra', 'admin'
                    st.success(f"¡Bienvenido, {user.nombre}!")
                    st.rerun()
                else:
                    st.error("Credenciales incorrectas o cuenta inactiva.")
                    
    with tab2:
        st.subheader("Registro de Usuario Gratuito")
        nombre_reg = st.text_input("Nombre completo", key="reg_nombre")
        email_reg = st.text_input("Correo electrónico", key="reg_email")
        pass_reg = st.text_input("Contraseña", type="password", key="reg_pass")
        pass_conf = st.text_input("Confirmar contraseña", type="password", key="reg_conf")
        
        if st.button("Registrarse"):
            if not nombre_reg or not email_reg or not pass_reg:
                st.error("Todos los campos son obligatorios.")
            elif pass_reg != pass_conf:
                st.error("Las contraseñas no coinciden.")
            else:
                existe = session.query(UsuarioModel).filter_by(email=email_reg).first()
                if existe:
                    st.error("Este correo ya está registrado.")
                else:
                    nuevo = UsuarioModel(
                        nombre=nombre_reg,
                        email=email_reg,
                        password_hash=hash_password(pass_reg),
                        auth_provider="local",
                        nivel="free",
                        activo=True
                    )
                    session.add(nuevo)
                    session.commit()
                    st.success("¡Registro exitoso! Ya puedes iniciar sesión en la pestaña de al lado.")
                    
    session.close()