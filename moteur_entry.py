"""Point d'entrée du moteur local : le serveur mlx_lm, réglé comme la mesure.

Empaqueté à part du backend (`sinam-moteur.spec`) et téléchargé seulement par
qui choisit le tri local : ~200 Mo de runtime que les autres n'ont pas à porter.
Le backend le lance au début d'un cycle et l'arrête à la fin, pour ne pas garder
~3 Go de modèle en mémoire le reste du temps.

Les réglages qui changent les réponses sont FIGÉS ici et non passés par
l'appelant : ce sont ceux de `scripts/entrainement/pod/mesurer_mlx.py`, qui a
produit le chiffre sur lequel on a décidé. Un serveur qui répondrait avec la
réflexion ouverte, ou une autre température, servirait un autre modèle que
celui qu'on a mesuré, sans rien casser de visible.

    sinam-moteur --model <dossier des poids> --adapter-path <dossier> --port 8766

Les requêtes doivent nommer le modèle `default_model` : tout autre nom est pris
par le serveur pour un dépôt Hugging Face à télécharger.
"""
import json
import os
import sys

# Réflexion coupée : le prompt se termine par un bloc de réflexion vide, comme
# à l'entraînement et à la mesure. Température 0 : même réponse à même question.
REGLAGES_FIGES = [
    "--host", "127.0.0.1",
    "--chat-template-args", json.dumps({"enable_thinking": False}),
    "--temp", "0.0",
    # Le cache de préfixes garde par défaut 10 conversations : 2,25 Go mesurés
    # le 26/09/2026 au-dessus des 2,9 Go de poids, et une panne mémoire Metal
    # sur un Mac 8 Go en plein cycle. Deux entrées suffisent, ce sont les deux
    # longs prompts système (moitié note, moitié graphe) qui valent d'être
    # gardés d'un appel à l'autre.
    "--prompt-cache-size", "2",
    "--prompt-cache-bytes", "512MB",
]


def _adaptateur_toujours_charge(server) -> None:
    """mlx_lm 0.31.3 IGNORE `--adapter-path`, sans erreur.

    `ModelProvider.load` remplace `default_model` par le chemin des poids AVANT
    de chercher l'adaptateur par défaut, qui est rangé sous `default_model` : la
    recherche échoue et le modèle se charge nu. Constaté le 26/09/2026 : le
    serveur rendait au caractère près la réponse du modèle NON entraîné, alors
    que la mesure (91,9 % contre 87,2 %) portait sur l'entraîné. Rien n'aurait
    planté ; on aurait livré le modèle qu'on avait écarté.

    Deux corrections : l'adaptateur par défaut est réinjecté avant la
    résolution, et le chargement REFUSE de rendre la main si les couches LoRA
    ne sont pas dans le modèle chargé. La seconde attrape aussi toute
    régression future de la première."""
    from mlx.utils import tree_flatten

    charger = server.ModelProvider.load
    charger_brut = server.ModelProvider._load

    def load(self, model_path, adapter_path=None, draft_model_path=None):
        if model_path == "default_model" and adapter_path is None:
            adapter_path = self.cli_args.adapter_path
        return charger(self, model_path, adapter_path, draft_model_path)

    def _load(self, model_path, adapter_path=None, draft_model_path=None):
        charger_brut(self, model_path, adapter_path, draft_model_path)
        if adapter_path is not None:
            lora = [k for k, _ in tree_flatten(self.model.parameters()) if "lora_a" in k]
            if not lora:
                raise SystemExit(f"adaptateur {adapter_path} demandé mais absent du "
                                 "modèle chargé : refus de servir le modèle nu")

    server.ModelProvider.load = load
    server.ModelProvider._load = _load


def main() -> None:
    # Le moteur ne parle à personne : sans ceci, un nom de modèle inattendu
    # déclenche une requête vers huggingface.co.
    os.environ["HF_HUB_OFFLINE"] = "1"
    from mlx_lm import server

    _adaptateur_toujours_charge(server)
    sys.argv = [sys.argv[0], *sys.argv[1:], *REGLAGES_FIGES]
    server.main()


if __name__ == "__main__":
    main()
