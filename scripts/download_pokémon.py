import os
import io
import requests
from PIL import Image

def download_pokemon_artwork(total_count=1025, output_dir="img/pokémon", target_size=(300, 300)):
    """Scarica gli artwork ufficiali di Pokémon, ridimensionandoli e salvandoli in formato WebP."""
    os.makedirs(output_dir, exist_ok=True)
    
    api_url = f"https://pokeapi.co/api/v2/pokemon?limit={total_count}"
    artwork_url_fmt = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/{id}.png"
    
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        pokemon_list = response.json().get("results", [])
    except requests.RequestException as e:
        print(f"Errore nel recupero dell'elenco Pokémon: {e}")
        return

    for index, item in enumerate(pokemon_list, start=1):
        name = item["name"].lower().strip()
        file_path = os.path.join(output_dir, f"{name}.webp")
        
        if os.path.exists(file_path):
            continue

        try:
            res = requests.get(artwork_url_fmt.format(id=index))
            if res.status_code != 200:
                continue

            with Image.open(io.BytesIO(res.content)) as img:
                img = img.convert("RGBA")
                img.thumbnail(target_size, Image.Resampling.LANCZOS)
                
                canvas = Image.new("RGBA", target_size, (0, 0, 0, 0))
                offset = ((target_size[0] - img.width) // 2, (target_size[1] - img.height) // 2)
                canvas.paste(img, offset)
                canvas.save(file_path, "WEBP", quality=85)
                
            print(f"[{index}/{total_count}] Salvato: {name}.webp")
        except Exception as e:
            print(f"Errore nell'elaborazione di {name} (#{index}): {e}")

if __name__ == "__main__":
    download_pokemon_artwork()