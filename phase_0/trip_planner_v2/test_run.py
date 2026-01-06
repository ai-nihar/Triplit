import os
import json
from planner import TripPlanner
from gemini_client import GeminiClient

# Mock the Gemini Client to avoid needing a real API Key for this test
class MockGeminiClient:
    def search_places(self, user_input, city_context=None):
        print(f"[Mock] Searching for: {user_input}")
        return {
            "suggested_city": "Ahmedabad",
            "places": [
                {
                    "name": "Sabarmati Ashram",
                    "city": "Ahmedabad",
                    "reason": "Historic home of Mahatma Gandhi.",
                    "estimated_duration_minutes": 90
                },
                {
                    "name": "Adalaj Stepwell",
                    "city": "Ahmedabad",
                    "reason": "Stunning example of Indo-Islamic architecture.",
                    "estimated_duration_minutes": 60
                },
                {
                    "name": "Sidi Saiyyed Mosque",
                    "city": "Ahmedabad",
                    "reason": "Famous for its intricate stone lattice work (Jali).",
                    "estimated_duration_minutes": 45
                },
                {
                    "name": "Kankaria Lake",
                    "city": "Ahmedabad",
                    "reason": "Popular recreational area and lakefront.",
                    "estimated_duration_minutes": 120
                }
            ]
        }

# Monkey patch the TripPlanner to use our Mock Client
def mock_init(self):
    self.gemini = MockGeminiClient()
    self.osm = TripPlanner.__dict__['osm'] if hasattr(TripPlanner, 'osm') else __import__('osm_client').OSMClient()
    self.wiki = TripPlanner.__dict__['wiki'] if hasattr(TripPlanner, 'wiki') else __import__('wiki_client').WikiClient()

# We need to instantiate OSM and Wiki clients properly in the mock
from osm_client import OSMClient
from wiki_client import WikiClient

class TestTripPlanner(TripPlanner):
    def __init__(self):
        self.gemini = MockGeminiClient()
        self.osm = OSMClient()
        self.wiki = WikiClient()

def main():
    print("--- TEST RUN (Mocking AI) ---")
    
    # Bypass API Key check for this test
    os.environ["GEMINI_API_KEY"] = "DUMMY_KEY"
    
    planner = TestTripPlanner()
    
    # Run with a sample query
    result = planner.create_itinerary("Ahmedabad for 2 days and none priority")
    
    if "error" in result:
        print(f"Error: {result['error']}")
    else:
        print("\n" + "="*50)
        print(f"ITINERARY: {result['trip_title']}")
        print("="*50 + "\n")
        
        for item in result["itinerary"]:
            place = item["place"]
            print(f"{item['order']}. {place['name']}")
            print(f"   Address: {place['address']}")
            
            if place['wiki_summary']:
                print(f"   Description (Wiki): {place['wiki_summary'][:100]}...")
            else:
                print(f"   Why (AI): {place['original_reason']}")
                
            print(f"   Duration: {place['estimated_duration']} mins")
            
            # Print Links for UI
            print(f"   [LINKS FOR UI]")
            if place.get('wiki_url'):
                print(f"   - Wiki: {place['wiki_url']}")
            print(f"   - Maps: {place['google_maps_url']}")
            print(f"   - Image: {place['image_url']}")
                
            if item["travel_to_next"]:
                travel = item["travel_to_next"]
                print(f"\n   --> Travel to {travel['to_next_place']}: {travel['distance_km']} km")
            
            print("-" * 40)

if __name__ == "__main__":
    main()
