import telebot
import requests
import json
import import telebot
import requests
import json
import os
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

# ============================================================
#  CONFIGURATION
# ============================================================
BOT_TOKEN    = os.environ.get("ECOM_BOT_TOKEN")
ADMIN_ID     = int(os.environ.get("ADMIN_ID", "0"))
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

if not BOT_TOKEN:
    raise ValueError("❌ Variable ECOM_BOT_TOKEN manquante !")
if not GROQ_API_KEY:
    raise ValueError("❌ Variable GROQ_API_KEY manquante !")

bot = telebot.TeleBot(BOT_TOKEN)

USERS_FILE   = "ecom_users.json"
PROFILE_FILE = "ecom_profiles.json"

# ============================================================
#  GESTION UTILISATEURS
# ============================================================

def load_users():
    if not os.path.exists(USERS_FILE):
        save_users([])
    with open(USERS_FILE, "r") as f:
        return json.load(f).get("allowed", [])

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump({"allowed": users}, f, indent=2)

def is_admin(uid):      return uid == ADMIN_ID
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
#  APPEL GROQ API
# ============================================================

def ask_groq(prompt, system=None):
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type":  "application/json"
            },
            json={
                "model":       "llama-3.3-70b-versatile",
                "messages":    messages,
                "max_tokens":  2000,
                "temperature": 0.8,
            },
            timeout=40
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Erreur Groq : {e}")
        return None

def get_system(profile):
    niche  = profile.get("niche", "e-commerce généraliste")
    cible  = profile.get("cible", "acheteurs en ligne 18-45 ans")
    pays   = profile.get("pays", "France")
    budget = profile.get("budget_ads", "500€/mois")
    return (
        f"Tu es un expert e-commerce spécialisé en dropshipping et Shopify. "
        f"Niche du store : {niche}. Cible : {cible}. Marché : {pays}. Budget ads : {budget}. "
        f"Plateformes : TikTok Ads et Facebook/Instagram Ads. "
        f"RÈGLES DE FORMATAGE STRICTES :\n"
        f"- Pour mettre en gras : utilise *texte* (un seul astérisque de chaque côté)\n"
        f"- NE JAMAIS utiliser ** (double astérisque)\n"
        f"- NE JAMAIS utiliser === ou --- comme séparateur\n"
        f"- Utilise des emojis au début de chaque section principale\n"
        f"- Saute une ligne entre chaque section\n"
        f"- Utilise • pour les listes\n"
        f"- Toujours en français, ultra concret et chiffré."
    )

def nettoyer(text):
    import re
    # Supprimer les séparateurs ===== et -----
    text = re.sub(r'={3,}', '', text)
    text = re.sub(r'-{3,}', '', text)
    # Convertir **texte** en *texte* pour Telegram
    text = re.sub(r'\*\*(.*?)\*\*', r'*\1*', text)
    # Supprimer les # markdown
    text = re.sub(r'^#{1,4}\s+', '', text, flags=re.MULTILINE)
    # Convertir - en bullet
    text = re.sub(r'^\s*[-–]\s', '• ', text, flags=re.MULTILINE)
    # Supprimer les lignes vides multiples
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def scraper_produit(url):
    """Récupère les infos du produit depuis le lien"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()

        # Extraire le titre depuis la balise <title>
        import re
        title_match = re.search(r'<title[^>]*>(.*?)</title>', r.text, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else "Produit"

        # Extraire les méta descriptions
        desc_match = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\'](.*?)["\']', r.text, re.IGNORECASE)
        description = desc_match.group(1).strip() if desc_match else ""

        # Extraire le prix si disponible
        price_match = re.search(r'"price"[:\s]+"?([\d.,]+)"?', r.text)
        price = price_match.group(1) if price_match else "Non trouvé"

        return {
            "titre": title[:200],
            "description": description[:500],
            "prix_fournisseur": price,
            "url": url
        }
    except Exception as e:
        print(f"Erreur scraping : {e}")
        return None

def generer_fiche_depuis_lien(profile, infos_produit):
    sys = get_system(profile)
    prompt = (
        f"Génère une fiche produit Shopify complète basée sur ces infos fournisseur :\n\n"
        f"Titre fournisseur : {infos_produit['titre']}\n"
        f"Description fournisseur : {infos_produit['description']}\n"
        f"Prix fournisseur : {infos_produit['prix_fournisseur']}\n"
        f"Source : {infos_produit['url']}\n\n"
        f"Génère une fiche produit optimisée pour Shopify :\n\n"
        f"*📦 NOM DU PRODUIT*\n"
        f"[Titre accrocheur et optimisé SEO]\n\n"
        f"*💰 STRATÉGIE PRIX*\n"
        f"• Prix fournisseur : [prix]\n"
        f"• Prix de vente recommandé : [prix]\n"
        f"• Marge estimée : [%]\n\n"
        f"*✍️ DESCRIPTION COURTE*\n"
        f"[2-3 phrases percutantes pour la page produit]\n\n"
        f"*📝 DESCRIPTION LONGUE*\n"
        f"[Description complète avec hook, bénéfices et CTA]\n\n"
        f"*⭐ BULLET POINTS*\n"
        f"• [5 arguments de vente courts]\n\n"
        f"*🔍 META DESCRIPTION SEO*\n"
        f"[155 caractères max]\n\n"
        f"*🏷️ TAGS SHOPIFY*\n"
        f"[10 tags pertinents]\n\n"
        f"*📢 ANGLE PUBLICITAIRE*\n"
        f"• Hook TikTok : [accroche vidéo]\n"
        f"• Accroche Meta : [texte pub]\n"
        f"• Cible recommandée : [audience]\n\n"
        f"*⚠️ POINTS D'ATTENTION*\n"
        f"• [Risques potentiels, concurrence, saisonnalité]"
    )
    return ask_groq(prompt, sys)
    sys = get_system(profile)
    prompt = (
        f"Trouve 7 produits à haute tendance pour du dropshipping en ce moment"
        + (f" dans la catégorie : {categorie}" if categorie else "")
        + f" pour le marché {profile.get('pays','France')}.\n\n"
        f"Pour chaque produit utilise ce format EXACT :\n\n"
        f"*🔥 [NUMÉRO]. [NOM DU PRODUIT]*\n\n"
        f"• Tendance : [pourquoi c'est tendance]\n"
        f"• Achat : [prix fournisseur]\n"
        f"• Vente : [prix recommandé]\n"
        f"• Marge : [marge brute %]\n"
        f"• TikTok Ads : [score/10]\n"
        f"• Meta Ads : [score/10]\n\n"
        f"• 🔗 Fournisseurs :\n"
        f"  1. AliExpress : https://fr.aliexpress.com/wholesale?SearchText=[mots-clés-produit]\n"
        f"  2. Alibaba : https://www.alibaba.com/trade/search?SearchText=[mots-clés-produit]\n"
        f"  3. CJ Dropshipping : https://cjdropshipping.com/list.html?searchKey=[mots-clés-produit]\n\n"
        f"Remplace [mots-clés-produit] par les vrais mots-clés du produit en anglais dans les URLs. "
        f"Sépare chaque produit par une ligne vide. Classe du plus au moins prometteur."
    )
    return ask_groq(prompt, sys)

def generer_fiche(profile, produit):
    sys = get_system(profile)
    prompt = (
        f"Génère une fiche produit Shopify complète et optimisée pour : '{produit}'.\n\n"
        f"Inclus :\n"
        f"*TITRE SEO* : titre accrocheur + mots-clés (max 70 caractères)\n\n"
        f"*DESCRIPTION COURTE* : 2-3 phrases percutantes pour la page produit\n\n"
        f"*DESCRIPTION LONGUE* : description complète HTML-ready avec :\n"
        f"  - Hook émotionnel d'ouverture\n"
        f"  - 5 bénéfices clés (pas des caractéristiques)\n"
        f"  - Preuves sociales suggérées\n"
        f"  - CTA fort de fermeture\n\n"
        f"*BULLET POINTS* : 5 arguments de vente courts\n\n"
        f"*MÉTA DESCRIPTION* : 155 caractères pour le SEO\n\n"
        f"*TAGS SHOPIFY* : 10 tags pertinents\n\n"
        f"*PRIX SUGGÉRÉ* : stratégie de prix psychologique"
    )
    return ask_groq(prompt, sys)

def generer_ads(profile, produit):
    sys = get_system(profile)
    prompt = (
        f"Crée des textes publicitaires complets pour '{produit}'.\n\n"
        f"*TIKTOK ADS*\n"
        f"• Hook vidéo (0-3s) : 3 variantes qui arrêtent le scroll\n"
        f"• Script vidéo 15s : texte complet à dire/afficher\n"
        f"• Script vidéo 30s : texte complet storytelling\n"
        f"• Caption TikTok : texte + hashtags\n\n"
        f"*FACEBOOK/INSTAGRAM ADS*\n"
        f"• Accroche principale : 3 variantes (max 40 caractères)\n"
        f"• Texte principal : 3 variantes (court/moyen/long)\n"
        f"• Description : 2 variantes\n"
        f"• CTA recommandé\n\n"
        f"*EMAIL MARKETING*\n"
        f"• Objet email : 3 variantes A/B\n"
        f"• Email de lancement (300 mots)\n\n"
        f"Adapte le ton pour la cible {profile.get('cible','acheteurs en ligne')}."
    )
    return ask_groq(prompt, sys)

def generer_page_vente(profile, produit):
    sys = get_system(profile)
    prompt = (
        f"Crée une page de vente Shopify complète et haute conversion pour : '{produit}'.\n\n"
        f"Structure :\n\n"
        f"*HERO SECTION*\n"
        f"• Titre principal (H1) accrocheur\n"
        f"• Sous-titre bénéfice\n"
        f"• CTA bouton\n\n"
        f"*PROBLÈME & SOLUTION*\n"
        f"• Le problème que ressent le client\n"
        f"• Comment ce produit le résout\n\n"
        f"*BÉNÉFICES CLÉS* (5 bénéfices avec icônes suggérées)\n\n"
        f"*PREUVES SOCIALES*\n"
        f"• 3 avis clients fictifs réalistes à adapter\n"
        f"• Chiffres clés à afficher\n\n"
        f"*FAQ* : 5 questions/réponses fréquentes\n\n"
        f"*OFFRE & URGENCE*\n"
        f"• Formulation de l'offre\n"
        f"• Éléments d'urgence/rareté\n"
        f"• Garantie suggérée\n\n"
        f"*CTA FINAL* : texte du bouton + phrase d'appui"
    )
    return ask_groq(prompt, sys)

def generer_offre_flash(profile, produit):
    sys = get_system(profile)
    prompt = (
        f"Crée une offre flash complète pour '{produit}'.\n\n"
        f"*STRATÉGIE DE L'OFFRE*\n"
        f"• Type d'offre recommandé (réduction %, bundle, cadeau...)\n"
        f"• Durée optimale\n"
        f"• Prix avant/après\n\n"
        f"*TEXTES PROMO*\n"
        f"• Titre de l'offre flash (court et percutant)\n"
        f"• Bannière site web (texte)\n"
        f"• Pop-up de sortie (texte)\n"
        f"• Email d'annonce (objet + corps)\n"
        f"• SMS/WhatsApp (160 caractères)\n\n"
        f"*POSTS RÉSEAUX SOCIAUX*\n"
        f"• Post Instagram/Facebook\n"
        f"• Story Instagram\n"
        f"• TikTok caption\n\n"
        f"*COMPTE À REBOURS* : phrase d'urgence à afficher sur le site"
    )
    return ask_groq(prompt, sys)

def analyser_concurrent(profile, concurrent):
    sys = get_system(profile)
    prompt = (
        f"Analyse ce concurrent e-commerce : '{concurrent}'.\n\n"
        f"*1. FORCES*\n"
        f"• Ce qu'il fait bien (produits, prix, marketing, UX)\n\n"
        f"*2. FAIBLESSES*\n"
        f"• Ce qu'il ne couvre pas ou mal\n\n"
        f"*3. STRATÉGIE ADS*\n"
        f"• Comment il probable ment fait ses pubs TikTok/Meta\n"
        f"• Angles créatifs qu'il utilise\n\n"
        f"*4. OPPORTUNITÉS*\n"
        f"• Comment le surpasser concrètement\n"
        f"• Produits complémentaires qu'il ne vend pas\n\n"
        f"*5. PLAN D'ACTION*\n"
        f"• 5 actions concrètes pour voler ses clients\n"
        f"• Angle de différenciation principal"
    )
    return ask_groq(prompt, sys)

def analyser_store(profile, description):
    sys = get_system(profile)
    prompt = (
        f"Analyse ce store Shopify et donne un audit complet :\n\n"
        f"Description : {description}\n\n"
        f"*1. AUDIT CONVERSION*\n"
        f"• Points qui freinent les ventes\n"
        f"• Taux de conversion estimé et objectif\n\n"
        f"*2. AUDIT PRODUITS*\n"
        f"• Sélection de produits (pertinence, prix, marges)\n\n"
        f"*3. AUDIT MARKETING*\n"
        f"• Stratégie ads actuelle vs optimale\n"
        f"• Canaux sous-exploités\n\n"
        f"*4. AUDIT TECHNIQUE*\n"
        f"• Vitesse, mobile, SEO\n"
        f"• Apps Shopify recommandées\n\n"
        f"*5. PLAN D'ACTION PRIORITAIRE*\n"
        f"• Top 5 actions à faire cette semaine\n"
        f"• Top 5 actions à faire ce mois\n"
        f"• Objectif CA à 90 jours réaliste"
    )
    return ask_groq(prompt, sys)

def strategie_lancement(profile, produit):
    sys = get_system(profile)
    prompt = (
        f"Crée une stratégie de lancement complète pour '{produit}' sur Shopify.\n\n"
        f"*PHASE 1 — PRÉPARATION (Semaine 1-2)*\n"
        f"• Validation du produit (méthode)\n"
        f"• Setup store Shopify (checklist)\n"
        f"• Création des visuels (brief créatif)\n\n"
        f"*PHASE 2 — TEST (Semaine 3-4)*\n"
        f"• Budget test recommandé\n"
        f"• Structure campagne TikTok Ads\n"
        f"• Structure campagne Meta Ads\n"
        f"• KPIs à surveiller (CPA cible, ROAS minimum)\n\n"
        f"*PHASE 3 — SCALE (Mois 2)*\n"
        f"• Critères pour passer au scale\n"
        f"• Comment augmenter le budget\n"
        f"• Nouveaux angles créatifs\n\n"
        f"*PHASE 4 — OPTIMISATION (Mois 3)*\n"
        f"• Upsell/cross-sell à ajouter\n"
        f"• Email flows à mettre en place\n"
        f"• Stratégie de rétention\n\n"
        f"*BUDGET TOTAL ESTIMÉ* et *CA PROJETÉ* par phase"
    )
    return ask_groq(prompt, sys)

def plan_contenu(profile, produit=None):
    sys = get_system(profile)
    mois = datetime.now().strftime("%B %Y")
    prompt = (
        f"Crée un plan de contenu e-commerce complet pour {mois}"
        + (f" autour du produit : '{produit}'" if produit else "")
        + f" pour {profile.get('niche','e-commerce')}.\n\n"
        f"*RÉPARTITION HEBDOMADAIRE*\n"
        f"• Lundi : type de contenu + sujet\n"
        f"• Mardi : type de contenu + sujet\n"
        f"• Mercredi : type de contenu + sujet\n"
        f"• Jeudi : type de contenu + sujet\n"
        f"• Vendredi : type de contenu + sujet\n"
        f"• Weekend : type de contenu + sujet\n\n"
        f"*CALENDRIER 30 JOURS*\n"
        f"Pour chaque semaine : thème principal, 5 idées de posts, 2 idées de vidéos TikTok\n\n"
        f"*CONTENUS EVERGREEN* : 5 idées de contenus qui fonctionnent toujours\n\n"
        f"*ÉVÉNEMENTS DU MOIS* : dates importantes à exploiter (promos, fêtes...)"
    )
    return ask_groq(prompt, sys)


# ============================================================
#  UTILITAIRES
# ============================================================

def nettoyer(text):
    import re
    text = re.sub(r'\*\*(.*?)\*\*', r'*\1*', text)
    text = re.sub(r'^#{1,4}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\- ', '• ', text, flags=re.MULTILINE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def send_long(chat_id, text, reply_to=None):
    text = nettoyer(text)
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
            try:
                if i == 0 and reply_to:
                    bot.reply_to(reply_to, chunk)
                else:
                    bot.send_message(chat_id, chunk)
            except Exception as e:
                print(f"Erreur envoi: {e}")


# ============================================================
#  COMMANDES TELEGRAM
# ============================================================

@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "⛔ Accès non autorisé."); return
    profile = get_profile(message.from_user.id)
    configured = "✅ Configuré" if profile else "⚠️ Non configuré — fais /profil"
    bot.reply_to(message,
        "🛒 Bot E-Commerce\n\n"
        f"Profil : {configured}\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "⚙️ CONFIGURATION\n"
        "/profil — Configurer ton store\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🔥 PRODUITS\n"
        "/tendances — Produits tendance à vendre\n"
        "/tendances [catégorie] — Par catégorie\n"
        "/analyse [lien] — Fiche depuis lien AliExpress/Alibaba\n"
        "/fiche [produit] — Fiche produit complète\n"
        "/page [produit] — Page de vente Shopify\n"
        "/flash [produit] — Offre flash complète\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📢 PUBLICITÉ\n"
        "/ads [produit] — Textes TikTok + Meta Ads\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📊 STRATÉGIE\n"
        "/lancement [produit] — Stratégie lancement\n"
        "/contenu — Plan de contenu 30 jours\n"
        "/contenu [produit] — Plan autour d'un produit\n"
        "/concurrent [nom] — Analyse concurrence\n"
        "/store [description] — Audit de ton store\n"
    )


@bot.message_handler(commands=["profil"])
def cmd_profil(message):
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "⛔ Accès non autorisé."); return
    profile = get_profile(message.from_user.id)
    profil_actuel = (
        f"Profil actuel :\n"
        f"• Niche : {profile.get('niche','Non défini')}\n"
        f"• Cible : {profile.get('cible','Non défini')}\n"
        f"• Pays : {profile.get('pays','Non défini')}\n"
        f"• Budget ads : {profile.get('budget_ads','Non défini')}"
        if profile else "⚠️ Aucun profil configuré"
    )
    bot.reply_to(message,
        "⚙️ Configuration de ton store\n\n"
        "/setniche [ta niche]\n"
        "Ex : /setniche Accessoires fitness et bien-être\n\n"
        "/setcible [ta cible]\n"
        "Ex : /setcible Femmes 25-40 ans sportives\n\n"
        "/setpays [ton marché]\n"
        "Ex : /setpays France\n\n"
        "/setbudget [budget ads/mois]\n"
        "Ex : /setbudget 500€/mois\n\n"
        + profil_actuel
    )


@bot.message_handler(commands=["setniche"])
def cmd_setniche(message):
    if not is_authorized(message.from_user.id): return
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage : /setniche [ta niche]"); return
    profile = get_profile(message.from_user.id)
    profile["niche"] = parts[1]
    save_profile(message.from_user.id, profile)
    bot.reply_to(message, f"✅ Niche : {parts[1]}")

@bot.message_handler(commands=["setcible"])
def cmd_setcible(message):
    if not is_authorized(message.from_user.id): return
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage : /setcible [ta cible]"); return
    profile = get_profile(message.from_user.id)
    profile["cible"] = parts[1]
    save_profile(message.from_user.id, profile)
    bot.reply_to(message, f"✅ Cible : {parts[1]}")

@bot.message_handler(commands=["setpays"])
def cmd_setpays(message):
    if not is_authorized(message.from_user.id): return
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage : /setpays [pays]"); return
    profile = get_profile(message.from_user.id)
    profile["pays"] = parts[1]
    save_profile(message.from_user.id, profile)
    bot.reply_to(message, f"✅ Pays : {parts[1]}")

@bot.message_handler(commands=["setbudget"])
def cmd_setbudget(message):
    if not is_authorized(message.from_user.id): return
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage : /setbudget [budget]"); return
    profile = get_profile(message.from_user.id)
    profile["budget_ads"] = parts[1]
    save_profile(message.from_user.id, profile)
    bot.reply_to(message, f"✅ Budget ads : {parts[1]}")


@bot.message_handler(commands=["tendances"])
def cmd_tendances(message):
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "⛔ Accès non autorisé."); return
    profile = get_profile(message.from_user.id)
    if not profile:
        bot.reply_to(message, "⚠️ Configure ton profil avec /profil"); return
    parts = message.text.split(" ", 1)
    cat = parts[1] if len(parts) > 1 else None
    bot.reply_to(message, "⏳ Recherche des produits tendance...")
    result = trouver_tendances(profile, cat)
    if result:
        send_long(message.chat.id, f"🔥 PRODUITS TENDANCE\n\n{result}", reply_to=message)
    else:
        bot.reply_to(message, "❌ Erreur. Réessaie.")


@bot.message_handler(commands=["fiche"])
def cmd_fiche(message):
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "⛔ Accès non autorisé."); return
    profile = get_profile(message.from_user.id)
    if not profile:
        bot.reply_to(message, "⚠️ Configure ton profil avec /profil"); return
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage : /fiche [produit]\nEx : /fiche Ceinture de massage électrique"); return
    bot.reply_to(message, "⏳ Génération de la fiche produit...")
    result = generer_fiche(profile, parts[1])
    if result:
        send_long(message.chat.id, f"📦 FICHE PRODUIT\n\n{result}", reply_to=message)
    else:
        bot.reply_to(message, "❌ Erreur. Réessaie.")


@bot.message_handler(commands=["ads"])
def cmd_ads(message):
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "⛔ Accès non autorisé."); return
    profile = get_profile(message.from_user.id)
    if not profile:
        bot.reply_to(message, "⚠️ Configure ton profil avec /profil"); return
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage : /ads [produit]\nEx : /ads Lampe LED gaming"); return
    bot.reply_to(message, "⏳ Création des textes publicitaires...")
    result = generer_ads(profile, parts[1])
    if result:
        send_long(message.chat.id, f"📢 TEXTES PUBLICITAIRES\n\n{result}", reply_to=message)
    else:
        bot.reply_to(message, "❌ Erreur. Réessaie.")


@bot.message_handler(commands=["page"])
def cmd_page(message):
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "⛔ Accès non autorisé."); return
    profile = get_profile(message.from_user.id)
    if not profile:
        bot.reply_to(message, "⚠️ Configure ton profil avec /profil"); return
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage : /page [produit]\nEx : /page Montre connectée sport"); return
    bot.reply_to(message, "⏳ Création de la page de vente... (30 secondes)")
    result = generer_page_vente(profile, parts[1])
    if result:
        send_long(message.chat.id, f"🛍️ PAGE DE VENTE SHOPIFY\n\n{result}", reply_to=message)
    else:
        bot.reply_to(message, "❌ Erreur. Réessaie.")


@bot.message_handler(commands=["flash"])
def cmd_flash(message):
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "⛔ Accès non autorisé."); return
    profile = get_profile(message.from_user.id)
    if not profile:
        bot.reply_to(message, "⚠️ Configure ton profil avec /profil"); return
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage : /flash [produit]\nEx : /flash Écouteurs sans fil"); return
    bot.reply_to(message, "⏳ Création de l'offre flash...")
    result = generer_offre_flash(profile, parts[1])
    if result:
        send_long(message.chat.id, f"⚡ OFFRE FLASH\n\n{result}", reply_to=message)
    else:
        bot.reply_to(message, "❌ Erreur. Réessaie.")


@bot.message_handler(commands=["concurrent"])
def cmd_concurrent(message):
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "⛔ Accès non autorisé."); return
    profile = get_profile(message.from_user.id)
    if not profile:
        bot.reply_to(message, "⚠️ Configure ton profil avec /profil"); return
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage : /concurrent [nom du site]\nEx : /concurrent gymshark.com"); return
    bot.reply_to(message, "⏳ Analyse de la concurrence...")
    result = analyser_concurrent(profile, parts[1])
    if result:
        send_long(message.chat.id, f"🔍 ANALYSE CONCURRENCE\n\n{result}", reply_to=message)
    else:
        bot.reply_to(message, "❌ Erreur. Réessaie.")


@bot.message_handler(commands=["store"])
def cmd_store(message):
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "⛔ Accès non autorisé."); return
    profile = get_profile(message.from_user.id)
    if not profile:
        bot.reply_to(message, "⚠️ Configure ton profil avec /profil"); return
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message,
            "Usage : /store [description de ton store]\n"
            "Ex : /store Shopify mode femme, 50 produits, 300 visites/jour, 1% conversion, dépense 300€/mois Meta Ads, CA 800€/mois"); return
    bot.reply_to(message, "⏳ Audit de ton store en cours...")
    result = analyser_store(profile, parts[1])
    if result:
        send_long(message.chat.id, f"📊 AUDIT DE TON STORE\n\n{result}", reply_to=message)
    else:
        bot.reply_to(message, "❌ Erreur. Réessaie.")


@bot.message_handler(commands=["lancement"])
def cmd_lancement(message):
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "⛔ Accès non autorisé."); return
    profile = get_profile(message.from_user.id)
    if not profile:
        bot.reply_to(message, "⚠️ Configure ton profil avec /profil"); return
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage : /lancement [produit]\nEx : /lancement Tapis de yoga antidérapant"); return
    bot.reply_to(message, "⏳ Création de la stratégie de lancement... (30 secondes)")
    result = strategie_lancement(profile, parts[1])
    if result:
        send_long(message.chat.id, f"🚀 STRATÉGIE DE LANCEMENT\n\n{result}", reply_to=message)
    else:
        bot.reply_to(message, "❌ Erreur. Réessaie.")


@bot.message_handler(commands=["contenu"])
def cmd_contenu(message):
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "⛔ Accès non autorisé."); return
    profile = get_profile(message.from_user.id)
    if not profile:
        bot.reply_to(message, "⚠️ Configure ton profil avec /profil"); return
    parts = message.text.split(" ", 1)
    produit = parts[1] if len(parts) > 1 else None
    bot.reply_to(message, "⏳ Création du plan de contenu... (30 secondes)")
    result = plan_contenu(profile, produit)
    if result:
        send_long(message.chat.id, f"📅 PLAN DE CONTENU 30 JOURS\n\n{result}", reply_to=message)
    else:
        bot.reply_to(message, "❌ Erreur. Réessaie.")


@bot.message_handler(commands=["analyse"])
def cmd_analyse(message):
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "⛔ Accès non autorisé."); return
    profile = get_profile(message.from_user.id)
    if not profile:
        bot.reply_to(message, "⚠️ Configure ton profil avec /profil"); return
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message,
            "Usage : /analyse [lien produit]\n\n"
            "Ex : /analyse https://fr.aliexpress.com/item/...\n"
            "Ex : /analyse https://www.alibaba.com/product-detail/..."); return

    url = parts[1].strip()
    if not url.startswith("http"):
        bot.reply_to(message, "❌ Lien invalide. Commence par https://"); return

    bot.reply_to(message, "⏳ Récupération du produit en cours...")
    infos = scraper_produit(url)

    if not infos or not infos.get("titre"):
        bot.reply_to(message,
            "❌ Impossible de récupérer les infos du produit.\n\n"
            "AliExpress bloque parfois les robots. Essayez :\n"
            "• Copier le nom du produit et utiliser /fiche [nom produit]"); return

    bot.send_message(message.chat.id, f"✅ Produit trouvé : {infos['titre'][:100]}\n\n⏳ Génération de la fiche...")
    result = generer_fiche_depuis_lien(profile, infos)
    if result:
        send_long(message.chat.id, f"📦 FICHE PRODUIT SHOPIFY\n\n{result}", reply_to=message)
    else:
        bot.reply_to(message, "❌ Erreur. Réessaie.")
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


@bot.message_handler(commands=["myid"])
def cmd_myid(message):
    bot.reply_to(message, f"Ton ID : {message.from_user.id}")


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
    print("  BOT E-COMMERCE DÉMARRÉ")
    print(f"  Admin : {ADMIN_ID}")
    print("=" * 50)
    bot.infinity_polling()
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
