from flask import Flask, jsonify, request, send_from_directory, redirect, session
from supabase import create_client
import os
import requests
import secrets

# =============================================
# CONFIGURATION
# =============================================
SUPABASE_URL = "https://wzsobvmzmpqvmfnwiiza.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Ind6c29idm16bXBxdm1mbndpaXphIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzMyMzIxNDAsImV4cCI6MjA4ODgwODE0MH0.wgWlW0Zc2cip4_2kM4ok-ATDyY83Lf8KYWMUV2TA3WM"
DISCORD_CLIENT_ID = "1481306486390132766"
DISCORD_CLIENT_SECRET = "R-0yI-4M2hOeoU0XgjGQ2M_dC0QhEuOq"
DISCORD_REDIRECT_URI = "https://lbc-finder-web-bot-2-production.up.railway.app/auth/callback"
SECRET_KEY = secrets.token_hex(32)
# =============================================

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
app = Flask(__name__, static_folder="static")
app.secret_key = SECRET_KEY

# ─── AUTH ───────────────────────────────────────

@app.route("/auth/login")
def login():
    return redirect(
        f"https://discord.com/api/oauth2/authorize"
        f"?client_id={DISCORD_CLIENT_ID}"
        f"&redirect_uri={DISCORD_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=identify"
    )

@app.route("/auth/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return redirect("/?error=no_code")

    # Exchange code for token
    token_res = requests.post("https://discord.com/api/oauth2/token", data={
        "client_id": DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": DISCORD_REDIRECT_URI,
    }, headers={"Content-Type": "application/x-www-form-urlencoded"})

    if token_res.status_code != 200:
        return redirect("/?error=token_failed")

    token_data = token_res.json()
    access_token = token_data.get("access_token")

    # Get Discord user info
    user_res = requests.get("https://discord.com/api/users/@me", headers={
        "Authorization": f"Bearer {access_token}"
    })

    if user_res.status_code != 200:
        return redirect("/?error=user_failed")

    user = user_res.json()
    user_id = user["id"]
    username = user["username"]
    avatar = user.get("avatar")
    avatar_url = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar}.png" if avatar else f"https://cdn.discordapp.com/embed/avatars/0.png"

    # Upsert user in Supabase
    supabase.table("users").upsert({
        "id": user_id,
        "username": username,
        "avatar_url": avatar_url,
    }).execute()

    session["user_id"] = user_id
    session["username"] = username
    session["avatar_url"] = avatar_url

    return redirect("/")

@app.route("/auth/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/auth/me")
def me():
    if "user_id" not in session:
        return jsonify({"authenticated": False})
    return jsonify({
        "authenticated": True,
        "user_id": session["user_id"],
        "username": session["username"],
        "avatar_url": session["avatar_url"],
    })

# ─── STATIC ─────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

# ─── ALERTS API ─────────────────────────────────

def get_current_user():
    return session.get("user_id")

@app.route("/api/alerts", methods=["GET"])
def get_alerts():
    user_id = get_current_user()
    if not user_id:
        return jsonify({"error": "Non connecté"}), 401
    try:
        res = supabase.table("alerts").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
        return jsonify(res.data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/alerts", methods=["POST"])
def create_alert():
    user_id = get_current_user()
    if not user_id:
        return jsonify({"error": "Non connecté"}), 401
    try:
        data = request.json
        if not data.get("name") or not data.get("keyword"):
            return jsonify({"error": "Nom et mot-clé obligatoires"}), 400
        res = supabase.table("alerts").insert({
            "user_id": user_id,
            "name": data["name"],
            "keyword": data["keyword"],
            "category": data.get("category", "TOUTES_CATEGORIES"),
            "price_min": int(data.get("price_min", 0)),
            "price_max": int(data.get("price_max", 99999)),
        }).execute()
        return jsonify(res.data[0]), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/alerts/<alert_id>", methods=["DELETE"])
def delete_alert(alert_id):
    user_id = get_current_user()
    if not user_id:
        return jsonify({"error": "Non connecté"}), 401
    try:
        supabase.table("alerts").delete().eq("id", alert_id).eq("user_id", user_id).execute()
        supabase.table("feed").delete().eq("alert_id", alert_id).execute()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/alerts/<alert_id>", methods=["PUT"])
def update_alert(alert_id):
    user_id = get_current_user()
    if not user_id:
        return jsonify({"error": "Non connecté"}), 401
    try:
        data = request.json
        res = supabase.table("alerts").update({
            "name": data["name"],
            "keyword": data["keyword"],
            "category": data.get("category", "TOUTES_CATEGORIES"),
            "price_min": int(data.get("price_min", 0)),
            "price_max": int(data.get("price_max", 99999)),
        }).eq("id", alert_id).eq("user_id", user_id).execute()
        return jsonify(res.data[0])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ─── FEED API ────────────────────────────────────

@app.route("/api/feed")
def get_feed():
    user_id = get_current_user()
    if not user_id:
        return jsonify({"error": "Non connecté"}), 401
    try:
        since = request.args.get("since")
        query = supabase.table("feed").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(50)
        if since:
            query = query.gt("created_at", since)
        res = query.execute()
        return jsonify(res.data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
