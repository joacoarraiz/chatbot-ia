# Guía: subir esto a GitHub

Esto es para vos, que es tu primera vez armando un repo del proyecto. Te lo explico sin asumir nada.

## Qué vas a necesitar

- Una cuenta de GitHub (gratuita): https://github.com/signup
- Git instalado en tu compu. Para chequear, abrí terminal y escribí `git --version`. Si no lo tenés, instalalo desde https://git-scm.com/downloads.

## Paso 1 — Crear la organización (recomendado) o usar tu cuenta personal

**Si vas a trabajar en equipo** (Eze, Seba, Fran):
1. En GitHub, click en tu avatar arriba a la derecha → "Your organizations" → "New organization".
2. Elegí el plan **Free**.
3. Nombre sugerido: algo corto como `toni-ai` o el nombre de tu empresa.

**Si lo querés más simple para arrancar**: subilo a tu cuenta personal y después se mueve.

## Paso 2 — Crear el repo

1. En GitHub: botón verde **"New"** o ícono **"+"** arriba a la derecha → "New repository".
2. Configurá así:
   - **Repository name**: `toni-bot`
   - **Description**: "Bot de WhatsApp para autopartes — Etapa 1"
   - **Visibility**: **Private** (importantísimo, hay prompts y arquitectura propia).
   - **NO** marques ninguna de las opciones de "Initialize this repository with..." (ni README, ni .gitignore, ni licencia). Vamos a subir todo nosotros.
3. Click "Create repository".

GitHub te va a mostrar una pantalla con comandos. Quedate en esa pestaña, la vas a usar.

## Paso 3 — Descargar los archivos que te armé

Descargás el zip que te paso al final del chat y lo descomprimís en tu compu. Vas a tener una carpeta `toni-bot/` con todo adentro.

## Paso 4 — Inicializar el repo localmente

Abrí terminal y entrá a la carpeta:

```bash
cd ruta/donde/descomprimiste/toni-bot
```

Ahora corré estos comandos uno por uno:

```bash
# 1. Inicializar git en esta carpeta
git init

# 2. Setear tu identidad (solo la primera vez en esta compu)
git config --global user.name "Tu Nombre"
git config --global user.email "tu@email.com"

# 3. Agregar todos los archivos al "staging"
git add .

# 4. Hacer el primer commit
git commit -m "Estructura inicial del proyecto: db, agentes, tools, checklist"

# 5. Renombrar la rama principal a "main" (estándar actual)
git branch -M main
```

## Paso 5 — Conectarlo al repo remoto

De la pantalla de GitHub copiate la URL del repo. Tiene esta forma:
`https://github.com/TU-USUARIO/toni-bot.git`

Ahora en terminal:

```bash
# 1. Decirle a git dónde está el remoto
git remote add origin https://github.com/TU-USUARIO/toni-bot.git

# 2. Subir todo
git push -u origin main
```

GitHub te va a pedir login. Si tenés autenticación de 2 factores activada (recomendado), no podés usar tu password normal — necesitás un **Personal Access Token**:

1. En GitHub: avatar → Settings → Developer settings → Personal access tokens → Tokens (classic).
2. Generate new token (classic).
3. Nombre: "toni-bot-laptop". Expiration: 90 días. Scope: marcá `repo`.
4. Generate. Copiá el token (te lo muestra una sola vez).
5. Cuando git te pida password, pegás el token.

## Paso 6 — Verificar

Refrescá la página del repo en GitHub. Deberías ver todos los archivos: `README.md`, `db/`, `agents/`, etc.

## Paso 7 — Sumar al equipo

1. En el repo: Settings → Collaborators → "Add people".
2. Buscá a Eze, Seba y Fran por su usuario de GitHub.
3. Ellos van a recibir un mail con la invitación.

## Paso 8 — Que cada uno clone el repo en su compu

Ellos hacen:

```bash
# En la carpeta donde quieran trabajar
git clone https://github.com/TU-USUARIO/toni-bot.git
cd toni-bot

# Copiar el .env.example a .env y completar credenciales
cp .env.example .env
# editar .env con sus credenciales
```

## Flujo de trabajo diario (cuando ya está todo arriba)

```bash
# Antes de empezar a trabajar: bajar los cambios del equipo
git pull

# Hacer cambios, modificar archivos...

# Cuando termines, subir los cambios:
git add .
git commit -m "Mensaje describiendo qué hiciste"
git push
```

## Errores comunes

**"fatal: not a git repository"** → te falta correr `git init` o estás en la carpeta equivocada.

**"Updates were rejected because the remote contains work..."** → alguien subió algo desde la última vez que bajaste. Corré `git pull` primero, después `git push`.

**El push pide usuario y password infinitamente** → tu password normal no funciona si tenés 2FA. Generá un Personal Access Token (paso 5).

**Subiste sin querer el .env con credenciales** → grave, hay que rotar todas las keys. El `.gitignore` que te pasé previene esto, **no lo borres**.

---

## Alternativa más simple: GitHub Desktop

Si los comandos te parecen mucho, descargá **GitHub Desktop** (https://desktop.github.com). Es una app con interfaz visual: abrís la carpeta, hace los commits con un botón, sube todo con otro botón. Para lo que necesitás ahora, sobra.
