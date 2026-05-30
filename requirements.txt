# Toni — dependencias Python
# pip install -r requirements.txt

# LLM
anthropic>=0.40.0

# Base de datos
supabase>=2.8.0
postgrest>=0.16.0

# Validación
jsonschema>=4.21.0

# Variables de entorno
python-dotenv>=1.0.0

# Cargador de Excel (cuando arranquemos con scripts/load_excel.py)
openpyxl>=3.1.0
pandas>=2.2.0

# Servidor web (cuando hagamos el webhook de WhatsApp)
fastapi>=0.110.0
uvicorn[standard]>=0.27.0

# Cliente HTTP (para llamadas a WhatsApp Cloud API y STT)
httpx>=0.27.0

# Logging y observabilidad
structlog>=24.1.0

# Tests
pytest>=8.0.0
