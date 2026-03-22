import telebot
import requests
import json
import os
import schedule
import time
import threading
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv(r"C:\Users\leoqu\Desktop\.env")

# ===========================================================
#  CONFIGURATION
# ===========================================================
BOT_TOKEN      = os.environ.get("MARKETING_BOT_TOKEN")
ADMIN_ID       = int(os.environ.get("ADMIN_ID", "0"))
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

if not BOT_TOKEN:
    raise ValueError("❌ Variable MARKETING_BOT_TOKEN manquante !")
if not GROQ_API_KEY:
    raise ValueError("❌ Variable GROQ_API_KEY manquante !")

bot = telebot.TeleBot(BOT_TOKEN)

USERS_FILE   = "marketing_users.json"
PROFILE_FILE = "profiles.json"

# ============================================================
#  GESTION UTILISATEURS & PROFILS
# ============================================================

def load_users():
    if not os.path.exists(USERS_FILE):
        save_users([])
    with open(USERS_FILE, "r") as f:
        return json.load(f).get("allowed", [])

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump({"allowed": users}, f, indent=2)

def is_admin(uid):   return uid == ADMIN_ID
def is_authorized(uid): return is_admin(uid) or uid in load_users()

def load_profiles():
    if not os.path.exists(PROFILE_FILE):
        return {}
    with open(PROFILE_FILE, "r") as f:
        return json.load(f)

def save_profiles(profiles):
    with open(PROFILE_FILE, "w") as f:
        json.dump(profiles, f, indent=2, ensure_ascii=False)

def get_profile(uid):
    return load_profiles().get(str(uid), {})

def save_profile(uid, profile):
    profiles = load_profiles()
    profiles[str(uid)] = profile
    save_profiles(profiles)


# ============================================================
#  APPEL CLAUDE API
# ============================================================

def ask_claude(prompt, system=None):
    """Appelle l'API Groq (gratuit) et retourne la réponse"""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": messages,
                "max_tokens": 1500,
                "temperature": 0.8,
            },
            timeout=30
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Erreur Groq API : {e}")
        return None

def get_system_prompt(profile):
    niche  = profile.get("niche", "coaching / formation")
    cible  = profile.get("cible", "entrepreneurs et personnes en reconversion")
    ton    = profile.get("ton", "inspirant, direct et authentique")
    langue = profile.get("langue", "français")
    return (
        f"Tu es un expert en marketing digital spécialisé en {niche}. "
        f"Ta cible est : {cible}. "
        f"Ton style de communication est : {ton}. "
        f"Tu réponds toujours en {langue}. "
        f"RÈGLES DE FORMATAGE OBLIGATOIRES :\n"
        f"- Utilise des emojis au début de chaque section\n"
        f"- Utilise *texte* pour mettre en gras les points importants\n"
        f"- Sépare chaque section par une ligne vide\n"
        f"- Utilise des bullet points avec • pour les listes\n"
        f"- Sois concret, direct et actionnable\n"
        f"- Jamais de contenu générique — toujours personnalisé à la niche"
    )


# ============================================================
#  FONCTIONS MARKETING
# ============================================================

def generer_idees(profile, sujet=None):
    sys = get_system_prompt(profile)
    prompt = (
        f"Génère 5 idées de contenu originales et virales pour {profile.get('niche','coaching')}. "
        + (f"Sur le thème : {sujet}. " if sujet else "")
        + "Pour chaque idée donne : le format (TikTok/Reel/Post/Story), l'angle accrocheur, et pourquoi ça va performer. "
        + "Format : numéroté, clair, concis."
    )
    return ask_claude(prompt, sys)

def generer_caption(profile, sujet):
    sys = get_system_prompt(profile)
    prompt = (
        f"Rédige une caption Instagram/TikTok complète pour ce sujet : '{sujet}'. "
        f"Structure : 1 hook percutant (première ligne), corps du message (3-4 lignes), CTA fort, "
        f"puis une liste de 15 hashtags pertinents pour {profile.get('niche','coaching')} en France. "
        f"Rends-la authentique et engageante, pas trop commerciale."
    )
    return ask_claude(prompt, sys)

def generer_script(profile, sujet):
    sys = get_system_prompt(profile)
    prompt = (
        f"Crée un script TikTok/Reel de 30-60 secondes sur : '{sujet}'. "
        f"Structure obligatoire :\n"
        f"🎬 HOOK (0-3s) : phrase qui arrête le scroll\n"
        f"📌 PROBLÈME (3-10s) : le pain point de la cible\n"
        f"💡 VALEUR (10-45s) : le contenu principal avec 3 points clés\n"
        f"🎯 CTA (45-60s) : call-to-action clair\n"
        f"Aussi : indique le ton (voix off ou face caméra), les textes à afficher à l'écran, et les émotions à transmettre."
    )
    return ask_claude(prompt, sys)

def generer_hooks(profile, sujet):
    sys = get_system_prompt(profile)
    prompt = (
        f"Génère 10 accroches publicitaires (hooks) ultra-percutantes pour ce sujet : '{sujet}'.\n"
        f"Pour {profile.get('niche','coaching')}, ciblant {profile.get('cible','entrepreneurs')}.\n\n"
        f"Types de hooks à créer :\n"
        f"- 3 hooks choc (statistique ou fait surprenant)\n"
        f"- 3 hooks question (interpelle directement la cible)\n"
        f"- 2 hooks storytelling (début d'histoire captivante)\n"
        f"- 2 hooks contraire (va à l'encontre des idées reçues)\n\n"
        f"Chaque hook doit tenir en 1-2 phrases maximum et arrêter le scroll instantanément."
    )
    return ask_claude(prompt, sys)

def generer_strategie(profile):
    sys = get_system_prompt(profile)
    prompt = (
        f"Crée une stratégie de contenu complète sur 90 jours pour {profile.get('niche','coaching')}.\n\n"
        f"La stratégie doit inclure :\n"
        f"1. POSITIONNEMENT : comment se démarquer dans la niche\n"
        f"2. PILIERS DE CONTENU : 4-5 thèmes récurrents avec exemples\n"
        f"3. RÉPARTITION PAR PLATEFORME : TikTok, Instagram, YouTube (fréquence et format)\n"
        f"4. PLAN 30/60/90 JOURS : objectifs et actions par phase\n"
        f"   - Mois 1 : Construction de l'audience\n"
        f"   - Mois 2 : Engagement et autorité\n"
        f"   - Mois 3 : Conversion et ventes\n"
        f"5. MÉTRIQUES À SUIVRE : KPIs importants\n"
        f"6. ERREURS À ÉVITER dans cette niche\n\n"
        f"Sois très concret et actionnable."
    )
    return ask_claude(prompt, sys)

def analyser_concurrence(profile, concurrent):
    sys = get_system_prompt(profile)
    prompt = (
        f"Analyse le concurrent suivant dans la niche {profile.get('niche','coaching')} : '{concurrent}'.\n\n"
        f"Fais une analyse complète :\n"
        f"1. FORCES PROBABLES : ce qu'il fait bien (contenu, positionnement, offre)\n"
        f"2. FAIBLESSES PROBABLES : ce qu'il ne couvre pas ou mal\n"
        f"3. OPPORTUNITÉS : comment se différencier de lui\n"
        f"4. ANGLES INEXPLOITÉS : sujets ou formats qu'il n'utilise pas\n"
        f"5. STRATÉGIE DE DIFFÉRENCIATION : comment le surpasser concrètement\n\n"
        f"Base ton analyse sur les tendances du marché et les meilleures pratiques en {profile.get('niche','coaching')}."
    )
    return ask_claude(prompt, sys)

def analyser_compte(profile, description):
    sys = get_system_prompt(profile)
    prompt = (
        f"Analyse ce compte de réseaux sociaux et donne des recommandations :\n\n"
        f"Description du compte : {description}\n\n"
        f"Analyse :\n"
        f"1. POINTS FORTS : ce qui fonctionne bien\n"
        f"2. POINTS FAIBLES : ce qui freine la croissance\n"
        f"3. BIO & PROFIL : optimisation suggérée\n"
        f"4. STRATÉGIE DE CONTENU : ce qui manque\n"
        f"5. MONÉTISATION : comment mieux convertir l'audience\n"
        f"6. PLAN D'ACTION : 5 actions prioritaires à faire cette semaine\n\n"
        f"Sois direct, précis et actionnable."
    )
    return ask_claude(prompt, sys)

def generer_tunnel(profile, offre):
    sys = get_system_prompt(profile)
    prompt = (
        f"Crée un tunnel de vente complet pour cette offre : '{offre}'.\n"
        f"Pour {profile.get('niche','coaching')}, ciblant {profile.get('cible','entrepreneurs')}.\n\n"
        f"Structure du tunnel :\n\n"
        f"🎯 ÉTAPE 1 — ATTRACTION (Réseaux sociaux)\n"
        f"- Type de contenu pour attirer la cible\n"
        f"- Hook pour le post/vidéo d'entrée\n"
        f"- CTA pour amener vers l'étape 2\n\n"
        f"📧 ÉTAPE 2 — CAPTURE (Lead Magnet)\n"
        f"- Idée de lead magnet gratuit irrésistible\n"
        f"- Titre accrocheur du lead magnet\n"
        f"- Texte de la page de capture (50 mots)\n\n"
        f"💌 ÉTAPE 3 — NURTURING (Email séquence)\n"
        f"- Email 1 (J+0) : Bienvenue + valeur immédiate\n"
        f"- Email 2 (J+2) : Histoire + problème résolu\n"
        f"- Email 3 (J+4) : Preuve sociale + témoignage\n"
        f"- Email 4 (J+6) : Présentation de l'offre\n\n"
        f"💰 ÉTAPE 4 — CONVERSION (Page de vente)\n"
        f"- Titre principal de la page de vente\n"
        f"- 3 arguments de vente principaux\n"
        f"- Objections à lever\n"
        f"- CTA final\n\n"
        f"Sois très concret avec des exemples de textes réels."
    )
    return ask_claude(prompt, sys)
    sys = get_system_prompt(profile)
    mois = datetime.now().strftime("%B %Y")
    prompt = (
        f"Crée un calendrier éditorial complet pour {mois} pour {profile.get('niche','coaching')}. "
        f"30 jours de contenu avec pour chaque jour : le jour, le format (TikTok/Reel/Post/Story/Email), "
        f"le sujet précis, et l'objectif (notoriété/engagement/conversion). "
        f"Varie les formats et les thèmes. Inclus des moments forts (lancements, promotions, contenus viraux). "
        f"Format tableau simple et lisible."
    )
    return ask_claude(prompt, sys)


# ============================================================
#  COMMANDES TELEGRAM
# ============================================================

def nettoyer_texte(text):
    """Nettoie le texte pour un affichage propre sur Telegram"""
    import re
    # Remplacer **texte** par texte en gras Telegram
    text = re.sub(r'\*\*(.*?)\*\*', r'*\1*', text)
    # Supprimer les # de titres markdown
    text = re.sub(r'^#{1,4}\s+', '', text, flags=re.MULTILINE)
    # Remplacer les tirets de liste par des emojis
    text = re.sub(r'^\- ', '• ', text, flags=re.MULTILINE)
    # Nettoyer les lignes vides multiples
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def send_long(chat_id, text, reply_to=None):
    text = nettoyer_texte(text)
    MAX = 4000
    chunks, current = [], ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > MAX:
            if current: chunks.append(current)
            current = line
        else:
            current += ("\n" if current else "") + line
    if current: chunks.append(current)
    for i, chunk in enumerate(chunks):
        try:
            if i == 0 and reply_to:
                bot.reply_to(reply_to, chunk, parse_mode="Markdown")
            else:
                bot.send_message(chat_id, chunk, parse_mode="Markdown")
        except:
            # Si Markdown échoue, envoyer sans formatage
            try:
                if i == 0 and reply_to:
                    bot.reply_to(reply_to, chunk)
                else:
                    bot.send_message(chat_id, chunk)
            except Exception as e:
                print(f"Erreur envoi: {e}")


@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "⛔ Accès non autorisé. Contacte l'admin."); return
    profile = get_profile(message.from_user.id)
    configured = "✅" if profile else "⚠️ Non configuré — fais /profil d'abord"
    bot.reply_to(message,
        "👋 Bot Marketing Digital\n\n"
        f"Profil : {configured}\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "⚙️ CONFIGURATION\n"
        "/profil — Configurer ton profil\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🚀 CONTENU\n"
        "/idees — 5 idées de contenu viral\n"
        "/idees [thème] — Idées sur un thème\n"
        "/caption [sujet] — Caption + hashtags\n"
        "/script [sujet] — Script TikTok/Reel\n"
        "/hooks [sujet] — 10 accroches pub\n"
        "/calendrier — Calendrier 30 jours\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📊 STRATÉGIE\n"
        "/strategie — Stratégie 90 jours\n"
        "/tunnel [offre] — Tunnel de vente\n"
        "/concurrent [nom] — Analyse concurrence\n"
        "/compte [description] — Analyse ton compte\n"
    )


@bot.message_handler(commands=["profil"])
def cmd_profil(message):
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "⛔ Accès non autorisé."); return
    profile = get_profile(message.from_user.id)
    profil_actuel = (
        f"📋 Profil actuel :\n"
        f"• Niche : {profile.get('niche','Non défini')}\n"
        f"• Cible : {profile.get('cible','Non défini')}\n"
        f"• Ton : {profile.get('ton','Non défini')}"
        if profile else "⚠️ Aucun profil configuré"
    )
    bot.reply_to(message,
        "⚙️ Configuration de ton profil\n\n"
        "Réponds à ces questions une par une :\n\n"
        "1️⃣ /setniche [ta niche]\n"
        "Ex : /setniche Coaching business pour femmes entrepreneures\n\n"
        "2️⃣ /setcible [ta cible]\n"
        "Ex : /setcible Femmes 25-40 ans qui veulent lancer leur business\n\n"
        "3️⃣ /seton [ton style]\n"
        "Ex : /seton Inspirant, bienveillant, direct et sans bullshit\n\n"
        + profil_actuel
    )


@bot.message_handler(commands=["setniche", "set_niche"])
def cmd_set_niche(message):
    if not is_authorized(message.from_user.id): return
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage : /setniche [ta niche]"); return
    profile = get_profile(message.from_user.id)
    profile["niche"] = parts[1]
    save_profile(message.from_user.id, profile)
    bot.reply_to(message, f"✅ Niche enregistrée : {parts[1]}")


@bot.message_handler(commands=["setcible", "set_cible"])
def cmd_set_cible(message):
    if not is_authorized(message.from_user.id): return
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage : /setcible [ta cible]"); return
    profile = get_profile(message.from_user.id)
    profile["cible"] = parts[1]
    save_profile(message.from_user.id, profile)
    bot.reply_to(message, f"✅ Cible enregistrée : {parts[1]}")


@bot.message_handler(commands=["seton", "set_ton"])
def cmd_set_ton(message):
    if not is_authorized(message.from_user.id): return
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage : /seton [ton style]"); return
    profile = get_profile(message.from_user.id)
    profile["ton"] = parts[1]
    save_profile(message.from_user.id, profile)
    bot.reply_to(message, f"✅ Ton enregistré : {parts[1]}")


@bot.message_handler(commands=["idees"])
def cmd_idees(message):
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "⛔ Accès non autorisé."); return
    profile = get_profile(message.from_user.id)
    if not profile:
        bot.reply_to(message, "⚠️ Configure d'abord ton profil avec /profil"); return

    parts = message.text.split(" ", 1)
    sujet = parts[1] if len(parts) > 1 else None

    bot.reply_to(message, "⏳ Génération des idées en cours...")
    result = generer_idees(profile, sujet)
    if result:
        send_long(message.chat.id, f"💡 *5 IDÉES DE CONTENU*\n\n{result}", reply_to=message)
    else:
        bot.reply_to(message, "❌ Erreur. Réessaie dans quelques secondes.")


@bot.message_handler(commands=["caption"])
def cmd_caption(message):
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "⛔ Accès non autorisé."); return
    profile = get_profile(message.from_user.id)
    if not profile:
        bot.reply_to(message, "⚠️ Configure d'abord ton profil avec /profil"); return

    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage : /caption [sujet]\n_Ex : /caption Les 3 erreurs des coachs débutants_"); return

    bot.reply_to(message, "⏳ Rédaction de ta caption...")
    result = generer_caption(profile, parts[1])
    if result:
        send_long(message.chat.id, f"📝 *CAPTION + HASHTAGS*\n\n{result}", reply_to=message)
    else:
        bot.reply_to(message, "❌ Erreur. Réessaie dans quelques secondes.")


@bot.message_handler(commands=["script"])
def cmd_script(message):
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "⛔ Accès non autorisé."); return
    profile = get_profile(message.from_user.id)
    if not profile:
        bot.reply_to(message, "⚠️ Configure d'abord ton profil avec /profil"); return

    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage : /script [sujet]\n_Ex : /script Comment passer de 0 à 1000€/mois en coaching_"); return

    bot.reply_to(message, "⏳ Création du script TikTok/Reel...")
    result = generer_script(profile, parts[1])
    if result:
        send_long(message.chat.id, f"🎬 *SCRIPT TIKTOK/REEL*\n\n{result}", reply_to=message)
    else:
        bot.reply_to(message, "❌ Erreur. Réessaie dans quelques secondes.")


@bot.message_handler(commands=["calendrier"])
def cmd_calendrier(message):
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "⛔ Accès non autorisé."); return
    profile = get_profile(message.from_user.id)
    if not profile:
        bot.reply_to(message, "⚠️ Configure d'abord ton profil avec /profil"); return

    bot.reply_to(message, "⏳ Création de ton calendrier 30 jours... (peut prendre 20-30 secondes)")
    result = generer_calendrier(profile)
    if result:
        send_long(message.chat.id, f"📅 *CALENDRIER ÉDITORIAL 30 JOURS*\n\n{result}", reply_to=message)
    else:
        bot.reply_to(message, "❌ Erreur. Réessaie dans quelques secondes.")


@bot.message_handler(commands=["adduser"])
def cmd_adduser(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ Admin seulement."); return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        bot.reply_to(message, "Usage : /adduser ID"); return
    uid = int(parts[1])
    users = load_users()
    if uid in users:
        bot.reply_to(message, "ℹ️ Déjà autorisé."); return
    users.append(uid); save_users(users)
    bot.reply_to(message, f"✅ {uid} ajouté.")
    try: bot.send_message(uid, "✅ Accès accordé ! Envoie /start")
    except: pass


@bot.message_handler(commands=["removeuser"])
def cmd_removeuser(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ Admin seulement."); return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        bot.reply_to(message, "Usage : /removeuser ID"); return
    uid = int(parts[1])
    users = load_users()
    if uid not in users:
        bot.reply_to(message, "ℹ️ Pas dans la liste."); return
    users.remove(uid); save_users(users)
    bot.reply_to(message, f"🗑️ {uid} retiré.")


@bot.message_handler(commands=["hooks"])
def cmd_hooks(message):
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "⛔ Accès non autorisé."); return
    profile = get_profile(message.from_user.id)
    if not profile:
        bot.reply_to(message, "⚠️ Configure d'abord ton profil avec /profil"); return
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage : /hooks [sujet]\nEx : /hooks Lancer son business en ligne"); return
    bot.reply_to(message, "⏳ Génération des hooks...")
    result = generer_hooks(profile, parts[1])
    if result:
        send_long(message.chat.id, f"🎣 10 ACCROCHES PUBLICITAIRES\n\n{result}", reply_to=message)
    else:
        bot.reply_to(message, "❌ Erreur. Réessaie dans quelques secondes.")


@bot.message_handler(commands=["strategie"])
def cmd_strategie(message):
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "⛔ Accès non autorisé."); return
    profile = get_profile(message.from_user.id)
    if not profile:
        bot.reply_to(message, "⚠️ Configure d'abord ton profil avec /profil"); return
    bot.reply_to(message, "⏳ Création de ta stratégie 90 jours... (30 secondes)")
    result = generer_strategie(profile)
    if result:
        send_long(message.chat.id, f"🗺️ STRATÉGIE CONTENU 90 JOURS\n\n{result}", reply_to=message)
    else:
        bot.reply_to(message, "❌ Erreur. Réessaie dans quelques secondes.")


@bot.message_handler(commands=["tunnel"])
def cmd_tunnel(message):
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "⛔ Accès non autorisé."); return
    profile = get_profile(message.from_user.id)
    if not profile:
        bot.reply_to(message, "⚠️ Configure d'abord ton profil avec /profil"); return
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage : /tunnel [ton offre]\nEx : /tunnel Programme coaching 3 mois à 1500€"); return
    bot.reply_to(message, "⏳ Création de ton tunnel de vente... (30 secondes)")
    result = generer_tunnel(profile, parts[1])
    if result:
        send_long(message.chat.id, f"💰 TUNNEL DE VENTE COMPLET\n\n{result}", reply_to=message)
    else:
        bot.reply_to(message, "❌ Erreur. Réessaie dans quelques secondes.")


@bot.message_handler(commands=["concurrent"])
def cmd_concurrent(message):
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "⛔ Accès non autorisé."); return
    profile = get_profile(message.from_user.id)
    if not profile:
        bot.reply_to(message, "⚠️ Configure d'abord ton profil avec /profil"); return
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage : /concurrent [nom ou description]\nEx : /concurrent @coach_business_marie"); return
    bot.reply_to(message, "⏳ Analyse de la concurrence...")
    result = analyser_concurrence(profile, parts[1])
    if result:
        send_long(message.chat.id, f"🔍 ANALYSE CONCURRENCE\n\n{result}", reply_to=message)
    else:
        bot.reply_to(message, "❌ Erreur. Réessaie dans quelques secondes.")


@bot.message_handler(commands=["compte"])
def cmd_compte(message):
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "⛔ Accès non autorisé."); return
    profile = get_profile(message.from_user.id)
    if not profile:
        bot.reply_to(message, "⚠️ Configure d'abord ton profil avec /profil"); return
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message,
            "Usage : /compte [description de ton compte]\n"
            "Ex : /compte Instagram coaching business, 2500 abonnés, je poste 3x/semaine des conseils entrepreneuriat, taux engagement 2%, pas de ventes"); return
    bot.reply_to(message, "⏳ Analyse de ton compte en cours...")
    result = analyser_compte(profile, parts[1])
    if result:
        send_long(message.chat.id, f"📊 ANALYSE DE TON COMPTE\n\n{result}", reply_to=message)
    else:
        bot.reply_to(message, "❌ Erreur. Réessaie dans quelques secondes.")


@bot.message_handler(func=lambda m: True)
def handle_unknown(message):
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "⛔ Accès non autorisé."); return
    bot.reply_to(message, "❓ Commande inconnue. Envoie /help.")


# ============================================================
#  LANCEMENT
# ============================================================

if __name__ == "__main__":
    print("=" * 50)
    print("  BOT MARKETING DIGITAL DÉMARRÉ")
    print(f"  Admin : {ADMIN_ID}")
    print("=" * 50)
    bot.infinity_polling()
