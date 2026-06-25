import os, logging, json
from datetime import datetime
from groq import Groq
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

client = Groq(api_key=GROQ_API_KEY)
MODEL  = "llama-3.3-70b-versatile"

# ── IDs autorisés ─────────────────────────────────────────────────────────────
RAMZI_ID = 5379708364
AUTHORIZED_USERS = {
    5379708364: "ramzi",
    8924126780: "friend",
}

# ── System prompt Ramzi ───────────────────────────────────────────────────────
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

# ── System prompt utilisateurs généraux ───────────────────────────────────────
SYSTEM_GENERAL = """Tu es LeBoss AI, un agent IA personnel ultra-performant.

━━━ TA PERSONNALITÉ ━━━
- Direct, intelligent, sans blabla inutile
- Tu parles comme un ami expert
- Tu anticipes les besoins avant qu'ils soient exprimés
- Tu es proactif : tu proposes toujours la prochaine étape
- Honnête : si tu ne sais pas, tu le dis clairement
- Jamais "Bien sûr !", "Absolument !", "Certainement !"

━━━ TES DOMAINES ━━━
1. Développement web (Node.js, Python, React, HTML/CSS)
2. Marketing digital et stratégie de contenu
3. Intelligence artificielle et automatisation
4. Business et entrepreneuriat
5. Rédaction en français, anglais et arabe
6. Trading et analyse de marchés
7. Design et créativité

━━━ STYLE ━━━
- Questions simples → réponse courte et directe
- Tâches complexes → structure claire et étapes numérotées
- Code → toujours complet et production-ready
- Adapte la langue à l'utilisateur automatiquement
- Termine toujours par une action concrète ou suggestion"""

PROMPTS = {
    "code": "Tu es un développeur senior expert. Code complet, commenté, production-ready. Directs sans introduction.",
    "web": "Tu es expert web. Génère des sites COMPLETS HTML+CSS+JS en un seul fichier. Design moderne, responsive, vrai contenu.",
    "redac": "Tu es expert en copywriting. Contenu percutant, structuré, adapté à l'audience. Pas de remplissage.",
    "analyse": "Tu es stratège business. Analyse factuelle, recommandations concrètes, plan d'action en 3 étapes.",
    "trade": "Tu es trader expert. Analyse technique précise, gestion du risque toujours mentionnée. Pédagogie avant tout.",
    "marketing": "Tu es expert marketing digital. Stratégies adaptées, KPIs mesurables, outils gratuits privilégiés.",
    "traduit": "Tu es traducteur expert trilingue FR/EN/AR. Traduction naturelle, adaptation culturelle.",
    "resume": "Tu es expert en synthèse. Structure hiérarchique, points clés, actions à retenir.",
}

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

sessions: dict[int, list] = {}
messages_log: list = []
connected_clients: list = []

app = FastAPI(title="LeBoss AI API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def get_system(user_id: int) -> str:
    if user_id == RAMZI_ID:
        return SYSTEM_RAMZI
    return SYSTEM_GENERAL

def get_history(chat_id, system=None):
    if chat_id not in sessions:
        sessions[chat_id] = [{"role": "system", "content": system or SYSTEM_GENERAL}]
    return sessions[chat_id]

def is_authorized(update):
    return update.effective_user.id in AUTHORIZED_USERS

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
    if system is None:
        system = get_system(user_id)
    history = get_history(chat_id, system)
    history.append({"role": "user", "content": user_msg})
    if len(history) > 31:
        system_msg = history[0]
        history = [system_msg] + history[-30:]
        sessions[chat_id] = history
    response = client.chat.completions.create(
        model=MODEL,
        messages=history,
        max_tokens=4096,
        temperature=0.75,
        top_p=0.9,
    )
    reply = response.choices[0].message.content
    history.append({"role": "assistant", "content": reply})
    return reply

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
        "active_sessions": len(sessions),
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
            "LeBoss AI est opérationnel. Je connais tous tes projets.\n\n"
            "Commandes :\n"
            "/code — Dev & programmation\n"
            "/web — Sites web complets\n"
            "/redac — Copywriting & contenu\n"
            "/analyse — Analyse stratégique\n"
            "/trade — Trading & forex\n"
            "/marketing — Marketing digital\n"
            "/traduit — Traduction FR/EN/AR\n"
            "/resume — Synthèse\n"
            "/reset — Nouvelle conversation\n\n"
            "Dis-moi ce dont tu as besoin."
        )
    else:
        msg = (
            f"Salam {first_name} ! 👋\n\n"
            f"Je suis LeBoss AI, ton agent IA personnel.\n\n"
            "Commandes :\n"
            "/code — Dev & programmation\n"
            "/web — Sites web complets\n"
            "/redac — Copywriting & contenu\n"
            "/analyse — Analyse stratégique\n"
            "/trade — Trading & forex\n"
            "/marketing — Marketing digital\n"
            "/traduit — Traduction FR/EN/AR\n"
            "/resume — Synthèse\n"
            "/reset — Nouvelle conversation\n\n"
            "Dis-moi ce dont tu as besoin."
        )
    await update.message.reply_text(msg)

async def reset(update, context):
    if not is_authorized(update):
        await update.message.reply_text("⛔ Accès non autorisé.")
        return
    sessions[update.effective_chat.id] = []
    await update.message.reply_text("Conversation remise à zéro. 🔄")

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
        sessions[chat_id] = [{"role": "system", "content": system}]
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
        await update.message.reply_text("⛔ Accès non autorisé. Contacte Ramzi pour obtenir l'accès.")
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
    for cmd in PROMPTS:
        telegram_app.add_handler(CommandHandler(cmd, specialized_cmd))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("🚀 LeBoss AI v4 multi-users démarré !")
    telegram_app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()