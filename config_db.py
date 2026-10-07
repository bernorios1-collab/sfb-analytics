import os
from dotenv import load_dotenv
from sqlalchemy import Column, DateTime, Integer, String, Boolean, create_engine
from sqlalchemy.ext.declarative import declarative_base

# Cargar las variables de entorno desde el archivo .env oculto
load_dotenv()

# --- CONFIGURACIÓN SEGURA MEDIANTE VARIABLES DE ENTORNO ---
USUARIO = os.getenv("DB_USER", "postgres")
PASSWORD = os.getenv("DB_PASSWORD", "")
HOST = os.getenv("DB_HOST", "localhost")
PORT = os.getenv("DB_PORT", "5432")
DATABASE = os.getenv("DB_NAME", "asfi_db")

# URL de conexión para SQLAlchemy
DB_URL = f'postgresql://{USUARIO}:{PASSWORD}@{HOST}:{PORT}/{DATABASE}'

Base = declarative_base()


class UsuarioModel(Base):
    __tablename__ = 'usuarios'
    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(150), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=True)
    auth_provider = Column(String(50), default='local')
    nivel = Column(String(50), default='free') # free, premium, ultra, admin
    activo = Column(Boolean, default=True)

def obtener_engine():
    """Retorna el engine de SQLAlchemy para procesos de carga"""
    return create_engine(DB_URL)

def inicializar_tabla_usuarios():
    """Crea la tabla usuarios si no existe"""
    engine = obtener_engine()
    Base.metadata.create_all(bind=engine)

def obtener_params_psycopg2():
    """Retorna los parámetros para conexiones directas de psycopg2 (App)"""
    return {
        "host": HOST,
        "database": DATABASE,
        "user": USUARIO,
        "password": PASSWORD
    }