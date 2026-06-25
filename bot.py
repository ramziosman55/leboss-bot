import os, logging, json, httpx, replicate
from datetime import datetime
from groq import Groq
from supabase import create_client
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application, CommandHandler,
    MessageHandler, filters, ContextTypes,
)
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import threading

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY       = os.getenv("GROQ_API_KEY")
SUPABASE_URL       = os.getenv("SUPABASE_URL")
SUPABASE_KEY       = os.getenv("SUPABASE_KEY")
REPLICATE_API_KEY  = os.getenv("REPLICATE_API_KEY")

os.environ["REPLICATE_API_TOKEN"] = REPLICATE_API_KEY or ""

client = Groq(api_key=GROQ_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
MODEL = "llama-3.3-70b-versatile"

RAMZI_ID = 5379708364
AUTHORIZED_USERS = {
    5379708364: "ramzi",
    8924126780: "friend",
}

SYSTEM_RAMZI = """Tu es LeBoss AI, l'agent IA personnel et exclusif de Ramzi Osmane.

━━━ QUI EST RAMZI ━━━
- Tunisien, basé à La Soukra, Ariana, Tunis
- Diplômé en Marketing avec spécialisation Digital Marketing
- Stage chez Arkan.tn comme Community Manager
- Décorateur d'intérieur indépendant avec atelier (15+ ans)
- Famille gère Chamss Distribution (plomberie, HVAC, piscine)
- Développe Glojia : marque skincare sur Shopify
- Apprend le trading : forex, EUR/USD, TradingView
- Construit son écosystème d'agents IA

━━━ TES PROJETS ━━━
1. Chamss Distribution — Node.js, Supabase, e-commerce
2. Glojia Skincare — Shopify, palette bordeaux/rose vif
3. LeBoss AI Bot — Python, Groq, FastAPI, Railway
4. Arkan.tn — stage terminé, e-réputation

━━━ TA PERSONNALITÉ ━━━
- Direct, sans blabla inutile
- Ami expert qui connaît toute la vie de Ramzi
- Proactif : tu anticipes toujours la prochaine étape
- Honnête et concret
- Réponds en français sauf si Ramzi écrit autrement
- Jamais "Bien sûr !", "Absolument !", "Certainement !"
- Termine toujours par une action concrète"""

SYSTEM_GENERAL = """Tu es LeBoss AI, un agent IA personnel ultra-performant.

━━━ TA PERSONNALITÉ ━━━
- Direct, intelligent, sans blabla inutile
- Tu parles comme un ami expert
- Tu anticipes les besoins avant qu'ils soient exprimés
- Proactif : tu proposes toujours la prochaine étape
- Honnête : si tu ne sais pas, tu le dis clairement
- Jamais "Bien sûr !", "Absolument !", "Certainement !"

━━━ TES DOMAINES ━━━
1. Développement web
2. Marketing digital
3. Intelligence artificielle
4. Business et entrepreneuriat
5. Rédaction multilingue
6. Trading et analyse

━━━ STYLE ━━━
- Questions simples → réponse courte et directe
- Tâches complexes → structure claire et étapes numérotées
- Code → toujours complet et production-ready
- Adapte la langue à l'utilisateur automatiquement"""

PROMPTS = {
    "code": "Tu es un développeur senior expert. Code complet, commenté, production-ready.",
    "web": "Tu es expert web. Génère des sites COMPLETS HTML+CSS+JS en un seul fichier. Design moderne, responsive.",
    "redac": "Tu es expert en copywriting. Contenu percutant, structuré, adapté à l'audience.",
    "analyse": "Tu es stratège business. Analyse factuelle, recommandations concrètes, plan d'action.",
    "trade": "Tu es trader expert. Analyse technique précise, gestion du risque toujours mentionnée.",
    "marketing": "Tu es expert marketing digital. Stratégies adaptées, KPIs mesurables.",
    "traduit": "Tu es traducteur expert trilingue FR/EN/AR. Traduction naturelle, adaptation culturelle.",
    "resume": "Tu es expert en synthèse. Structure hiérarchique, points clés, actions à retenir.",
}

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

messages_log: list = []
connected_clients: list = []

app = FastAPI(title="LeBoss AI API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def get_system(user_id: int) -> str:
    return SYSTEM_RAMZI if user_id == RAMZI_ID else SYSTEM_GENERAL

def is_authorized(update):
    return update.effective_user.id in AUTHORIZED_USERS

def save_message(chat_id, user_id, role, content):
    try:
        supabase.table("conversations").insert({
            "chat_id": chat_id,
            "user_id": user_id,
            "role": role,
            "content": content,
        }).execute()
    except Exception as e:
        logger.error(f"Supabase save error: {e}")

def load_history(chat_id, user_id):
    try:
        result = supabase.table("conversations")\
            .select("role,content")\
            .eq("chat_id", chat_id)\
            .order("created_at", desc=False)\
            .limit(30)\
            .execute()
        history = [{"role": r["role"], "content": r["content"]} for r in result.data]
        system = get_system(user_id)
        return [{"role": "system", "content": system}] + history
    except Exception as e:
        logger.error(f"Supabase load error: {e}")
        return [{"role": "system", "content": get_system(user_id)}]

def clear_history(chat_id):
    try:
        supabase.table("conversations")\
            .delete()\
            .eq("chat_id", chat_id)\
            .execute()
    except Exception as e:
        logger.error(f"Supabase clear error: {e}")

async def send_long(update, text):
    for i in range(0, len(text), 4096):
        await update.message.reply_text(text[i:i+4096])

async def broadcast(data: dict):
    msg = json.dumps(data, ensure_ascii=False)
    dead = []
    for ws in connected_clients:
        try:
            await ws.send_text(msg)
        except:
            dead.append(ws)
    for ws in dead:
        connected_clients.remove(ws)

async def ask_groq(chat_id, user_id, user_msg, system=None):
    history = load_history(chat_id, user_id)
    if system:
        history[0] = {"role": "system", "content": system}
    history.append({"role": "user", "content": user_msg})
    response = client.chat.completions.create(
        model=MODEL,
        messages=history,
        max_tokens=4096,
        temperature=0.75,
        top_p=0.9,
    )
    reply = response.choices[0].message.content
    save_message(chat_id, user_id, "user", user_msg)
    save_message(chat_id, user_id, "assistant", reply)
    return reply

async def generate_image_flux(prompt: str) -> bytes:
    output = replicate.run(
        "black-forest-labs/flux-schnell",
        input={
            "prompt": prompt,
            "num_outputs": 1,
            "aspect_ratio": "1:1",
            "output_format": "webp",
            "output_quality": 90
        }
    )
    image_url = output[0]
    async with httpx.AsyncClient(timeout=60) as http:
        resp = await http.get(str(image_url))
        return resp.content

@app.get("/")
def root():
    return {"status": "LeBoss AI en ligne", "time": datetime.now().isoformat()}

@app.get("/messages")
def get_messages():
    return {"messages": messages_log[-50:]}

@app.get("/stats")
def get_stats():
    return {
        "total_messages": len(messages_log),
        "active_sessions": 0,
        "bot_status": "online"
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    try:
        await websocket.send_text(json.dumps({
            "type": "history",
            "messages": messages_log[-20:]
        }))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in connected_clients:
            connected_clients.remove(websocket)

async def start(update, context):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
    if not is_authorized(update):
        await update.message.reply_text("⛔ Accès non autorisé. Contacte Ramzi pour obtenir l'accès.")
        return
    if user_id == RAMZI_ID:
        msg = (
            "Salam Ramzi ! 👋\n\n"
            "LeBoss AI v7 est opérationnel.\n\n"
            "Commandes :\n"
            "/code — Dev & programmation\n"
            "/web — Sites web complets\n"
            "/image — Générer une image HD (Flux AI)\n"
            "/redac — Copywriting & contenu\n"
            "/analyse — Analyse stratégique\n"
            "/trade — Trading & forex\n"
            "/marketing — Marketing digital\n"
            "/traduit — Traduction FR/EN/AR\n"
            "/resume — Synthèse\n"
            "/reset — Effacer la mémoire\n\n"
            "Dis-moi ce dont tu as besoin."
        )
    else:
        msg = (
            f"Salam {first_name} ! 👋\n\n"
            f"Je suis LeBoss AI, ton agent IA personnel.\n\n"
            "Commandes :\n"
            "/code — Dev & programmation\n"
            "/web — Sites web complets\n"
            "/image — Générer une image HD\n"
            "/redac — Copywriting & contenu\n"
            "/analyse — Analyse stratégique\n"
            "/trade — Trading & forex\n"
            "/marketing — Marketing digital\n"
            "/traduit — Traduction FR/EN/AR\n"
            "/resume — Synthèse\n"
            "/reset — Effacer la mémoire\n\n"
            "Dis-moi ce dont tu as besoin."
        )
    await update.message.reply_text(msg)

async def reset(update, context):
    if not is_authorized(update):
        await update.message.reply_text("⛔ Accès non autorisé.")
        return
    chat_id = update.effective_chat.id
    clear_history(chat_id)
    await update.message.reply_text("Mémoire effacée. 🔄")

async def image_cmd(update, context):
    if not is_authorized(update):
        await update.message.reply_text("⛔ Accès non autorisé.")
        return
    chat_id = update.effective_chat.id
    user_input = " ".join(context.args)
    if not user_input:
        await update.message.reply_text(
            "Décris l'image que tu veux générer.\n\n"
            "Ex: /image logo Glojia skincare minimal burgundy white\n"
            "Ex: /image modern villa Tunisia sunset ocean view\n"
            "Ex: /image product photo skincare bottle luxury"
        )
        return
    await context.bot.send_chat_action(chat_id=chat_id, action="upload_photo")
    await update.message.reply_text("🎨 Génération HD en cours... (15-30 secondes)")
    try:
        image_bytes = await generate_image_flux(user_input)
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=image_bytes,
            caption=f"🎨 {user_input}"
        )
    except Exception as e:
        await update.message.reply_text(f"Erreur génération : {str(e)}")

async def specialized_cmd(update, context):
    if not is_authorized(update):
        await update.message.reply_text("⛔ Accès non autorisé.")
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    cmd = update.message.text.split()[0].lstrip("/").split("@")[0]
    user_input = " ".join(context.args)
    if not user_input:
        hints = {
            "code": "Ex: /code API REST Node.js avec auth JWT",
            "web": "Ex: /web landing page moderne pour une boutique",
            "redac": "Ex: /redac post LinkedIn sur l'IA",
            "analyse": "Ex: /analyse marché e-commerce Tunisie 2025",
            "trade": "Ex: /trade analyse EUR/USD H4",
            "marketing": "Ex: /marketing stratégie Instagram boutique",
            "traduit": "Ex: /traduit en anglais : mon texte ici",
            "resume": "Ex: /resume [colle ton texte]",
        }
        await update.message.reply_text(hints.get(cmd, f"Ajoute ta demande après /{cmd}"))
        return
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    try:
        system = PROMPTS.get(cmd, get_system(user_id))
        reply = await ask_groq(chat_id, user_id, user_input, system=system)
        await send_long(update, reply)
        log_entry = {
            "type": "message",
            "from": update.effective_user.first_name,
            "cmd": cmd,
            "input": user_input[:100],
            "reply": reply[:200],
            "time": datetime.now().strftime("%H:%M:%S")
        }
        messages_log.append(log_entry)
        await broadcast(log_entry)
    except Exception as e:
        await update.message.reply_text(f"Erreur : {str(e)}")

async def handle_message(update, context):
    if not is_authorized(update):
        await update.message.reply_text("⛔ Accès non autorisé. Contacte Ramzi.")
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    try:
        reply = await ask_groq(chat_id, user_id, update.message.text)
        await send_long(update, reply)
        log_entry = {
            "type": "message",
            "from": update.effective_user.first_name,
            "cmd": "chat",
            "input": update.message.text[:100],
            "reply": reply[:200],
            "time": datetime.now().strftime("%H:%M:%S")
        }
        messages_log.append(log_entry)
        await broadcast(log_entry)
    except Exception as e:
        await update.message.reply_text(f"Erreur : {str(e)}")

def run_api():
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")

def main():
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN manquant")
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY manquant")
    api_thread = threading.Thread(target=run_api, daemon=True)
    api_thread.start()
    logger.info("🌐 API démarrée sur http://localhost:8000")
    telegram_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("reset", reset))
    telegram_app.add_handler(CommandHandler("image", image_cmd))
    for cmd in PROMPTS:
        telegram_app.add_handler(CommandHandler(cmd, specialized_cmd))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("🚀 LeBoss AI v7 avec Flux HD démarré !")
    telegram_app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()