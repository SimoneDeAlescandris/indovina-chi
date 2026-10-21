import os
import io
import requests
from PIL import Image

HEADERS = {"User-Agent": "IndovinaChiApp/1.0 (contact: admin@example.com)"}

def _fetch_commons_image_url(query):
    """Cerca un'immagine valida su Wikimedia Commons e ne restituisce l'URL."""
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f"file:{query}",
        "gsrlimit": 5,
        "gsrnamespace": 6,
        "prop": "imageinfo",
        "iiprop": "url|mime",
        "format": "json"
    }
    try:
        res = requests.get("https://commons.wikimedia.org/w/api.php", params=params, headers=HEADERS)
        res.raise_for_status()
        pages = res.json().get("query", {}).get("pages", {})
        for page in pages.values():
            info = page.get("imageinfo", [{}])[0]
            if info.get("mime") in ["image/jpeg", "image/png", "image/webp"]:
                return info.get("url")
    except requests.RequestException:
        pass
    return None

def download_commons_images(items, output_dir="img/commons", target_size=(300, 300)):
    """Scarica una lista di immagini da Wikimedia Commons, ritagliandole al centro in formato quadrato WebP."""
    os.makedirs(output_dir, exist_ok=True)

    for item in items:
        filename = item.lower().replace(" ", "_")
        file_path = os.path.join(output_dir, f"{filename}.webp")

        if os.path.exists(file_path):
            continue

        image_url = _fetch_commons_image_url(item)
        if not image_url:
            print(f"Nessun risultato per: '{item}'")
            continue

        try:
            res = requests.get(image_url, headers=HEADERS)
            if res.status_code != 200:
                continue

            with Image.open(io.BytesIO(res.content)) as img:
                img = img.convert("RGBA")
                min_dim = min(img.size)
                
                left = (img.width - min_dim) // 2
                top = (img.height - min_dim) // 2
                
                cropped = img.crop((left, top, left + min_dim, top + min_dim))
                resized = cropped.resize(target_size, Image.Resampling.LANCZOS)
                resized.save(file_path, "WEBP", quality=85)

            print(f"Salvato: {file_path}")
        except Exception as e:
            print(f"Errore nell'elaborazione di '{item}': {e}")

if __name__ == "__main__":
    lista_soggetti = ["Colosseo", "Mona Lisa", "Torre Eiffel", "Statua della Liberta"]
    download_commons_images(lista_soggetti)