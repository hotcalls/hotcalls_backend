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

## 🔍 GRÜNDLICHE ANALYSE: Massive Duplikate und unnötige Komplexität gefunden!

Du hast völlig recht - es gibt massive Duplikate in der Subscription Management API! Hier ist meine detaillierte Analyse:

## 🚨 **KRITISCHE PROBLEME GEFUNDEN:**

### 1. **DOPPELTE SUBSCRIPTION SYSTEME** 
Es gibt zwei parallele, sich überschneidende Systeme für das Gleiche:

#### **❌ Database-basiert (Subscription API):**
```
/api/subscriptions/plans/          # Django Database Plans
/api/subscriptions/features/       # Django Database Features  
/api/subscriptions/plan-features/  # Plan-Feature Zuordnungen
```

#### **✅ Stripe-basiert (Payment API):**
```
/api/payments/stripe/products/                     # Live Stripe Products
/api/payments/workspaces/{id}/subscription/        # Live Stripe Status
/api/payments/stripe/create-checkout-session/      # Stripe Checkout
```

### 2. **DREIFACHE SUBSCRIPTION STATUS ENDPOINTS** 
```
❌ /api/payments/workspaces/{id}/check-subscription/    # Duplikat 1
❌ /api/payments/workspaces/{id}/subscription/          # Duplikat 2  
❌ /api/workspaces/workspaces/{id}/ (is_subscription_active) # Duplikat 3
```

### 3. **DOPPELTE CHECKOUT URLs**
```python
# Identische Funktionalität auf 2 URLs:
path('stripe/create-checkout-session/', create_checkout_session),
path('stripe/checkout-session/', create_checkout_session),
```

### 4. **INCONSISTENTE WORKSPACE SUBSCRIPTION FIELDS**
```python
class Workspace:
    # ❌ Database Plan (unnötig)
    current_plan = models.ForeignKey('Plan', ...)
    
    # ✅ Stripe Integration (das einzige was wir brauchen)  
    stripe_customer_id = models.CharField(...)
    stripe_subscription_id = models.CharField(...)
```

### 5. **VERALTETE SUBSCRIPTION_STATUS VERWEISE**
❌ **Payment API verwendet noch entferntes `subscription_status` Feld!** 