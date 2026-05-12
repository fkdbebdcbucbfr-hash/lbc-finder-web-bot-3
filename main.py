import time
import logging
import threading
import requests
from datetime import datetime
from supabase import create_client
import lbc
from lbc import Sort

# =============================================
# CONFIGURATION
# =============================================
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://wzsobvmzmpqvmfnwiiza.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Ind6c29idm16bXBxdm1mbndpaXphIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzMyMzIxNDAsImV4cCI6MjA4ODgwODE0MH0.wgWlW0Zc2cip4_2kM4ok-ATDyY83Lf8KYWMUV2TA3WM")
CHECK_INTERVAL = 10
# =============================================

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
log = logging.getLogger(__name__)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
seen_ads = {}  # { alert_id: set of ad ids }

CATEGORY_MAP = {
    "TOUTES_CATEGORIES": lbc.Category.TOUTES_CATEGORIES,
    "ELECTRONIQUE_CONSOLES": lbc.Category.ELECTRONIQUE_CONSOLES,
    "ELECTRONIQUE_JEUX_VIDEO": lbc.Category.ELECTRONIQUE_JEUX_VIDEO,
    "ELECTRONIQUE_TELEPHONES_ET_OBJETS_CONNECTES": lbc.Category.ELECTRONIQUE_TELEPHONES_ET_OBJETS_CONNECTES,
    "ELECTRONIQUE_ORDINATEURS": lbc.Category.ELECTRONIQUE_ORDINATEURS,
    "ELECTRONIQUE_TABLETTES_ET_LISEUSES": lbc.Category.ELECTRONIQUE_TABLETTES_ET_LISEUSES,
    "ELECTRONIQUE_PHOTO_AUDIO_ET_VIDEO": lbc.Category.ELECTRONIQUE_PHOTO_AUDIO_ET_VIDEO,
    "ELECTRONIQUE_ELECTROMENAGER": lbc.Category.ELECTRONIQUE_ELECTROMENAGER,
    "VEHICULES_VOITURES": lbc.Category.VEHICULES_VOITURES,
    "VEHICULES_MOTOS": lbc.Category.VEHICULES_MOTOS,
    "VEHICULES_VELOS": lbc.Category.VEHICULES_VELOS,
    "IMMOBILIER_VENTES_IMMOBILIERES": lbc.Category.IMMOBILIER_VENTES_IMMOBILIERES,
    "IMMOBILIER_LOCATIONS": lbc.Category.IMMOBILIER_LOCATIONS,
    "MODE_VETEMENTS": lbc.Category.MODE_VETEMENTS,
    "MODE_CHAUSSURES": lbc.Category.MODE_CHAUSSURES,
    "LOISIRS_LIVRES": lbc.Category.LOISIRS_LIVRES,
    "LOISIRS_JEUX_ET_JOUETS": lbc.Category.LOISIRS_JEUX_ET_JOUETS,
    "LOISIRS_SPORT_ET_PLEIN_AIR": lbc.Category.LOISIRS_SPORT_ET_PLEIN_AIR,
    "LOISIRS_INSTRUMENTS_DE_MUSIQUE": lbc.Category.LOISIRS_INSTRUMENTS_DE_MUSIQUE,
    "MAISON_ET_JARDIN_AMEUBLEMENT": lbc.Category.MAISON_ET_JARDIN_AMEUBLEMENT,
    "ANIMAUX_ANIMAUX": lbc.Category.ANIMAUX_ANIMAUX,
    "FAMILLE_JEUX_ET_JOUETS": lbc.Category.FAMILLE_JEUX_ET_JOUETS,
}

def save_new_ad(alert_id, user_id, ad):
    """Save a new ad to Supabase for real-time feed"""
    try:
        ad_time = ad.first_publication_date
        if isinstance(ad_time, str):
            ad_time = datetime.strptime(ad_time, "%Y-%m-%d %H:%M:%S")
        diff = (datetime.now() - ad_time).total_seconds()
        if diff > 300:
            return

        image_url = ad.images[0] if ad.images else None
        supabase.table("feed").insert({
            "alert_id": str(alert_id),
            "user_id": str(user_id),
            "title": ad.subject,
            "price": ad.price,
            "url": ad.url,
            "image_url": image_url,
        }).execute()
        log.info(f"New ad saved for user {user_id}: {ad.subject}")
    except Exception as e:
        log.error(f"Error saving ad: {e}")

def search_alert(alert):
    try:
        alert_id = alert["id"]
        user_id = alert["user_id"]

        if alert_id not in seen_ads:
            seen_ads[alert_id] = set()

        client = lbc.Client()
        category = CATEGORY_MAP.get(alert["category"], lbc.Category.TOUTES_CATEGORIES)
        result = client.search(
            text=alert["keyword"],
            category=category,
            price=[alert["price_min"], alert["price_max"]],
            sort=Sort.NEWEST
        )
        for ad in result.ads:
            if ad.id not in seen_ads[alert_id]:
                seen_ads[alert_id].add(ad.id)
                save_new_ad(alert_id, user_id, ad)
    except Exception as e:
        log.error(f"Search error [{alert.get('name')}]: {e}")

def bot_loop():
    log.info("🤖 LBC Finder Bot started!")
    while True:
        try:
            res = supabase.table("alerts").select("*").execute()
            alerts = res.data or []
            log.info(f"🔍 {len(alerts)} active alert(s)")
            for alert in alerts:
                thread = threading.Thread(target=search_alert, args=(alert,))
                thread.start()
        except Exception as e:
            log.error(f"Bot loop error: {e}")
        time.sleep(CHECK_INTERVAL)

bot_thread = threading.Thread(target=bot_loop, daemon=True)
bot_thread.start()

from app import app
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
