# Variables de entorno con credenciales — NUNCA commitear
.env
.env.local
.env.*.local

# Node
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*
.pnpm-debug.log*
dist/
build/
.next/

# Python
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
.venv/
venv/
.pytest_cache/
.mypy_cache/

# IDE
.vscode/
.idea/
*.swp
*.swo
.DS_Store
Thumbs.db

# Logs
*.log
logs/

# Datos sensibles del piloto — NUNCA commitear catálogos reales
data/
*.xlsx
*.csv
!docs/*.csv
!scripts/sample_*.csv

# Supabase local
supabase/.branches
supabase/.temp

# Output del trabajo local
tmp/
output/
