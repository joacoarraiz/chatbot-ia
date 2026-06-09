# Guía rápida — GitHub

## Hacer cambios y subirlos

```bash
git add .
git commit -m "descripción breve del cambio"
git push origin main
```

## Bajar cambios del repo

```bash
git pull origin main
```

## Crear una rama para trabajar sin afectar la main

```bash
git checkout -b mi-rama
# (hacés cambios)
git push origin mi-rama
# Después abrir PR en github.com
```

## Si te trabás

- `git status` te muestra qué cambió.
- `git log --oneline -10` los últimos 10 commits.
- `git diff` lo que cambiaste vs el último commit.
