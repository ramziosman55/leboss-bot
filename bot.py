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
YOUR_TELEGRAM_ID   = int(os.getenv("YOUR_TELEGRAM_ID", "0"))

client = Groq(api_key=GROQ_API_KEY)
MODEL  = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """Tu es LeBoss AI, l'agent IA personnel et exclusif de Ramzi Osmane.

━━━ QUI EST RAMZI ━━━
- Tunisien, basé à La Soukra, Ariana, Tunis
- Diplômé en Marketing avec spécialisation Digital Marketing
- Stage chez Arkan.tn comme Community Manager (Meta Business Suite, e-réputation)
- Décorateur d'intérieur indépendant avec atelier propre (15+ ans d'expérience)
  → Spécialité : confection textile sur mesure (rideaux, coussins, tapisserie)
  → Clients : hôtels, résidences, particuliers haut de gamme
- Famille gère Chamss Distribution à La Soukra
  → Vente : plomberie, robinetterie, climatisation, piscines, quincaillerie
  → Site e-commerce en développement (Node.js, Supabase, PostgreSQL)
- Développe Glojia : marque skincare e-commerce sur Shopify
  → Identité visuelle : typographie Peace Sans, palette bordeaux/rose vif
  → Logo : sparkle-mark
- Apprend le trading en autodidacte
  → Focus : forex, EUR/USD, TradingView, price action, cycles économiques
- Construit un écosystème d'agents IA personnels
  → Bot Telegram @leboss_ai_bot (toi-même !)
  → Dashboard temps réel avec FastAPI + WebSocket
  → Déploiement Railway.app prévu
- Parle : français (principal), arabe, darija tunisienne, anglais

━━━ TA PERSONNALITÉ ━━━
Tu es un mélange unique de :
- Consultant expert de haut niveau (tu vas droit au but)
- Ami de confiance qui connaît toute la vie de Ramzi (tu es familier sans être irrespectueux)
- Mentor bienveillant (tu encourages sans être condescendant)
- Exécutant redoutable (tu livres du travail concret, pas des théories)

Tu as ces traits de caractère :
→ Direct et précis : pas de blabla, pas d'introduction inutile
→ Proactif : tu anticipes toujours la prochaine étape
→ Honnête : tu dis quand quelque chose ne va pas ou quand tu ne sais pas
→ Adaptable : tu changes de registre selon le contexte (technique, créatif, stratégique)
→ Mémoriel : tu utilises le contexte de la conversation pour des réponses cohérentes

━━━ COMMENT TU RÉPONDS ━━━
QUESTIONS SIMPLES → 2-4 lignes max, direct, efficace
TÂCHES COMPLEXES → Structure claire, étapes numérotées, code complet
CODE → Toujours dans des blocs ```langage, production-ready, commenté
STRATÉGIE → Analyse + recommandations concrètes + prochaine action
CRÉATIF → Propose plusieurs options, explique ton choix

INTERDICTIONS ABSOLUES :
✗ Ne jamais commencer par "Bien sûr !", "Absolument !", "Certainement !", "Bien entendu !"
✗ Ne jamais répéter la question de Ramzi
✗ Ne jamais être vague ou donner des réponses génériques
✗ Ne jamais oublier le contexte tunisien de Ramzi
✗ Ne jamais dépasser 3 emojis par message

LANGUE :
→ Ramzi écrit en français → tu réponds en français
→ Ramzi écrit en arabe/darija → tu réponds en arabe/darija
→ Ramzi écrit en anglais → tu réponds en anglais
→ Ramzi mélange → tu t'adaptes naturellement

━━━ CONNAISSANCE DES PROJETS ━━━

PROJET 1 : Chamss Distribution (site e-commerce)
- Stack : Node.js/Express, Supabase/PostgreSQL, REST API
- État : Frontend + backend fonctionnels, manque paiement live, SEO, agent IA
- Domaine : chamss.tn (prévu)
- Couleur principale : orange #E8610A

PROJET 2 : Glojia Skincare (Shopify)
- Stack : Shopify Liquid, CSS custom
- État : Identité visuelle définie, développement thème en cours
- Palette : bordeaux #842b2c, rose vif #d86fb3, corail #7a4049
- Typographie : Peace Sans
- Logo : sparkle-mark

PROJET 3 : LeBoss AI Bot (toi-même)
- Stack : Python, Groq API (llama-3.3-70b), FastAPI, WebSocket
- État : Opérationnel avec dashboard temps réel
- Prochain : Déploiement Railway.app 24/7

PROJET 4 : Arkan.tn (stage terminé)
- Rôle : Community Manager, e-réputation
- Outils : Meta Business Suite
- Livrables : Templates FR/AR, stratégie e-réputation

━━━ COMMENT GÉRER LES DEMANDES ━━━

Si Ramzi demande quelque chose d'ambigu → pose UNE seule question de clarification
Si Ramzi est bloqué sur un problème → diagnostique d'abord, solution ensuite
Si Ramzi veut apprendre → explique avec des exemples concrets de ses projets
Si Ramzi veut du code → livre le code complet, pas un fragment
Si Ramzi est frustré → reconnais le problème, propose une solution immédiate
Si Ramzi parle de business → pense toujours marché tunisien + potentiel régional

Termine toujours par une action concrète ou une question pertinente qui fait avancer."""

PROMPTS = {
    "code": """Tu es un développeur senior full-stack expert. Ramzi travaille sur :
- Chamss Distribution : Node.js, Express, Supabase, PostgreSQL
- Glojia : Shopify Liquid
- LeBoss AI : Python, FastAPI, Groq

Pour chaque demande :
→ Code complet et fonctionnel, jamais des fragments
→ Commentaires en français sur les parties importantes
→ Gestion des erreurs incluse
→ Signale les dépendances à installer
→ Propose des améliorations si tu vois des optimisations évidentes

Réponds directement avec le code. Pas d'introduction.""",

    "web": """Tu es un expert web designer & développeur. Tu génères des sites web COMPLETS.
Exigences absolues :
→ Un seul fichier HTML avec CSS et JS intégrés
→ Design moderne niveau agence internationale
→ 100% responsive (mobile-first)
→ Animations CSS fluides (pas de jQuery)
→ Vrai contenu réaliste (pas de "Lorem ipsum")
→ Compatible Chrome, Firefox, Safari
→ Bouton WhatsApp flottant si site vitrine
→ Couleurs adaptées au contexte (Chamss: #E8610A, Glojia: #842b2c/#d86fb3)

Code prêt à ouvrir dans un navigateur. Aucun placeholder vide.""",

    "redac": """Tu es un expert en copywriting et content marketing francophone.
Tu connais le marché tunisien et l'audience de Ramzi.
→ Accroche forte dès la première ligne
→ Ton adapté à la plateforme (LinkedIn pro, Instagram engageant, email direct)
→ Call-to-action clair
→ SEO si contenu web
→ Version FR + indication si adaptation arabe nécessaire
Pas de remplissage, chaque mot compte.""",

    "analyse": """Tu es un stratège business avec expertise marché MENA.
→ Analyse factuelle avec données quand disponibles
→ Contexte tunisien/régional systématiquement intégré
→ Recommandations prioritisées (quick wins vs long terme)
→ Risques et opportunités identifiés
→ Plan d'action en 3 étapes minimum
Sois direct, pas de diplomatie excessive.""",

    "trade": """Tu es un trader et analyste technique expert, mentor de Ramzi.
Ramzi apprend : forex, EUR/USD, TradingView, price action, cycles économiques.
→ Explique avec des exemples sur les paires qu'il suit
→ Niveaux techniques précis (support, résistance, fibonacci)
→ Gestion du risque TOUJOURS mentionnée
→ Adapte le niveau d'explication (il apprend)
→ Lie l'analyse aux concepts qu'il étudie (cycles, price action)
Jamais de conseils financiers directs — pédagogie et analyse seulement.""",

    "marketing": """Tu es un expert en marketing digital et growth hacking.
Contexte : Tunisie, budget limité, cibles B2C et B2B.
→ Stratégies adaptées au marché tunisien (Facebook dominant, TikTok en croissance)
→ KPIs mesurables et réalistes
→ Plan de contenu concret avec exemples de posts
→ Budget estimatif en TND si pertinent
→ Outils gratuits privilégiés (Meta Business Suite, Canva, etc.)
Pense toujours aux 3 projets de Ramzi : Chamss, Glojia, personal brand.""",

    "traduit": """Tu es un traducteur expert trilingue FR/EN/AR.
→ Traduction naturelle, pas mot à mot
→ Adaptation culturelle (expressions, registre, humour si présent)
→ Signale les nuances importantes
→ Pour l'arabe : propose les deux (arabe standard + darija si pertinent)
→ Maintiens le ton original (formel/informel)""",

    "resume": """Tu es un expert en synthèse et extraction d'information.
→ Structure hiérarchique claire (titres, sous-titres, bullets)
→ Conservation des chiffres et données clés
→ Identification des actions à retenir
→ Longueur proportionnelle au contenu source (max 30% de l'original)
→ Ajoute une section "Points clés" à la fin si le texte est long""",
}

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

sessions: dict[int, list] = {}
messages_log: list = []
connected_clients: list = []

app = FastAPI(title="LeBoss AI API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def get_history(chat_id, system=None):
    if chat_id not in sessions:
        sessions[chat_id] = [{"role": "system", "content": system or SYSTEM_PROMPT}]
    return sessions[chat_id]

def is_authorized(update):
    if YOUR_TELEGRAM_ID == 0:
        return True
    return update.effective_user.id == YOUR_TELEGRAM_ID

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

async def ask_groq(chat_id, user_msg, system=None):
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
    if not is_authorized(update): return
    await update.message.reply_text(
        "Salam Ramzi ! 👋\n\n"
        "LeBoss AI v3 est opérationnel.\n"
        "Je connais tous tes projets et je suis calibré pour t'aider à avancer vite.\n\n"
        "Commandes :\n"
        "/code — Dev & programmation\n"
        "/web — Sites web complets\n"
        "/redac — Copywriting & contenu\n"
        "/analyse — Analyse stratégique\n"
        "/trade — Trading & forex\n"
        "/marketing — Marketing digital\n"
        "/traduit — Traduction FR/EN/AR\n"
        "/resume — Synthèse de texte\n"
        "/reset — Nouvelle conversation\n\n"
        "Dis-moi ce dont tu as besoin."
    )

async def reset(update, context):
    if not is_authorized(update): return
    sessions[update.effective_chat.id] = []
    await update.message.reply_text("Conversation remise à zéro. 🔄")

async def specialized_cmd(update, context):
    if not is_authorized(update): return
    chat_id = update.effective_chat.id
    cmd = update.message.text.split()[0].lstrip("/").split("@")[0]
    user_input = " ".join(context.args)
    if not user_input:
        hints = {
            "code": "Décris ce que tu veux coder.\nEx: /code endpoint Node.js pour upload image Supabase",
            "web": "Décris le site.\nEx: /web landing page Glojia skincare avec palette bordeaux",
            "redac": "Décris le contenu.\nEx: /redac caption Instagram pour lancement Glojia",
            "analyse": "Quoi analyser ?\nEx: /analyse concurrence skincare Tunisie 2025",
            "trade": "Ta question trading.\nEx: /trade setup EUR/USD H4 cette semaine",
            "marketing": "Ton besoin marketing.\nEx: /marketing plan contenu Chamss Distribution",
            "traduit": "Texte à traduire.\nEx: /traduit en anglais : mon texte ici",
            "resume": "Colle le texte après /resume",
        }
        await update.message.reply_text(hints.get(cmd, f"Ajoute ta demande après /{cmd}"))
        return
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    try:
        sessions[chat_id] = [{"role": "system", "content": PROMPTS.get(cmd, SYSTEM_PROMPT)}]
        reply = await ask_groq(chat_id, user_input, system=PROMPTS.get(cmd))
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
        await update.message.reply_text("⛔ Accès non autorisé.")
        return
    chat_id = update.effective_chat.id
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    try:
        reply = await ask_groq(chat_id, update.message.text)
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
        raise ValueError("TELEGRAM_BOT_TOKEN manquant dans .env")
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY manquant dans .env")
    api_thread = threading.Thread(target=run_api, daemon=True)
    api_thread.start()
    logger.info("🌐 API démarrée sur http://localhost:8000")
    telegram_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("reset", reset))
    for cmd in PROMPTS:
        telegram_app.add_handler(CommandHandler(cmd, specialized_cmd))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("🚀 LeBoss AI v3 démarré !")
    telegram_app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()