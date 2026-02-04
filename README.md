# Triplit (Flask)

## Quick start (Windows / PowerShell)

1) Create/activate your venv (you already have one named `.env`):

```powershell
.\.env\Scripts\Activate.ps1
```

2) Install dependencies:

```powershell
pip install -r requirements.txt
```

3) Create your environment file:

```powershell
Copy-Item .env.example .env
```

4) Run the app:

```powershell
$env:FLASK_APP = "app"
flask run --debug
```

Open http://127.0.0.1:5000/

## Structure

- `app.py` - Flask app factory + blueprint registration
- `routes/` - Flask blueprints (URL mapping)
- `controllers/` - Request handlers (render templates / return JSON)
- `models/` - Data models (add ORM later)
- `templates/` - Jinja2 templates
- `static/` - CSS/JS/images
- `utils/` - Shared helpers
- `adapters/` - Integrations (APIs, email, etc.)
