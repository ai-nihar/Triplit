from gemini_client import GeminiClient
from osm_client import OSMClient
from wiki_client import WikiClient
import math

class TripPlanner:
    def __init__(self):
        self.gemini = GeminiClient()
        self.osm = OSMClient()
        self.wiki = WikiClient()

    def create_itinerary(self, user_request):
        print(f"Analyzing request: '{user_request}'...")
        
        # 1. Get suggestions from Gemini
        suggestions = self.gemini.search_places(user_request)
        if not suggestions or not suggestions.get("places"):
            return {"error": "Could not generate suggestions based on the request."}

        city_context = suggestions.get("suggested_city")
        print(f"Targeting area: {city_context}")
        
        validated_places = []

        # 2. Verify and Enrich Data
        for place in suggestions["places"]:
            print(f"Processing: {place['name']}...")
            
            # Verify with OSM
            osm_data = self.osm.search_place(place["name"], city_context)
            if not osm_data:
                # Try without city context if specific search failed
                osm_data = self.osm.search_place(place["name"])
            
            if osm_data:
                # Extract Wiki Title from OSM tags if available
                wiki_title = None
                if "extratags" in osm_data and "wikipedia" in osm_data["extratags"]:
                    wiki_tag = osm_data["extratags"]["wikipedia"]
                    # Format is usually "en:Page Title"
                    if ":" in wiki_tag:
                        wiki_title = wiki_tag.split(":", 1)[1]
                    else:
                        wiki_title = wiki_tag
                    print(f"    -> Found Wiki tag: {wiki_title}")

                # Get Wiki Info
                wiki_data = self.wiki.get_place_info(place["name"], direct_title=wiki_title)
                
                validated_places.append({
                    "name": place["name"],
                    "original_reason": place["reason"],
                    "estimated_duration": place["estimated_duration_minutes"],
                    "coords": (osm_data["lat"], osm_data["lon"]),
                    "address": osm_data["display_name"],
                    "wiki_summary": wiki_data["summary"] if wiki_data else None,
                    "image_url": wiki_data["image_url"] if wiki_data else None,
                    "wiki_url": wiki_data["wiki_url"] if wiki_data else None,
                    "google_maps_url": f"https://www.google.com/maps/search/?api=1&query={osm_data['lat']},{osm_data['lon']}"
                })
            else:
                print(f"  - Could not verify location for {place['name']}, skipping.")

        if not validated_places:
            return {"error": "No valid places found after verification."}

        # 3. Optimize Route (Nearest Neighbor)
        # Start with the first place (or the most central one? Let's pick the first one returned by Gemini as a starting point)
        sorted_places = [validated_places.pop(0)]
        
        while validated_places:
            current = sorted_places[-1]
            curr_coords = current["coords"]
            
            # Find nearest next place
            nearest_idx = 0
            min_dist = float('inf')
            
            for i, p in enumerate(validated_places):
                # Simple Euclidean distance for sorting (fast), accurate enough for local sorting
                dist = math.sqrt((p["coords"][0] - curr_coords[0])**2 + (p["coords"][1] - curr_coords[1])**2)
                if dist < min_dist:
                    min_dist = dist
                    nearest_idx = i
            
            sorted_places.append(validated_places.pop(nearest_idx))

        # 4. Calculate Routes and Timings
        itinerary = []
        total_trip_time = 0
        
        for i in range(len(sorted_places)):
            place = sorted_places[i]
            
            travel_info = None
            if i < len(sorted_places) - 1:
                next_place = sorted_places[i+1]
                route_data = self.osm.get_route(place["coords"], next_place["coords"])
                
                if route_data:
                    # Add a buffer for traffic/parking (e.g., 15 mins)
                    buffer_time = 15 * 60 
                    travel_time = route_data["duration_seconds"] + buffer_time
                    
                    travel_info = {
                        "to_next_place": next_place["name"],
                        "distance_km": round(route_data["distance_meters"] / 1000, 2),
                        "travel_time_minutes": round(travel_time / 60),
                        "note": "Includes 15 min buffer for traffic/parking"
                    }
            
            itinerary.append({
                "order": i + 1,
                "place": place,
                "travel_to_next": travel_info
            })

        return {
            "trip_title": f"Trip to {city_context}" if city_context else "Custom Trip Itinerary",
            "itinerary": itinerary
        }
