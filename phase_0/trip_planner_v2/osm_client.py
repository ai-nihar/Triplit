import requests
import config

class OSMClient:
    def search_place(self, place_name, city_context=None):
        """
        Search for a place using Nominatim.
        Returns a dict with lat, lon, display_name, or None if not found.
        """
        query = place_name
        if city_context:
            query = f"{place_name}, {city_context}"

        params = {
            "q": query,
            "format": "json",
            "limit": 1,
            "addressdetails": 1,
            "extratags": 1
        }
        
        try:
            res = requests.get(config.NOMINATIM_URL, params=params, headers=config.HEADERS)
            res.raise_for_status()
            data = res.json()
            if data:
                result = {
                    "lat": float(data[0]["lat"]),
                    "lon": float(data[0]["lon"]),
                    "display_name": data[0]["display_name"],
                    "osm_id": data[0]["osm_id"],
                    "extratags": data[0].get("extratags", {})
                }
                return result
        except Exception as e:
            print(f"Error searching OSM for {place_name}: {e}")
        return None

    def get_route(self, start_coords, end_coords):
        """
        Get route between two points (lat, lon) tuples using OSRM.
        Returns dict with distance (meters) and duration (seconds).
        """
        # OSRM expects "lon,lat"
        start_str = f"{start_coords[1]},{start_coords[0]}"
        end_str = f"{end_coords[1]},{end_coords[0]}"
        
        url = f"{config.OSRM_ROUTING_URL}/{start_str};{end_str}"
        params = {
            "overview": "false"
        }

        try:
            res = requests.get(url, params=params)
            res.raise_for_status()
            data = res.json()
            if data["code"] == "Ok" and data["routes"]:
                route = data["routes"][0]
                return {
                    "distance_meters": route["distance"],
                    "duration_seconds": route["duration"]
                }
        except Exception as e:
            print(f"Error fetching route from OSRM: {e}")
        
        return None
