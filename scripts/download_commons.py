import base64
import io
import os
import re
import tempfile
import time
import unicodedata
import webbrowser
from html import escape
from pathlib import Path
from urllib.parse import unquote

import requests
from PIL import Image
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

COMMONS = "https://commons.wikimedia.org/w/api.php"
WIKIDATA = "https://www.wikidata.org/w/api.php"
WIKIPEDIA = "https://{}.wikipedia.org/w/api.php"
OPENVERSE = "https://api.openverse.org/v1/images/"
FLICKR = "https://www.flickr.com/services/rest/"
EUROPEANA = "https://api.europeana.eu/record/v2/search.json"
MET = "https://collectionapi.metmuseum.org/public/collection/v1/"
LINGUE = ("en", "it")
FONTI_DEFAULT = ("wikidata", "commons", "wikipedia", "openverse")
INTESTAZIONE = "Crediti delle immagini (Nome | Autore | Licenza | Fonte)\n"
FORMATI = {"image/jpeg", "image/png", "image/webp", "image/svg+xml"}
ERRORI_FONTE = (requests.RequestException, ValueError, KeyError, TypeError)
LICENZE_OK = re.compile(r"^(cc0|cc[ -]zero|cc[ -]by|public domain|pd\b|pdm)", re.I)
LICENZE_NO = re.compile(r"(?<![a-z])(nc|nd)(?![a-z])", re.I)
LICENZA_URL = re.compile(r"creativecommons\.org/(publicdomain/zero|publicdomain/mark|licenses/by-sa|licenses/by)/([\d.]+)",
                        re.I)
NOMI_LICENZA_URL = {"publicdomain/zero": "CC0", "publicdomain/mark": "PDM", "licenses/by-sa": "CC BY-SA",
                    "licenses/by": "CC BY"}
LICENZE_FLICKR = {"4": "CC BY 2.0", "5": "CC BY-SA 2.0", "9": "CC0 1.0", "10": "PDM 1.0"}
STILE_FOGLIO = ("body{font-family:sans-serif;margin:16px}.g{display:flex;flex-wrap:wrap;gap:12px}"
                "figure{margin:0;width:230px}img{width:230px;height:230px;object-fit:contain;background:#eee}"
                "figcaption{font-size:12px}b{font-size:20px}")
POSITIVE_CALCIO = ("jersey", "shirt", "kit", "football", "soccer", "calcio", "match", "uefa", "fifa", "world cup",
                "serie a", "champions league", "premier league", "la liga", "bundesliga", "national team",
                "stadium", "maglia", "playing", "player")
NEGATIVE_CALCIO = ("signature", "autograph", "statue", "wax", "logo", "caricature", "cartoon", "drawing", "painting",
                "stamp", "coin", "crowd", "fans", "press conference", "interview", "tuxedo", "politic",
                "president", "referee", "mural", "graffiti", "museum")
TIPI = {
    "persona": {"contesto": "football", "positive": POSITIVE_CALCIO, "negative": NEGATIVE_CALCIO, "volto": True,
                "ritaglio": "volto", "proprieta": ("P18",), "minimo": 500, "extra": ("{n}", "{n} portrait")},
    "luogo": {"contesto": "", "volto": False, "ritaglio": "centro", "proprieta": ("P18",), "minimo": 500,
            "positive": ("monument", "landmark", "exterior", "facade", "panorama", "view", "architecture", "cathedral",
                        "castle", "tower", "bridge", "temple"),
            "negative": ("interior", "inside", "map", "plan", "drawing", "painting", "stamp", "coin", "postcard",
                        "miniature", "replica", "model", "plaque", "sign"),
            "extra": ("{n}", "{n} exterior")},
    "logo": {"contesto": "logo", "volto": False, "ritaglio": "adatta", "proprieta": ("P154",), "minimo": 300,
            "positive": ("logo", "wordmark", "emblem", "brand", "symbol", "official"),
            "negative": ("vintage", "historical", "parody", "fake", "redesign", "proposal", "headquarters",
                        "storefront", "concept"),
            "extra": ("{n}", "{n} wordmark")},
    "personaggio": {"contesto": "character", "volto": False, "ritaglio": "adatta", "proprieta": ("P18",),
                    "minimo": 400,
                    "positive": ("character", "official", "artwork", "render", "illustration", "mascot"),
                    "negative": ("cosplay", "statue", "toy", "figurine", "costume", "fan art", "parody", "plush",
                                "tattoo", "convention", "merchandise"),
                    "extra": ("{n}", "{n} artwork")},
}


def scarica_immagini(soggetti, cartella="img/commons", crediti="img/crediti.txt", contesto=None,
                    positive=None, negative=None, volto=None, lato=500, minimo=None, candidati=8,
                    soglia=4, qualita=85, pausa=0.4,
                    contatto="IndovinaChiApp/1.0 (tuo-nome; tua-email@dominio.it)",
                    fonti=FONTI_DEFAULT, interattivo=True, anteprima=True, tipo="persona", ritaglio=None):
    if tipo not in TIPI:
        raise ValueError(f"tipo sconosciuto: {tipo} (disponibili: {', '.join(TIPI)})")
    scelte = {"contesto": contesto, "positive": positive, "negative": negative, "volto": volto, "minimo": minimo,
            "ritaglio": ritaglio}
    impostazioni = {**TIPI[tipo], **{k: v for k, v in scelte.items() if v is not None}}
    contesto, positive, negative, volto, minimo, ritaglio = (impostazioni[k] for k in scelte)
    proprieta, ricerche_extra = impostazioni["proprieta"], impostazioni["extra"]

    sessione = requests.Session()
    sessione.headers["User-Agent"] = contatto
    sessione.mount("https://", HTTPAdapter(max_retries=Retry(
        total=3, backoff_factor=1.5, status_forcelist=[429, 500, 502, 503, 504])))

    rilevatore = None
    if volto:
        try:
            import cv2
            import numpy as np
            cascata = cv2.CascadeClassifier(getattr(cv2, "data").haarcascades + "haarcascade_frontalface_default.xml")
            if not cascata.empty():
                rilevatore = lambda img: cascata.detectMultiScale(
                    cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY), 1.1, 6, minSize=(max(60, img.width // 14),) * 2)
        except (ImportError, AttributeError):
            pass
    if volto and rilevatore is None:
        print("ATTENZIONE: serve OpenCV 4 per verificare il volto, procedo senza verifica: "
            "pip install \"opencv-python-headless<5\" numpy")

    def norm(testo):
        testo = unicodedata.normalize("NFKD", testo or "")
        return re.sub(r"\s+", " ", "".join(c for c in testo if not unicodedata.combining(c)).lower())

    def pulisci(html):
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()

    def richiedi(url, **parametri):
        risposta = sessione.get(url, params=parametri or None, timeout=40)
        time.sleep(pausa)
        risposta.raise_for_status()
        return risposta

    def richiedi_json(url, **parametri):
        return richiedi(url, **parametri).json()

    def licenza_valida(licenza):
        return bool(LICENZE_OK.match(licenza or "")) and not LICENZE_NO.search(licenza)

    def licenza_da_url(url):
        trovata = LICENZA_URL.search(url or "")
        return f"{NOMI_LICENZA_URL[trovata.group(1).lower()]} {trovata.group(2)}" if trovata else ""

    def piccola(larghezza, altezza):
        return bool(larghezza and altezza) and min(larghezza, altezza) < minimo

    def nuovo(**campi):
        return {"autore": "", "pagina": "", "larghezza": 0, "altezza": 0, "fiducia": False, "bonus": 0, **campi}

    def da_pagine_commons(pagine, fonte, extra):
        trovati = []
        for p in sorted(pagine, key=lambda p: p.get("index", 0)):
            info = (p.get("imageinfo") or [{}])[0]
            meta = info.get("extmetadata", {})
            licenza = meta.get("LicenseShortName", {}).get("value", "")
            vettoriale = info.get("mime") == "image/svg+xml"
            larghezza = info.get("thumbwidth", 0) if vettoriale else info.get("width", 0)
            altezza = info.get("thumbheight", 0) if vettoriale else info.get("height", 0)
            if info.get("mime") not in FORMATI or piccola(larghezza, altezza) or not licenza_valida(licenza):
                continue
            testo = " ".join([p["title"], extra.get(p["title"], ""), pulisci(meta.get("ImageDescription", {}).get("value")),
                            meta.get("Categories", {}).get("value", "").replace("|", " ")])
            trovati.append(nuovo(fonte=fonte, titolo=re.sub(r"^File:", "", p["title"]), licenza=licenza,
                                autore=pulisci(meta.get("Artist", {}).get("value")), testo=norm(testo),
                                pagina=info.get("descriptionurl", ""), url=info.get("thumburl") or info["url"],
                                larghezza=larghezza, altezza=altezza))
        return trovati

    def per_titoli(titoli, fonte):
        if not titoli:
            return []
        dati = richiedi_json(COMMONS, action="query", format="json", titles="|".join(titoli), redirects=1,
                             prop="imageinfo", iiprop="url|mime|size|extmetadata", iiurlwidth=lato * 2)
        return da_pagine_commons(dati.get("query", {}).get("pages", {}).values(), fonte, titoli)

    def da_commons(query, limite, chiavi):
        dati = richiedi_json(COMMONS, action="query", format="json", generator="search", gsrsearch=query,
                             gsrnamespace=6, gsrlimit=min(limite * 2, 50), prop="imageinfo",
                             iiprop="url|mime|size|extmetadata", iiurlwidth=lato * 2)
        return da_pagine_commons(dati.get("query", {}).get("pages", {}).values(), "Wikimedia Commons", {})

    def da_wikidata(query, limite, chiavi):
        entita = {}
        for lingua in LINGUE:
            dati = richiedi_json(WIKIDATA, action="wbsearchentities", format="json", search=query, language=lingua,
                                uselang=lingua, type="item", limit=5)
            for x in dati.get("search", []):
                if any(k in norm(x.get("label", "")) for k in chiavi):
                    entita.setdefault(x["id"], x.get("description", ""))
        if not entita:
            return []
        dati = richiedi_json(WIKIDATA, action="wbgetentities", format="json", ids="|".join(list(entita)[:limite]),
                            props="claims")
        titoli = {}
        for id_entita, e in dati.get("entities", {}).items():
            for prop in proprieta:
                nome_file = next((c.get("mainsnak", {}).get("datavalue", {}).get("value")
                                for c in e.get("claims", {}).get(prop, [])), None)
                if nome_file:
                    titoli["File:" + nome_file.replace("_", " ")] = entita[id_entita]
                    break
        return [dict(c, fiducia=True) for c in per_titoli(titoli, "Wikidata")]

    def da_wikipedia(query, limite, chiavi):
        titoli = {}
        for lingua in LINGUE:
            dati = richiedi_json(WIKIPEDIA.format(lingua), action="query", format="json", generator="search",
                                gsrsearch=query, gsrlimit=3, prop="pageimages", piprop="name", pilicense="free")
            for p in sorted(dati.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0)):
                if p.get("pageimage"):
                    titoli.setdefault("File:" + p["pageimage"].replace("_", " "), p.get("title", ""))
        return per_titoli(dict(list(titoli.items())[:limite]), "Wikipedia")

    def da_openverse(query, limite, chiavi):
        dati = richiedi_json(OPENVERSE, q=query, license="cc0,pdm,by,by-sa", page_size=min(limite * 2, 20),
                            mature="false")
        trovati = []
        for x in dati.get("results", []):
            codice = (x.get("license") or "").upper()
            licenza = f"{'CC ' if codice.startswith('BY') else ''}{codice} {x.get('license_version') or ''}".strip()
            if piccola(x.get("width"), x.get("height")) or not licenza_valida(licenza):
                continue
            tag = " ".join(t.get("name", "") for t in x.get("tags") or [])
            trovati.append(nuovo(fonte="Openverse", titolo=x.get("title") or "", autore=x.get("creator") or "",
                                licenza=licenza, testo=norm(f"{x.get('title') or ''} {tag}"),
                                pagina=x.get("foreign_landing_url") or "", url=x["url"],
                                larghezza=x.get("width") or 0, altezza=x.get("height") or 0))
        return trovati

    def da_flickr(query, limite, chiavi):
        dati = richiedi_json(FLICKR, method="flickr.photos.search", api_key=os.environ["FLICKR_API_KEY"], text=query,
                            license=",".join(LICENZE_FLICKR), media="photos", sort="relevance", safe_search=1,
                             per_page=min(limite * 2, 50), extras="license,owner_name,url_k,url_h,url_l,tags",
                            format="json", nojsoncallback=1)
        if dati.get("stat") == "fail":
            raise ValueError(dati.get("message", "errore Flickr"))
        trovati = []
        for x in dati.get("photos", {}).get("photo", []):
            misura = next((s for s in "khl" if x.get(f"url_{s}")), None)
            licenza = LICENZE_FLICKR.get(str(x.get("license")), "")
            if not misura or not licenza_valida(licenza):
                continue
            larghezza, altezza = int(x.get(f"width_{misura}") or 0), int(x.get(f"height_{misura}") or 0)
            if piccola(larghezza, altezza):
                continue
            trovati.append(nuovo(fonte="Flickr", titolo=x.get("title") or "", autore=x.get("ownername") or "",
                                licenza=licenza, testo=norm(f"{x.get('title') or ''} {x.get('tags') or ''}"),
                                pagina=f"https://www.flickr.com/photos/{x['owner']}/{x['id']}",
                                url=x[f"url_{misura}"], larghezza=larghezza, altezza=altezza))
        return trovati

    def da_europeana(query, limite, chiavi):
        dati = richiedi_json(EUROPEANA, wskey=os.environ["EUROPEANA_API_KEY"], query=query, qf="TYPE:IMAGE",
                             media="true", reusability="open", rows=min(limite * 2, 50))
        trovati = []
        for x in dati.get("items", []):
            licenza = licenza_da_url((x.get("rights") or [""])[0])
            immagine = (x.get("edmIsShownBy") or [""])[0]
            if not immagine or not licenza_valida(licenza):
                continue
            titolo = (x.get("title") or [""])[0]
            trovati.append(nuovo(fonte="Europeana", titolo=titolo, autore=(x.get("dcCreator") or [""])[0],
                                licenza=licenza, testo=norm(f"{titolo} {' '.join(x.get('dcDescription') or [])}"),
                                pagina=x.get("guid", ""), url=immagine))
        return trovati

    def da_met(query, limite, chiavi):
        ricerca = richiedi_json(MET + "search", q=query, hasImages="true", isPublicDomain="true")
        trovati = []
        for id_oggetto in (ricerca.get("objectIDs") or [])[:limite]:
            o = richiedi_json(f"{MET}objects/{id_oggetto}")
            if not o.get("isPublicDomain") or not o.get("primaryImage"):
                continue
            tag = " ".join(t.get("term", "") for t in o.get("tags") or [])
            trovati.append(nuovo(fonte="Met Museum", titolo=o.get("title") or "", licenza="CC0 1.0",
                                autore=o.get("artistDisplayName") or "The Metropolitan Museum of Art",
                                testo=norm(f"{o.get('title') or ''} {o.get('objectName') or ''} {tag}"),
                                pagina=o.get("objectURL", ""), url=o["primaryImage"]))
        return trovati

    catalogo = {
        "wikidata": {"nome": "Wikidata", "cerca": da_wikidata, "ricerche": ("{n}",), "bonus": 3},
        "commons": {"nome": "Wikimedia Commons", "cerca": da_commons, "ricerche": ('"{n}" {c}', '"{n}"'), "extra": 1},
        "wikipedia": {"nome": "Wikipedia", "cerca": da_wikipedia, "ricerche": ("{n}",), "bonus": 1},
        "openverse": {"nome": "Openverse", "cerca": da_openverse, "ricerche": ("{n} {c}",), "extra": 1},
        "met": {"nome": "Met Museum", "cerca": da_met, "ricerche": ("{n}",), "extra": 1},
        "flickr": {"nome": "Flickr", "cerca": da_flickr, "ricerche": ("{n} {c}",), "extra": 1,
                "chiave": "FLICKR_API_KEY"},
        "europeana": {"nome": "Europeana", "cerca": da_europeana, "ricerche": ("{n}",), "extra": 1,
                    "chiave": "EUROPEANA_API_KEY"},
    }
    sconosciute = [f for f in fonti if f not in catalogo]
    if sconosciute:
        raise ValueError(f"fonti sconosciute: {', '.join(sconosciute)} (disponibili: {', '.join(catalogo)})")
    fonti_attive = [f for f in fonti if not catalogo[f].get("chiave") or os.environ.get(catalogo[f]["chiave"])]

    def valuta(c, posizione, chiavi):
        titolo = c["titolo"][:60]
        if not c["fiducia"] and not any(k in c["testo"] for k in chiavi):
            print(f"      - {titolo} | scartata: non cita il soggetto")
            return None
        try:
            img = Image.open(io.BytesIO(richiedi(c["url"]).content))
            img.load()
        except (requests.RequestException, OSError, Image.DecompressionBombError) as errore:
            print(f"      - {titolo} | download fallito ({type(errore).__name__})")
            return None
        if not c["larghezza"]:
            if piccola(*img.size):
                print(f"      - {titolo} | scartata: immagine troppo piccola")
                return None
            c = dict(c, larghezza=img.width, altezza=img.height)
        img = img.convert("RGBA")
        sfondo = Image.new("RGB", img.size, "white")
        sfondo.paste(img, mask=img.getchannel("A"))
        img = sfondo
        facce = []
        if rilevatore is not None:
            facce = sorted(rilevatore(img), key=lambda f: f[2] * f[3], reverse=True)
            if not len(facce) and not interattivo:
                print(f"      - {titolo} | scartata: nessun volto in primo piano")
                return None
        sorgente = (min(int(facce[0][2] * 2.8), *img.size) if len(facce) and ritaglio == "volto"
                    else max(img.size) if ritaglio == "adatta" else min(img.size))
        trovate = [k for k in positive if k in c["testo"]]
        vietate = [k for k in negative if k in c["testo"]]
        punti = (min(len(trovate), 4) * 2 - 6 * len(vietate) - posizione * 0.1 + c["bonus"]
                 - 3 * max(0, 1 - sorgente / lato))
        if len(facce):
            punti += (4 if len(facce) == 1 else 1) + min(facce[0][2] / img.width * 10, 4)
        elif rilevatore is not None:
            punti -= 5
        print(f"      - {titolo} | punti {punti:.1f} | volti {len(facce)} | parole: {','.join(trovate) or '-'}"
            + (f" | VIETATE: {','.join(vietate)}" if vietate else ""))
        return {**c, "punti": punti, "img": img, "volti": len(facce), "sorgente": sorgente,
                "faccia": tuple(facce[0]) if len(facce) else None}

    def raccogli(nome, chiavi, giro, valutati, visti):
        for nome_fonte in fonti_attive:
            fonte = catalogo[nome_fonte]
            if giro and not fonte.get("extra"):
                continue
            modelli = ricerche_extra if giro else fonte["ricerche"]
            for query in dict.fromkeys(m.format(n=nome, c=contesto).strip() for m in modelli):
                print(f"   ricerca su {fonte['nome']}: {query}")
                try:
                    trovati = fonte["cerca"](query, candidati * (giro + 1), chiavi)
                except ERRORI_FONTE as errore:
                    print(f"      errore {fonte['nome']}: {errore}")
                    trovati = []
                print(f"      trovati: {len(trovati)}")
                nuovi = []
                for c in trovati[:candidati * (giro + 1)]:
                    identificativi = {c["pagina"], c["url"]} - {""}
                    if not identificativi & visti:
                        visti |= identificativi
                        nuovi.append(dict(c, bonus=c["bonus"] or fonte.get("bonus", 0)))
                valutati.extend(v for v in (valuta(c, n, chiavi) for n, c in enumerate(nuovi)) if v)
                if not interattivo and valutati and max(v["punti"] for v in valutati) >= soglia:
                    return

    def ritaglia(img, faccia, modo):
        if modo == "adatta":
            quadro = Image.new("RGB", (max(img.size),) * 2, "white")
            quadro.paste(img, ((quadro.width - img.width) // 2, (quadro.height - img.height) // 2))
            return quadro.resize((lato, lato), Image.Resampling.LANCZOS)
        if modo == "volto" and faccia:
            x, y, w, h = faccia
            lato_c = int(min(w * 2.8, *img.size))
            sx = min(max(x + w / 2 - lato_c / 2, 0), img.width - lato_c)
            sy = min(max(y + h / 2 - lato_c * 0.42, 0), img.height - lato_c)
        else:
            lato_c = min(img.size)
            sx, sy = (img.width - lato_c) // 2, (img.height - lato_c) * 0.2
        sx, sy = int(sx), int(sy)
        return img.crop((sx, sy, sx + lato_c, sy + lato_c)).resize((lato, lato), Image.Resampling.LANCZOS)

    def chiedi(domanda):
        try:
            return input(domanda).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return "q"

    def foglio_contatto(nome, valutati, cartella_tmp):
        celle = []
        for n, v in enumerate(valutati, 1):
            miniatura = v["img"].copy()
            miniatura.thumbnail((230, 230))
            buffer = io.BytesIO()
            miniatura.save(buffer, "JPEG", quality=70)
            celle.append(f'<figure><img src="data:image/jpeg;base64,{base64.b64encode(buffer.getvalue()).decode()}">'
                        f'<figcaption><b>{n}</b> {escape(v["titolo"][:50])}<br>{escape(v["fonte"])} - '
                        f'{escape(v["licenza"])}<br>{v["larghezza"]}x{v["altezza"]} - volti {v["volti"]} - '
                        f'punti {v["punti"]:.1f}</figcaption></figure>')
        with tempfile.NamedTemporaryFile("w", dir=cartella_tmp, suffix=".html", delete=False, encoding="utf-8") as f:
            f.write(f'<!doctype html><html><head><meta charset="utf-8"><title>{escape(nome)}</title>'
                    f'<style>{STILE_FOGLIO}</style></head><body><h1>{escape(nome)}</h1>'
                    f'<div class="g">{"".join(celle)}</div></body></html>')
        return f.name

    def mostra(nome, valutati, cartella_tmp):
        print(f"   candidati per '{nome}' (ordinati per punteggio):")
        if not valutati:
            print("   nessun candidato trovato")
        for n, v in enumerate(valutati, 1):
            print(f"   {n:>2}. [{v['fonte']}] {v['titolo'][:50]} | {v['licenza']} | {v['larghezza']}x{v['altezza']} "
                f"| volti {v['volti']} | punti {v['punti']:.1f} | sorgente {v['sorgente']}px")
        aperto = False
        if anteprima and valutati:
            try:
                aperto = webbrowser.open(Path(foglio_contatto(nome, valutati, cartella_tmp)).as_uri())
            except webbrowser.Error:
                pass
            if aperto:
                print("   anteprima aperta nel browser")
        if not aperto:
            for n, v in enumerate(valutati, 1):
                print(f"   {n:>2}. {v['pagina'] or v['url']}")

    def da_url_manuale(chiavi):
        url = chiedi("   URL dell'immagine o pagina File: di Commons: ")
        if not url or url == "q":
            return None
        pagina_commons = re.search(r"commons\.wikimedia\.org/wiki/(File:[^?#]+)", url)
        try:
            if pagina_commons:
                trovati = per_titoli({unquote(pagina_commons.group(1)).replace("_", " "): ""}, "Commons (URL manuale)")
                if not trovati:
                    print("   file non utilizzabile: licenza non ammessa, formato o dimensioni non adatti")
                    return None
                c = trovati[0]
            else:
                licenza = chiedi("   Licenza (es. CC BY 4.0, CC BY-SA 4.0, CC0, Public Domain): ")
                if not licenza_valida(licenza):
                    print("   licenza non ammessa: servono CC0, Public Domain, CC BY o CC BY-SA")
                    return None
                c = nuovo(fonte="URL manuale", titolo=url.rsplit("/", 1)[-1] or url, licenza=licenza, url=url, testo="",
                        autore=chiedi("   Autore: "), pagina=chiedi("   Pagina di origine (invio = stesso URL): ") or url)
            c = valuta(dict(c, fiducia=True), 0, chiavi)
        except ERRORI_FONTE as errore:
            print(f"   errore: {errore}")
            return None
        if c is None:
            print("   immagine non utilizzabile")
        return c

    def menu(nome, chiavi, valutati, visti, cartella_tmp):
        giro = 0
        while True:
            valutati.sort(key=lambda v: v["punti"], reverse=True)
            mostra(nome, valutati, cartella_tmp)
            comando = chiedi("   Scelta [numero | a = migliore | s = salta | m = altri | u = URL | q = esci]: ").lower()
            if comando in ("q", "s"):
                return {"q": "esci", "s": "salta"}[comando], None
            scelto = None
            if comando == "m":
                giro += 1
                prima = len(valutati)
                raccogli(nome, chiavi, giro, valutati, visti)
                print(f"   nuovi candidati: {len(valutati) - prima}")
            elif comando == "u":
                scelto = da_url_manuale(chiavi)
            elif comando == "a" and valutati:
                scelto = valutati[0]
            elif comando.isdigit() and 1 <= int(comando) <= len(valutati):
                scelto = valutati[int(comando) - 1]
            else:
                print("   comando non valido")
            if scelto:
                return "scelta", scelto

    def pulito(testo):
        return re.sub(r"\s+", " ", (testo or "").replace("|", "/")).strip()

    def salva(etichetta, destinazione, scelto, modo):
        ritaglia(scelto["img"], scelto["faccia"], modo).save(destinazione, "WEBP", quality=qualita)
        print(f"   salvata: {destinazione} ({os.path.getsize(destinazione) // 1024} KB)")
        if etichetta in gia_citati:
            return
        riga = (f"{etichetta} | {pulito(scelto['autore']) or 'autore non indicato'} | {pulito(scelto['licenza'])} | "
                f"{pulito(scelto['pagina'] or scelto['url'])}\n")
        with open(crediti, "ab+") as f:
            f.seek(0, os.SEEK_END)
            if f.tell():
                f.seek(-1, os.SEEK_END)
                if f.read(1) != b"\n":
                    f.write(b"\n")
            f.write(riga.encode("utf-8"))
        gia_citati.add(etichetta)
        print(f"   credito aggiunto in fondo a {crediti}")

    soggetti = list(dict.fromkeys(s.strip() for s in soggetti if s.strip()))
    os.makedirs(cartella, exist_ok=True)
    os.makedirs(os.path.dirname(crediti) or ".", exist_ok=True)
    gia_citati = set()
    if os.path.exists(crediti):
        with open(crediti, encoding="utf-8") as f:
            gia_citati = {riga.split(" | ")[0] for riga in f if " | " in riga}
    else:
        with open(crediti, "w", encoding="utf-8", newline="\n") as f:
            f.write(INTESTAZIONE)

    esito = {"salvate": 0, "gia_presenti": 0, "saltate": [], "fallite": [], "interrotto": False}
    print(f"=== Download di {len(soggetti)} immagini '{tipo}' in '{cartella}' ({lato}x{lato}px, WebP) ===")
    print(f"Fonti attive: {', '.join(fonti_attive)} | modalita': {'interattiva' if interattivo else 'automatica'}")
    print(f"Verifica volto: {'attiva' if rilevatore is not None else 'disattivata'} | ritaglio: {ritaglio} | contesto: '{contesto}'")

    with tempfile.TemporaryDirectory() as cartella_tmp:
        for i, nome in enumerate(soggetti, 1):
            etichetta = re.sub(r'[<>:"/\\|?*]', "", nome).strip().rstrip(".")
            destinazione = os.path.join(cartella, f"{etichetta}.webp")
            print(f"\n[{i}/{len(soggetti)}] {nome}")
            if not etichetta:
                print("   FALLITO: nome non utilizzabile come nome file")
                esito["fallite"].append(nome)
                continue
            if os.path.exists(destinazione):
                print("   gia' presente, salto")
                esito["gia_presenti"] += 1
                continue

            parole = [p for p in norm(nome).replace("'", " ").replace("-", " ").split() if len(p) > 2]
            chiavi = [max(parole, key=len)] if parole else [norm(nome)]
            valutati, visti = [], set()
            raccogli(nome, chiavi, 0, valutati, visti)
            valutati.sort(key=lambda v: v["punti"], reverse=True)
            print(f"   candidati validi: {len(valutati)}")

            if interattivo:
                azione, scelto = menu(nome, chiavi, valutati, visti, cartella_tmp)
            elif valutati:
                azione, scelto = "scelta", valutati[0]
                if scelto["punti"] < soglia:
                    print(f"   ATTENZIONE: punteggio basso ({scelto['punti']:.1f}), controlla a mano questa immagine")
            else:
                azione, scelto = "fallita", None

            if scelto is None:
                if azione == "esci":
                    esito["interrotto"] = True
                    print("   uscita richiesta: progresso salvato, rilancia lo script per continuare")
                    break
                saltato = azione == "salta"
                esito["saltate" if saltato else "fallite"].append(nome)
                print("   saltato" if saltato else "   FALLITO: nessuna immagine adatta con licenza libera")
                continue

            modo = ritaglio
            if modo == "volto" and (not scelto["faccia"] or (
                    interattivo and chiedi("   Ritaglio sul volto? (invio = si, n = centrato): ").lower() == "n")):
                modo = "centro"
            print(f"   scelta: {scelto['titolo']} | {scelto['licenza']} | {scelto['fonte']} | ritaglio: {modo}")
            salva(etichetta, destinazione, scelto, modo)
            esito["salvate"] += 1

    print("\n=== Riepilogo ===")
    print(f"Salvate: {esito['salvate']} | Gia' presenti: {esito['gia_presenti']} | "
        f"Saltate: {len(esito['saltate'])} | Fallite: {len(esito['fallite'])}")
    if esito["interrotto"]:
        print(f"Interrotto prima della fine: restano {len(soggetti) - i + 1} soggetti da elaborare")
    if esito["fallite"] or esito["saltate"]:
        print("Da cercare a mano: " + ", ".join(esito["fallite"] + esito["saltate"]))
    print(f"Crediti (da citare per CC BY / CC BY-SA): {crediti}")
    return esito


if __name__ == "__main__":
    scarica_immagini([
        "Gianluigi Buffon", "Andrea Pirlo", "Kakà", "Lothar Matthäus", "Franco Baresi", "Gabriel Batistuta", "Zlatan Ibrahimović", "Andriy Shevchenko", "Ronaldinho", "Samuel Eto'o", "Pavel Nedvěd", "Javier Zanetti", "Giorgio Chiellini", "Leonardo Bonucci", "Daniele De Rossi", "Alessandro Nesta", "Fabio Cannavaro", "Marek Hamšík", "Gonzalo Higuaín", "Lautaro Martínez", "Paulo Dybala", "Nicolo Barella", "Ciro Immobile", "Dusan Vlahovic", "Khvicha Kvaratskhelia", "Victor Osimhen", "Hernán Crespo", "Adriano Leite Ribeiro", "Christian Vieri", "Filippo Inzaghi", "Luca Toni", "Gianluca Vialli", "Roberto Mancini", "Lionel Messi", "Pelé", "Kylian Mbappé", "Erling Haaland", "Neymar Jr", "Robert Lewandowski", "Karim Benzema", "Luka Modrić", "Andrés Iniesta", "Sergio Ramos", "Manuel Neuer", "Kevin De Bruyne", "Mohamed Salah", "Jude Bellingham", "Harry Kane", "Toni Kroos", "Thomas Müller", "Arjen Robben", "David Beckham", "Wayne Rooney", "Gerard Piqué", "Sergio Busquets", "Luis Suárez", "Edinson Cavani", "Sergio Agüero", "Angel Di Maria", "Virgil van Dijk", "Alisson Becker", "Thibaut Courtois", "Romelu Lukaku", "Lamine Yamal", "Samir Handanovič", "Achraf Hakimi", "Francesco Pio Esposito", "Marcus Thuram", "Alessandro Bastoni", "Federico Dimarco", "Lorenzo Palmisani", "Donyell Malen", "Hakan Çalhanoğlu",
    ])