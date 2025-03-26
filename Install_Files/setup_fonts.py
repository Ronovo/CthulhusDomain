import os
import urllib.request
import zipfile
import io

def download_font():
    # Create fonts directory if it doesn't exist
    os.makedirs("fonts", exist_ok=True)
    
    # URL for Crimson Text font
    font_url = "https://github.com/google/fonts/raw/main/ofl/crimsontext/CrimsonText-Regular.ttf"
    
    try:
        # Download the font
        print("Downloading Crimson Text font...")
        urllib.request.urlretrieve(font_url, "fonts/CrimsonText-Regular.ttf")
        print("Font downloaded successfully!")
    except Exception as e:
        print(f"Error downloading font: {e}")
        print("The game will use the system font instead.")

if __name__ == "__main__":
    download_font() 