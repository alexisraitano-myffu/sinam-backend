"""Où part un appel de modèle : chez Anthropic, ou au modèle local.

Un seul endroit décide, pour que la promesse du mode local tienne d'un bloc :
en local, AUCUN appel ne sort de la machine, et il n'y a pas de repli vers le
cloud. Un repli silencieux serait précisément la fuite que l'utilisateur a
refusée en choisissant le local ; si le modèle ne répond pas, le cycle
s'interrompt et les captures restent en file, comme sans réseau.

Le modèle local est un serveur compatible OpenAI sur la boucle locale (le
moteur que l'app installe à la demande). Le core sait déjà lui parler par son
fournisseur `openai` : le choix se fait ici, pas dans le core.
"""
import os
from dataclasses import dataclass

import config_store
from config import CLAUDE_MODEL

MODE_CLOUD = "cloud"
MODE_LOCAL = "local"

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

    @property
    def is_local(self) -> bool:
        return self.provider == "openai"

    def core_kwargs(self) -> dict:
        """Les arguments nommés communs aux appels LLM du core."""
        return {"base_url": self.base_url, "fuel_token": self.fuel_token,
                "provider": self.provider}


def mode() -> str:
    return config_store.get_llm_mode()


def resolve() -> LlmTarget:
    """La cible du prochain appel. Lève EnvironmentError en cloud sans clé,
    même message qu'avant ce module. En local aucune clé n'est lue : elle
    peut exister (l'utilisateur est passé du cloud au local) sans jamais servir."""
    if mode() == MODE_LOCAL:
        return LlmTarget("openai", LOCAL_MODEL, "", local_base_url(), None)

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
