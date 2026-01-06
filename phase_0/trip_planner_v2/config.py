import os

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# OSM / Nominatim Configuration
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_ROUTING_URL = "http://router.project-osrm.org/route/v1/driving"

# Wikimedia Configuration
WIKI_API_URL = "https://en.wikipedia.org/w/api.php"

# User Agent for OSM (Required by their ToS)
HEADERS = {
    "User-Agent": "TripPlanner_Student_App_V2/1.0 (contact: student_project_test@gmail.com)",
    "Referer": "https://github.com/myuser/trip-planner"
}
