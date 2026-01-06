import requests
import config

class WikiClient:
    def get_place_info(self, place_name, direct_title=None):
        """
        Search Wikipedia for the place to get a summary and main image.
        If direct_title is provided (e.g. from OSM), use it directly.
        """
        title = direct_title
        
        try:
            # 1. If no direct title, search for it
            if not title:
                search_params = {
                    "action": "query",
                    "list": "search",
                    "srsearch": place_name,
                    "format": "json"
                }
                res = requests.get(config.WIKI_API_URL, params=search_params, headers=config.HEADERS)
                res.raise_for_status()
                data = res.json()
                
                if not data.get("query", {}).get("search"):
                    return None
                
                title = data["query"]["search"][0]["title"]
            
            # 2. Get page info (extract and image)
            info_params = {
                "action": "query",
                "titles": title,
                "prop": "extracts|pageimages",
                "exintro": True,
                "explaintext": True,
                "pithumbsize": 1000,
                "format": "json"
            }
            
            res = requests.get(config.WIKI_API_URL, params=info_params, headers=config.HEADERS)
            res.raise_for_status()
            data = res.json()
            
            pages = data.get("query", {}).get("pages", {})
            for page_id, page_data in pages.items():
                if page_id == "-1": continue
                
                return {
                    "title": page_data.get("title"),
                    "summary": page_data.get("extract", "No description available."),
                    "image_url": page_data.get("thumbnail", {}).get("source"),
                    "wiki_url": f"https://en.wikipedia.org/wiki/{page_data.get('title').replace(' ', '_')}"
                }
                
        except Exception as e:
            print(f"Error fetching Wiki info for {place_name}: {e}")
            
        return None
