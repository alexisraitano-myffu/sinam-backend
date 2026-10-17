"""Où part un appel de modèle : chez Anthropic, ou au modèle local.

Un seul endroit décide, pour que la promesse du mode local tienne d'un bloc :
en local, AUCUN appel ne sort de la machine, et il n'y a pas de repli vers le
cloud. Un repli silencieux serait précisément la fuite que l'utilisateur a
refusée en choisissant le local ; si le modèle ne répond pas, le cycle
s'interrompt et les captures restent en file, comme sans réseau.

Le modèle local est un serveur compatible OpenAI sur la boucle locale (le
moteur que l'app installe à la demande). Le core sait déjà lui parler par son
fournisseur `openai` : le choix se fait ici, pas dans le core.

Le troisième mode, « endpoint », est le serveur que l'utilisateur apporte
(freellmapi, Ollama, OpenRouter…). Même fournisseur `openai` que le local,
mais ce n'est PAS le local : rien à démarrer, et l'appel sort de la machine
vers l'adresse que l'utilisateur a choisie. Il n'y a pas non plus de repli
vers Anthropic : quelqu'un qui a branché son serveur ne paie pas Anthropic
dans son dos parce que son serveur dormait.
"""
import os
from dataclasses import dataclass

import config_store
from config import CLAUDE_MODEL

MODE_CLOUD = "cloud"
MODE_LOCAL = "local"
MODE_ENDPOINT = "endpoint"

# Le nom qui désigne, pour le serveur mlx_lm, le modèle qu'il a chargé au
# démarrage. Tout autre nom est pris pour un dépôt Hugging Face à télécharger
# (constaté le 26/09/2026 : 404, et une requête sortante vers huggingface.co).
LOCAL_MODEL = "default_model"


def local_base_url() -> str:
    """Origine du moteur local. La variable d'environnement sert au développement
    (un serveur lancé à la main sur un autre port)."""
    port = os.environ.get("SYNAPSE_LOCAL_LLM_PORT", "8766")
    return f"http://127.0.0.1:{port}"


@dataclass(frozen=True)
class LlmTarget:
    provider: str            # "anthropic" | "openai", tel que le core l'attend
    model: str
    api_key: str
    base_url: str | None
    fuel_token: str | None
    # Le moteur local de cette machine, qu'il faut démarrer pour l'appel. Un
    # serveur apporté par l'utilisateur parle le même dialecte mais n'en est pas un.
    is_local: bool = False

    def core_kwargs(self) -> dict:
        """Les arguments nommés communs aux appels LLM du core."""
        return {"base_url": self.base_url, "fuel_token": self.fuel_token,
                "provider": self.provider}


def mode() -> str:
    return config_store.get_llm_mode()


def uses_anthropic() -> bool:
    """Faux en local ET avec un serveur personnel : aucun client Anthropic,
    donc pas de Batch API, et les fonctions qui n'existent que chez Anthropic
    s'éteignent au lieu de fuir."""
    return mode() == MODE_CLOUD


def ready() -> bool:
    """Le tri peut-il tourner cette nuit ? Ce que l'app demande pour savoir si
    elle doit réclamer quelque chose à l'utilisateur. Une clé Anthropic ne
    compte qu'en cloud : en local ou avec un serveur personnel, la réclamer
    serait le mur qui a bloqué un testeur sur freellmapi."""
    m = mode()
    if m == MODE_LOCAL:
        import moteur_local
        return moteur_local.est_installe()
    if m == MODE_ENDPOINT:
        return config_store.get_llm_endpoint() is not None
    return config_store.has_anthropic_key()


def resolve() -> LlmTarget:
    """La cible du prochain appel. Lève EnvironmentError en cloud sans clé,
    même message qu'avant ce module. En local aucune clé n'est lue : elle
    peut exister (l'utilisateur est passé du cloud au local) sans jamais servir."""
    if mode() == MODE_LOCAL:
        return LlmTarget("openai", LOCAL_MODEL, "", local_base_url(), None, is_local=True)
    if mode() == MODE_ENDPOINT:
        ep = config_store.get_llm_endpoint()
        if ep is None:
            raise EnvironmentError(
                "serveur personnel incomplet : il manque l'adresse ou le nom du "
                "modèle (Réglages → Qui fait le tri)."
            )
        return LlmTarget("openai", ep["model"], ep["api_key"], ep["base_url"], None)

    from anthropic_client import _fuel_base_url, is_fuel_token

    key = config_store.get_anthropic_key()
    if not key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY manquante : exporte-la, mets-la dans .env, ou "
            "règle-la depuis l'app (Réglages → Clé Anthropic API)."
        )
    if is_fuel_token(key):
        return LlmTarget("anthropic", CLAUDE_MODEL, "", _fuel_base_url(), key)
    return LlmTarget("anthropic", CLAUDE_MODEL, key, None, None)
