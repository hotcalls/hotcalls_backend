# Django Migrations in Docker - Quick Guide

## 🚨 Golden Rule
**Model changes** → **makemigrations** → **migrate** → **commit**

## ✅ Proper Workflow

### After ANY model change:
```bash
# 1. Generate migration file
docker-compose exec backend python manage.py makemigrations

# 2. Apply to database  
docker-compose exec backend python manage.py migrate

# 3. Commit to git
git add core/migrations/
git commit -m "Add new model fields"
```

## 🔍 Useful Commands

```bash
# Check migration status
docker-compose exec backend python manage.py showmigrations

# Preview changes before applying
docker-compose exec backend python manage.py makemigrations --dry-run

# See what migrations will run
docker-compose exec backend python manage.py migrate --plan
```

## 🚨 When to Rebuild vs Migrate

**Just Migrate (Fast):**
- ✅ Model field changes
- ✅ New models
- ✅ Relationship changes

**Need Rebuild (Slow):**
- ❌ New Python dependencies
- ❌ Dockerfile changes
- ❌ requirements.txt updates

## ⚡ Quick Fixes

**Reset everything (DEV ONLY):**
```bash
docker-compose down
docker volume rm hotcalls_postgres_data
docker-compose up
```

**Check what broke:**
```bash
docker-compose logs backend | grep -i migration
```

## 💡 Pro Tips

- Migrations run automatically on `docker-compose up`
- Always review migration files before applying
- Never edit migration files manually
- Keep migrations in git
- Use `--dry-run` to preview changes

## 🎯 Remember
Your `docker-compose.yml` already runs `migrate` on startup, but you still need to **create** migration files with `makemigrations` after model changes! 