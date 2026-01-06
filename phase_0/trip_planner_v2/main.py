import os
import json
import webbrowser
from planner import TripPlanner

def main():
    print("--- AI Trip Planner V2 ---")
    
    # Check for API Key
    if not os.getenv("GEMINI_API_KEY"):
        print("Error: GEMINI_API_KEY environment variable not set.")
        print("Please set it using: $env:GEMINI_API_KEY='your_key_here'")
        return

    user_input = input("Describe your ideal trip (e.g., 'I want to visit historical sites in Rome'): ")
    
    if not user_input.strip():
        print("Please provide a description.")
        return

    planner = TripPlanner()
    result = planner.create_itinerary(user_input)
    
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
            
            # Prioritize Wiki Summary for description
            if place['wiki_summary']:
                print(f"   Description (Wiki): {place['wiki_summary'][:300]}...")
            else:
                print(f"   Why (AI): {place['original_reason']}")
                
            print(f"   Duration: {place['estimated_duration']} mins")
            
            if place['image_url']:
                print(f"   Image: {place['image_url']}")
            else:
                # Fallback: Create a Google Image Search URL
                search_query = place['name'].replace(" ", "+")
                google_img_url = f"https://www.google.com/search?tbm=isch&q={search_query}"
                print(f"   Image: No direct image found. Search here: {google_img_url}")
                # Store this fallback URL so we can open it later if requested
                place['image_url'] = google_img_url

            # Print Links for UI
            print(f"   [LINKS FOR UI]")
            if place.get('wiki_url'):
                print(f"   - Wiki: {place['wiki_url']}")
            print(f"   - Maps: {place['google_maps_url']}")
            print(f"   - Image: {place['image_url']}")
                
            if item["travel_to_next"]:
                travel = item["travel_to_next"]
                print(f"\n   --> Travel to {travel['to_next_place']}: {travel['distance_km']} km, ~{travel['travel_time_minutes']} mins")
                print(f"       ({travel['note']})")
            
            print("-" * 40)
            
        # Optional: Open images
        choice = input("\nWould you like to open the images in your browser? (y/n): ")
        if choice.lower() == 'y':
            for item in result["itinerary"]:
                if item["place"]["image_url"]:
                    webbrowser.open(item["place"]["image_url"])

if __name__ == "__main__":
    main()
