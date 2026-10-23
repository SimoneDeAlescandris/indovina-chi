import io
import os
import re
import time
import unicodedata

import numpy as np
import requests
from PIL import Image
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    import cv2
    RILEVATORE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
except (ImportError, AttributeError):
    cv2 = None

COMMONS = "https://commons.wikimedia.org/w/api.php"
OPENVERSE = "https://api.openverse.org/v1/images/"
FORMATI = {"image/jpeg", "image/png", "image/webp"}
LICENZE_OK = re.compile(r"^(cc0|cc by(-sa)?\b|public domain|pd\b|pdm)", re.I)
POSITIVE_CALCIO = ("jersey", "shirt", "kit", "football", "soccer", "calcio", "match", "uefa", "fifa", "world cup",
                   "serie a", "champions league", "premier league", "la liga", "bundesliga", "national team",
                   "stadium", "maglia", "playing", "player")
NEGATIVE_CALCIO = ("signature", "autograph", "statue", "wax", "logo", "caricature", "cartoon", "drawing", "painting",
                   "stamp", "coin", "crowd", "fans", "press conference", "interview", "tuxedo", "politic",
                   "president", "referee", "mural", "graffiti", "museum")


def scarica_immagini(soggetti, cartella="img/commons", crediti="img/crediti.txt", contesto="football",
                     positive=POSITIVE_CALCIO, negative=NEGATIVE_CALCIO, volto=True, lato=300, minimo=500,
                     candidati=8, soglia=4, qualita=85, pausa=0.4,
                     contatto="IndovinaChiApp/1.0 (tuo-nome; tua-email@dominio.it)"):
    sessione = requests.Session()
    sessione.headers["User-Agent"] = contatto
    sessione.mount("https://", HTTPAdapter(max_retries=Retry(
        total=3, backoff_factor=1.5, status_forcelist=[429, 500, 502, 503, 504])))

    usa_volto = volto and cv2 is not None
    if volto and cv2 is None:
        print("ATTENZIONE: serve OpenCV 4 per verificare il volto: pip install \"opencv-python-headless<5\"")

    def norm(testo):
        testo = unicodedata.normalize("NFKD", testo or "")
        return re.sub(r"\s+", " ", "".join(c for c in testo if not unicodedata.combining(c)).lower())

    def pulisci(html):
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()

    def da_commons(query):
        try:
            r = sessione.get(COMMONS, timeout=20, params={
                "action": "query", "format": "json", "generator": "search", "gsrsearch": query,
                "gsrnamespace": 6, "gsrlimit": candidati * 2, "prop": "imageinfo",
                "iiprop": "url|mime|size|extmetadata", "iiurlwidth": 1000})
            r.raise_for_status()
            pagine = sorted(r.json().get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
        except (requests.RequestException, ValueError) as e:
            print(f"      errore Commons: {e}")
            return []
        trovati = []
        for p in pagine:
            info = (p.get("imageinfo") or [{}])[0]
            meta = info.get("extmetadata", {})
            licenza = meta.get("LicenseShortName", {}).get("value", "")
            if info.get("mime") not in FORMATI or min(info.get("width", 0), info.get("height", 0)) < minimo:
                continue
            if not LICENZE_OK.match(licenza):
                continue
            testo = " ".join([p["title"], pulisci(meta.get("ImageDescription", {}).get("value")),
                              meta.get("Categories", {}).get("value", "").replace("|", " ")])
            trovati.append({"fonte": "Wikimedia Commons", "titolo": p["title"], "licenza": licenza,
                            "autore": pulisci(meta.get("Artist", {}).get("value")), "testo": norm(testo),
                            "pagina": info.get("descriptionurl", ""), "url": info.get("thumburl") or info["url"]})
        return trovati

    def da_openverse(query):
        try:
            r = sessione.get(OPENVERSE, timeout=20, params={
                "q": query, "license": "cc0,pdm,by,by-sa", "page_size": candidati * 2, "mature": "false"})
            r.raise_for_status()
            risultati = r.json().get("results", [])
        except (requests.RequestException, ValueError) as e:
            print(f"      errore Openverse: {e}")
            return []
        trovati = []
        for x in risultati:
            if x.get("width") and x.get("height") and min(x["width"], x["height"]) < minimo:
                continue
            tag = " ".join(t.get("name", "") for t in x.get("tags") or [])
            trovati.append({"fonte": "Openverse", "titolo": x.get("title") or "", "autore": x.get("creator") or "",
                            "licenza": f"{x['license'].upper()} {x.get('license_version') or ''}".strip(),
                            "testo": norm(f"{x.get('title') or ''} {tag}"),
                            "pagina": x.get("foreign_landing_url") or "", "url": x["url"]})
        return trovati

    def valuta(c, chiavi_nome, posizione):
        if not any(k in c["testo"] for k in chiavi_nome):
            print(f"      - {c['titolo'][:60]} | scartata: non cita il soggetto")
            return None
        try:
            r = sessione.get(c["url"], timeout=40)
            r.raise_for_status()
            img = Image.open(io.BytesIO(r.content))
            img.load()
        except Exception as e:
            print(f"      - {c['titolo'][:60]} | download fallito ({type(e).__name__})")
            return None
        img = img.convert("RGB") if "A" not in img.getbands() else img.convert("RGBA")
        facce = []
        if usa_volto:
            grigio = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2GRAY)
            facce = sorted(RILEVATORE.detectMultiScale(grigio, 1.1, 6, minSize=(max(60, img.width // 14),) * 2),
                           key=lambda f: f[2] * f[3], reverse=True)
            if not facce:
                print(f"      - {c['titolo'][:60]} | scartata: nessun volto in primo piano")
                return None
        trovate = [k for k in positive if k in c["testo"]]
        vietate = [k for k in negative if k in c["testo"]]
        punti = min(len(trovate), 4) * 2 - 6 * len(vietate) - posizione * 0.1
        if facce:
            punti += (4 if len(facce) == 1 else 1) + min(facce[0][2] / img.width * 10, 4)
        print(f"      - {c['titolo'][:60]} | punti {punti:.1f} | volti {len(facce)} | parole: {','.join(trovate) or '-'}"
              + (f" | VIETATE: {','.join(vietate)}" if vietate else ""))
        return {**c, "punti": punti, "img": img, "faccia": tuple(facce[0]) if len(facce) else None}

    def ritaglia(img, faccia):
        if faccia:
            x, y, w, h = faccia
            lato_c = int(min(w * 2.8, *img.size))
            sx = min(max(x + w / 2 - lato_c / 2, 0), img.width - lato_c)
            sy = min(max(y + h / 2 - lato_c * 0.42, 0), img.height - lato_c)
        else:
            lato_c = min(img.size)
            sx, sy = (img.width - lato_c) // 2, (img.height - lato_c) * 0.2
        sx, sy = int(sx), int(sy)
        return img.crop((sx, sy, sx + lato_c, sy + lato_c)).resize((lato, lato), Image.Resampling.LANCZOS)

    soggetti = list(dict.fromkeys(s.strip() for s in soggetti if s.strip()))
    os.makedirs(cartella, exist_ok=True)
    os.makedirs(os.path.dirname(crediti) or ".", exist_ok=True)
    gia_citati = set()
    if os.path.exists(crediti):
        with open(crediti, encoding="utf-8") as f:
            gia_citati = {riga.split(" | ")[0] for riga in f if " | " in riga}
    else:
        with open(crediti, "w", encoding="utf-8") as f:
            f.write("Crediti delle immagini (Nome | Autore | Licenza | Fonte)\n")
    esito = {"salvate": 0, "gia_presenti": 0, "fallite": []}

    print(f"=== Download di {len(soggetti)} immagini in '{cartella}' ({lato}x{lato}px, WebP) ===")
    print(f"Verifica volto: {'attiva' if usa_volto else 'disattivata'} | contesto di ricerca: '{contesto}'")

    for i, nome in enumerate(soggetti, 1):
        etichetta = re.sub(r'[<>:"/\\|?*]', "", nome).strip().rstrip(".")
        destinazione = os.path.join(cartella, f"{etichetta}.webp")
        print(f"\n[{i}/{len(soggetti)}] {nome}")
        if os.path.exists(destinazione):
            print("   gia' presente, salto")
            esito["gia_presenti"] += 1
            continue

        parole = [p for p in norm(nome).replace("'", " ").replace("-", " ").split() if len(p) > 2]
        chiavi_nome = [max(parole, key=len)] if parole else [norm(nome)]
        migliore = None

        for fonte, ricerche in (("Wikimedia Commons", [f'"{nome}" {contesto}', f'"{nome}"']),
                                ("Openverse", [f"{nome} {contesto}"])):
            if migliore and migliore["punti"] >= soglia:
                break
            for query in ricerche:
                print(f"   ricerca su {fonte}: {query}")
                cercati = (da_commons if fonte == "Wikimedia Commons" else da_openverse)(query)
                valutati = [v for v in (valuta(c, chiavi_nome, n) for n, c in enumerate(cercati[:candidati])) if v]
                if valutati:
                    top = max(valutati, key=lambda v: v["punti"])
                    if not migliore or top["punti"] > migliore["punti"]:
                        migliore = top
                if migliore and migliore["punti"] >= soglia:
                    break

        if not migliore:
            print("   FALLITO: nessuna immagine adatta con licenza libera")
            esito["fallite"].append(nome)
            continue
        if migliore["punti"] < soglia:
            print(f"   ATTENZIONE: punteggio basso ({migliore['punti']:.1f}), controlla a mano questa immagine")

        print(f"   scelta: {migliore['titolo']} | {migliore['licenza']} | {migliore['fonte']}")
        ritaglia(migliore["img"], migliore["faccia"]).save(destinazione, "WEBP", quality=qualita)
        print(f"   salvata: {destinazione} ({os.path.getsize(destinazione) // 1024} KB)")
        if etichetta not in gia_citati:
            with open(crediti, "rb+") as f:
                f.seek(0, os.SEEK_END)
                if f.tell():
                    f.seek(-1, os.SEEK_END)
                    fine = f.read(1)
                    f.seek(0, os.SEEK_END)
                    if fine != b"\n":
                        f.write(b"\n")
                f.write(f"{etichetta} | {migliore['autore'] or 'autore non indicato'} | {migliore['licenza']} | "
                        f"{migliore['pagina']}\n".encode("utf-8"))
            gia_citati.add(etichetta)
            print(f"   credito aggiunto in fondo a {crediti}")
        esito["salvate"] += 1
        time.sleep(pausa)

    print("\n=== Riepilogo ===")
    print(f"Salvate: {esito['salvate']} | Gia' presenti: {esito['gia_presenti']} | Fallite: {len(esito['fallite'])}")
    if esito["fallite"]:
        print("Da cercare a mano: " + ", ".join(esito["fallite"]))
    print(f"Crediti (da citare per CC BY / CC BY-SA): {crediti}")
    return esito


if __name__ == "__main__":
    scarica_immagini([
        "Diego Maradona", "Cristiano Ronaldo", "Zinedine Zidane", "Ronaldo Nazario", "Marco van Basten",
        "Roberto Baggio", "Paolo Maldini", "Francesco Totti", "Alessandro Del Piero", "Gianluigi Buffon",
        "Andrea Pirlo", "Kakà", "Lothar Matthäus", "Franco Baresi", "Gabriel Batistuta", "Zlatan Ibrahimović",
        "Andriy Shevchenko", "Ronaldinho", "Samuel Eto'o", "Pavel Nedvěd", "Javier Zanetti",
        "Giorgio Chiellini", "Leonardo Bonucci", "Daniele De Rossi", "Alessandro Nesta", "Fabio Cannavaro",
        "Marek Hamšík", "Gonzalo Higuaín", "Lautaro Martínez", "Paulo Dybala", "Nicolo Barella",
        "Ciro Immobile", "Dusan Vlahovic", "Khvicha Kvaratskhelia", "Victor Osimhen", "Hernán Crespo",
        "Adriano Leite Ribeiro", "Christian Vieri", "Filippo Inzaghi", "Luca Toni",
        "Gianluca Vialli", "Roberto Mancini", "Lionel Messi", "Pelé", "Kylian Mbappé", "Erling Haaland",
        "Neymar Jr", "Robert Lewandowski", "Karim Benzema", "Luka Modrić", "Andrés Iniesta", "Sergio Ramos",
        "Manuel Neuer", "Kevin De Bruyne", "Mohamed Salah", "Jude Bellingham", "Harry Kane", "Toni Kroos",
        "Thomas Müller", "Arjen Robben", "David Beckham", "Wayne Rooney", "Gerard Piqué", "Sergio Busquets",
        "Luis Suárez", "Edinson Cavani", "Sergio Agüero", "Angel Di Maria", "Virgil van Dijk",
        "Alisson Becker", "Thibaut Courtois", "Romelu Lukaku", "Lamine Yamal", "Samir Handanovič",
        "Achraf Hakimi", "Francesco Pio Esposito", "Marcus Thuram", "Alessandro Bastoni", "Federico Dimarco",
        "Lorenzo Palmisani", "Donyell Malen", "Hakan Çalhanoğlu",
    ])