# HotCalls API

A production-ready Django REST API application for CRUD operations and business logic, designed for Kubernetes deployment on Azure.

## 🚀 Features

- **RESTful API** with Django REST Framework
- **Asynchronous Task Processing** with Celery and Redis
- **PostgreSQL Database** for production-grade data storage
- **API Documentation** with Swagger/OpenAPI (drf_yasg)
- **CORS Support** for cross-origin requests
- **Kubernetes Ready** for cloud-native deployment
- **Production Optimized** with minimal dependencies

## 🛠 Technology Stack

- **Backend:** Django 5.0+, Django REST Framework
- **Database:** PostgreSQL with psycopg2-binary
- **Task Queue:** Celery with Redis broker
- **Documentation:** drf_yasg (Swagger/OpenAPI)
- **Production Server:** Gunicorn
- **Deployment:** Kubernetes on Azure

## 📋 Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Redis 6+
- Docker (for containerized deployment)
- Kubernetes cluster (for production deployment)

## 🔧 Installation & Setup

### 1. Clone the Repository
```bash
git clone <repository-url>
cd hotcalls
```

### 2. Create Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Environment Configuration
Create a `.env` file in the project root:

```env
# Django Settings
SECRET_KEY=your-secret-key-here
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1,your-domain.com
TIME_ZONE=Europe/Berlin

# Security Settings
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_BROWSER_XSS_FILTER=True
SECURE_CONTENT_TYPE_NOSNIFF=True
X_FRAME_OPTIONS=DENY

# Database Configuration
DATABASE_URL=postgresql://username:password@localhost:5432/hotcalls_db

# Celery Configuration
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# CORS Settings
CORS_ALLOW_ALL_ORIGINS=False
CORS_ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com

# Base URL
BASE_URL=https://api.yourdomain.com
```

### 5. Database Setup
```bash
# Run migrations
python manage.py migrate

# Create superuser (optional)
python manage.py createsuperuser
```

### 6. Run Development Server
```bash
# Start Django development server
python manage.py runserver

# In another terminal, start Celery worker
celery -A hotcalls worker --loglevel=info

# In another terminal, start Celery beat (for scheduled tasks)
celery -A hotcalls beat --loglevel=info
```

## 📚 API Documentation

### Swagger UI
Access interactive API documentation at:
- **Development:** `http://localhost:8000/swagger/`
- **Production:** `https://your-domain.com/swagger/`

### ReDoc
Alternative documentation format:
- **Development:** `http://localhost:8000/redoc/`
- **Production:** `https://your-domain.com/redoc/`

### API Schema
Download OpenAPI schema:
- **JSON:** `/swagger.json`
- **YAML:** `/swagger.yaml`

## 🏗 Project Structure

```
hotcalls/
├── hotcalls/                 # Main Django project
│   ├── __init__.py
│   ├── settings.py          # Django settings
│   ├── urls.py              # URL routing
│   ├── wsgi.py              # WSGI application
│   ├── asgi.py              # ASGI application
│   └── celery.py            # Celery configuration
├── core/                    # Core application
│   ├── models.py            # Database models
│   ├── tasks.py             # Celery tasks
│   ├── frontend_api/        # API endpoints
│   └── utils/               # Utility functions
├── manage.py                # Django management script
├── requirements.txt         # Python dependencies
└── README.md               # This file
```

## 🐳 Docker Deployment

### Build Docker Image
```bash
docker build -t hotcalls-api .
```

### Run with Docker Compose
```bash
docker-compose up -d
```

## ☸️ Kubernetes Deployment

### Prerequisites
- Kubernetes cluster on Azure (AKS)
- PostgreSQL database (Azure Database for PostgreSQL)
- Redis cache (Azure Cache for Redis)

### Deployment Components
- **Web Pods:** Django API with Gunicorn
- **Worker Pods:** Celery workers for background tasks
- **Beat Pod:** Celery beat for scheduled tasks
- **Ingress:** NGINX for routing and SSL termination

### Deploy to Kubernetes
```bash
# Apply Kubernetes manifests
kubectl apply -f k8s/

# Check deployment status
kubectl get pods -l app=hotcalls
```

## 🔒 Security Features

- **Environment-based Configuration**
- **HTTPS Enforcement** in production
- **Secure Cookie Settings**
- **XSS Protection**
- **Content Type Validation**
- **CORS Configuration**
- **SQL Injection Protection** (Django ORM)

## 🧪 Testing

```bash
# Run tests
python manage.py test

# Run with coverage
pip install coverage
coverage run manage.py test
coverage report
```

## 📊 Monitoring & Logging

### Health Checks
- **API Health:** `/health/`
- **Database:** Django admin interface
- **Celery:** Celery monitoring tools

### Logging
- Configure logging in `settings.py`
- Use structured logging for production
- Integrate with Azure Monitor or ELK stack

## 🚀 Performance Optimization

- **Database Optimization:** Proper indexing and query optimization
- **Caching:** Redis for session and application caching
- **Static Files:** Served via CDN in production
- **Connection Pooling:** Optimized database connections
- **Horizontal Scaling:** Multiple pod replicas in Kubernetes

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/new-feature`
3. Commit your changes: `git commit -am 'Add new feature'`
4. Push to the branch: `git push origin feature/new-feature`
5. Submit a pull request

## 📄 License

This project is proprietary and confidential.

## 📞 Support

For support and questions, contact: contact@hotcalls.example

---

**Built with ❤️ for production-grade performance and scalability**
