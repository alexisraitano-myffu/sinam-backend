"""Appeler un modèle candidat, quel que soit son runtime.

Deux dialectes suffisent aujourd'hui :

  * `anthropic:<model>` — la référence (Haiku), via `anthropic_client.get_client()`,
    donc le seam fuel-proxy marche aussi pour un token `syn-fuel-`.
  * `ollama:<model>`    — tout ce qui tourne en local (Qwen, Llama, Gemma…).
  * `mlx:<model>`       — un modèle MLX servi par `mlx_lm.server`, adaptateur
    LoRA compris. C'est par là qu'un modèle ENTRAÎNÉ se note contre le corpus.

Toute réponse est ramenée à la MÊME forme (`Reply`), pour que le scoring ne
sache pas d'où elle vient. C'est la leçon apprise côté core : normaliser au
plus près du réseau, et laisser le reste du code provider-agnostique.

⚠️ Le piège Ollama qui invalide silencieusement une mesure : `num_ctx` vaut
2048 par défaut selon les modèles. Notre prompt classifieur en fait ~4 500 —
Ollama tronque alors le DÉBUT du prompt sans le dire, et le modèle paraît
mauvais alors qu'il n'a jamais reçu les règles. On fixe donc `num_ctx`
explicitement ET on relit `prompt_eval_count` pour vérifier que le modèle a bien
avalé ce qu'on lui a envoyé (`Reply.prompt_tokens`).
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

OLLAMA_URL = "http://localhost:11434/api/chat"
# `mlx_lm.server`, l'endpoint compatible OpenAI qui sert un modèle MLX et son
# adaptateur LoRA. C'est le SEUL moyen de noter un modèle entraîné contre le
# corpus : sans lui, on ne lirait qu'une perte de validation, qui ne dit rien de
# ce que le produit fait.
MLX_URL = os.environ.get("SYNAPSE_MLX_URL", "http://127.0.0.1:8080/v1/chat/completions")
# L'endpoint compatible OpenAI de Gemini, et pas l'API native : la forme de
# `Reply` se remplit alors avec les mêmes champs que partout ailleurs
# (`finish_reason`, `usage.prompt_tokens`), donc un cas mesuré sur Gemini se
# compare à un cas mesuré sur Haiku sans traduction au milieu.
GEMINI_URL = ("https://generativelanguage.googleapis.com/v1beta/openai/"
              "chat/completions")
# Borne la réflexion de Gemini 3.x. Sans elle, un lot de 12 captures à
# étiqueter a rendu 319 jetons visibles sur un budget de 8000 et un
# `finish_reason=length` : tout le reste est parti en raisonnement, qui compte
# dans `max_tokens` sans apparaître dans `completion_tokens`. Mesuré le
# 2026-08-29. "none" éteindrait tout mais 3.6-flash le refuse en HTTP 400, donc
# "low" est le seul réglage qui vaille pour les deux modèles à la fois.
GEMINI_REASONING = "low"
# Assez large pour le classifieur (~4 500 tokens) + la capture + la sortie JSON.
# Volontairement pas énorme : un num_ctx géant réserve du KV-cache pour rien et
# fausse la mesure d'empreinte mémoire (leçon du portage on-device, cf. maxNumTokens 8192→6144).
DEFAULT_NUM_CTX = 8192


@dataclass
class Reply:
    """Réponse normalisée, identique quel que soit le provider."""

    text: str
    #  "stop" (fini) | "max_tokens" (tronqué) | autre chose (anormal)
    stop_reason: str | None
    latency_s: float
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    error: str | None = None
    extra: dict = field(default_factory=dict)

    @property
    def truncated(self) -> bool:
        return self.stop_reason == "max_tokens"

    @property
    def ok(self) -> bool:
        return self.error is None and not self.truncated and bool(self.text.strip())


def parse_spec(spec: str) -> tuple[str, str]:
    """`ollama:qwen2.5:3b` → ('ollama', 'qwen2.5:3b'). Le modèle peut contenir ':'."""
    if ":" not in spec:
        raise ValueError(f"spec de modèle invalide : {spec!r} (attendu 'provider:model')")
    provider, model = spec.split(":", 1)
    if provider not in ("anthropic", "ollama", "gemini", "mlx"):
        raise ValueError(f"provider inconnu : {provider!r}")
    return provider, model


def call(spec: str, system_blocks: list[str], user: str, max_tokens: int,
         num_ctx: int = DEFAULT_NUM_CTX, schema: dict | None = None,
         temperature: float = 0.0) -> Reply:
    """Un appel, un `Reply`. Ne lève jamais : une panne est une donnée de mesure.

    `schema` (JSON Schema) active le décodage contraint quand le runtime le
    supporte. Ollama : passé dans `format`. Anthropic : **ignoré** — l'API n'a pas
    d'équivalent sur `messages.create`, et prétendre le contraire fausserait la
    comparaison. Une mesure contrainte ne se compare donc qu'à une autre mesure
    contrainte du même côté.
    """
    provider, model = parse_spec(spec)
    try:
        if provider == "anthropic":
            return _call_anthropic(model, system_blocks, user, max_tokens, temperature)
        if provider == "gemini":
            return _call_gemini(model, system_blocks, user, max_tokens, schema,
                                temperature)
        if provider == "mlx":
            return _call_mlx(model, system_blocks, user, max_tokens, schema,
                             temperature)
        return _call_ollama(model, system_blocks, user, max_tokens, num_ctx, schema,
                            temperature)
    except Exception as exc:  # noqa: BLE001 — un modèle qui casse EST un résultat
        return Reply(text="", stop_reason=None, latency_s=0.0,
                     error=f"{type(exc).__name__}: {exc}")


def _call_anthropic(model: str, system_blocks: list[str], user: str,
                    max_tokens: int, temperature: float = 0.0) -> Reply:
    from anthropic_client import get_client

    # Le premier bloc porte le cache : c'est ce que fait le core (le classifieur
    # est stable, les blocs vocab/projets bougent). Reproduire la vraie forme,
    # pas une forme simplifiée, sinon on ne mesure pas ce qui tourne en prod.
    blocks = [{"type": "text", "text": system_blocks[0],
               "cache_control": {"type": "ephemeral"}}]
    blocks += [{"type": "text", "text": b} for b in system_blocks[1:]]

    # ⚠️ Sans température explicite, l'API échantillonne au défaut (1.0) et la
    # mesure devient irreproductible. Constaté le 2026-08-20 : sur DEUX passes du
    # même modèle sur le même texte, 2 cas sur 12 divergent, dont une bascule de
    # branche (« Nouveau projet : rénovation » produit une note, puis plus rien).
    # Le harnais fixait déjà 0 côté Ollama : la comparaison Haiku-vs-local était
    # donc faussée, un côté déterministe et l'autre non.
    # NB : le core, LUI, ne fixe pas la température — cette valeur mesure le
    # prompt, pas la variance de production. Passer --temperature 1.0 pour ça.
    t0 = time.time()
    msg = get_client().messages.create(
        model=model, max_tokens=max_tokens, system=blocks, temperature=temperature,
        messages=[{"role": "user", "content": user}],
    )
    text = msg.content[0].text if msg.content else ""
    # ⚠️ `input_tokens` EXCLUT ce qui a été servi par le cache de prompt : quand le
    # cache mord, le prompt bascule dans `cache_read_input_tokens` et
    # `input_tokens` retombe à ~200. Compter la seule valeur brute ferait croire
    # que le modèle n'a pas reçu le prompt — le gate a justement rendu ce faux
    # NO-GO à sa première exécution.
    #
    # ⚠️ Mesuré le 2026-08-25 : sur Haiku 4.5, le cache ne mord PLUS. Il demande un
    # préfixe d'au moins ~4 096 tokens ; le classifieur en un seul appel en faisait
    # ~4 500 et passait, chaque moitié en fait ~3 050 et ne passe pas. Le marqueur
    # ci-dessus est donc posé pour rien depuis le découpage du 2026-08-21. Vérifié
    # dans les deux sens : rallongé au-dessus du seuil, le même prompt écrit puis
    # relit bien 7 775 tokens. Ne pas relire ce commentaire comme la promesse d'un
    # cache actif : c'est la trace de ce qu'il coûte de ne plus l'avoir.
    usage = msg.usage
    prompt_tokens = (usage.input_tokens
                     + (getattr(usage, "cache_read_input_tokens", 0) or 0)
                     + (getattr(usage, "cache_creation_input_tokens", 0) or 0))
    return Reply(
        text=text, stop_reason=msg.stop_reason, latency_s=round(time.time() - t0, 2),
        prompt_tokens=prompt_tokens, output_tokens=usage.output_tokens,
        extra={"uncached_input_tokens": usage.input_tokens,
               # Écrire le cache et le relire ne se paient pas au même
               # prix (1,25× l'entrée contre 0,1×). Les additionner dans
               # `prompt_tokens` était juste pour « le modèle a-t-il reçu
               # le prompt », mais ne permet plus de chiffrer un lot.
               "cache_creation_input_tokens":
                   getattr(usage, "cache_creation_input_tokens", 0) or 0},
    )


def _call_ollama(model: str, system_blocks: list[str], user: str,
                 max_tokens: int, num_ctx: int, schema: dict | None = None,
                 temperature: float = 0.0) -> Reply:
    # Ollama n'a pas de blocs système multiples ni de cache_control : on aplatit
    # avec le même séparateur que le core (\n\n) pour que le TEXTE reçu par le
    # modèle local soit identique à celui reçu par Haiku.
    system = "\n\n".join(system_blocks)
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens,
                    "num_ctx": num_ctx},
    }
    if schema is not None:
        # Décodage contraint : le sampler n'accepte que les continuations valides
        # au regard du schéma. Rend les valeurs hors énumération impossibles.
        payload["format"] = schema
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL, data=body, headers={"content-type": "application/json"})
    t0 = time.time()
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=900).read())
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Ollama injoignable sur {OLLAMA_URL} — lancer `ollama serve` ({exc})"
        ) from exc
    done = resp.get("done_reason")
    return Reply(
        text=resp.get("message", {}).get("content", "") or "",
        # `length` = budget de sortie épuisé : c'est le `max_tokens` d'Anthropic.
        stop_reason="max_tokens" if done == "length" else done,
        latency_s=round(time.time() - t0, 2),
        prompt_tokens=resp.get("prompt_eval_count"),
        output_tokens=resp.get("eval_count"),
        extra={"eval_s": round(resp.get("eval_duration", 0) / 1e9, 2),
               "num_ctx": num_ctx},
    )


def _call_mlx(model: str, system_blocks: list[str], user: str, max_tokens: int,
              schema: dict | None = None, temperature: float = 0.0) -> Reply:
    """Un modèle MLX local, servi par `mlx_lm.server`, adaptateur LoRA compris.

    Mêmes blocs système aplatis avec le MÊME séparateur que partout ailleurs
    (\n\n) : le jour où l'on compare deux providers sur le même cas, la seule
    variable doit être le modèle, jamais la mise en page.

    ⚠ LE PIÈGE QUI REND LA MESURE FAUSSE SANS RIEN DIRE, et il est propre à ce
    provider : un modèle ENTRAÎNÉ sur le prompt court doit être mesuré AVEC le
    prompt court. Le harnais lit ses prompts dans `SYNAPSE_SPLIT_PROMPTS_DIR` ;
    l'oublier lui envoie les 20 000 caractères de production, c'est-à-dire un
    énoncé qu'il n'a jamais vu à l'entraînement, et on conclurait que
    l'entraînement a échoué alors qu'on aurait posé la mauvaise question.

    ⚠ LE NOM DU MODÈLE COMPTE, contrairement à ce qu'on suppose d'un serveur
    lancé avec `--model`. Mesuré le 2026-09-01 : le serveur RÉSOUT le champ
    `model` de la requête, et un nom fantaisiste le fait partir chercher un
    dépôt sur Hugging Face, puis répondre 404 après un aller-retour réseau. Il
    faut donc passer l'identifiant exact du modèle à servir.

    ⚠⚠ ET `--adapter-path` NE SERT À RIEN, en silence. Il a coûté deux mesures
    fausses le 2026-09-01 : un modèle entraîné et le modèle nu ont rendu
    93 sorties identiques au caractère près, ce qui était le seul indice.
    La cause est dans `mlx_lm/server.py` (0.31.3), et c'est un défaut de leur
    code, pas du nôtre :

        model_path   = self._model_map.get(model_path, model_path)
        adapter_path = self._adapter_map.get(model_path, adapter_path)

    L'adaptateur du CLI est rangé sous la clé « default_model », mais la
    recherche se fait APRÈS que `model_path` a été remplacé par le vrai dépôt.
    La clé ne tombe donc jamais, quel que soit le `model` de la requête, et
    aucune ligne de log ni aucun champ de réponse ne le signale.

    LA SEULE FAÇON FIABLE de mesurer un entraînement est donc de FUSIONNER
    l'adaptateur dans un modèle à part entière, et de servir ce dossier :

        python -m mlx_lm fuse --model <base> --adapter-path <adaptateur> \
            --save-path <dossier>
        python -m mlx_lm.server --model <dossier chemin absolu>

    Le nom du modèle dans la baseline devient alors le chemin du dossier, donc
    la mesure dit d'elle-même quels poids ont répondu. (Le champ `adapters`
    dans le corps de la requête marche aussi, mais il laisse la même ambiguïté
    dans la baseline.)

    ⚠ Reste vrai dans tous les cas : rien dans la réponse ne dit quels poids
    ont répondu, et l'empreinte de la baseline certifie le PROMPT, jamais les
    poids. Deux entraînements différents rendent des empreintes IDENTIQUES.
    """
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": "\n\n".join(system_blocks)},
                     {"role": "user", "content": user}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if schema is not None:
        # Le support du décodage contraint varie d'une version de mlx-lm à
        # l'autre. Un refus remonte tel quel dans `error` : c'est une donnée de
        # mesure, pas une panne à rattraper en silence.
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "sortie", "schema": schema, "strict": True},
        }
    req = urllib.request.Request(
        MLX_URL, data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"})
    t0 = time.time()
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=900).read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"mlx_lm.server HTTP {exc.code} : {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"mlx_lm.server injoignable sur {MLX_URL} — le lancer avec "
            f"`python -m mlx_lm.server --model … --adapter-path …` ({exc})"
        ) from exc
    choix = (resp.get("choices") or [{}])[0]
    fin = choix.get("finish_reason")
    usage = resp.get("usage") or {}
    return Reply(
        text=(choix.get("message") or {}).get("content") or "",
        # `length` est l'orthographe OpenAI du `max_tokens` d'Anthropic, que
        # seul connaît le garde de troncature du harnais.
        stop_reason="max_tokens" if fin == "length" else fin,
        latency_s=round(time.time() - t0, 2),
        prompt_tokens=usage.get("prompt_tokens"),
        output_tokens=usage.get("completion_tokens"),
        # Rien n'est mis en cache côté local : tout est payé en calcul, à
        # chaque appel. La clé garde le même nom qu'ailleurs pour que le
        # chiffrage d'un lot ne fasse pas de cas particulier.
        extra={"uncached_input_tokens": usage.get("prompt_tokens")},
    )


def _call_gemini(model: str, system_blocks: list[str], user: str, max_tokens: int,
                 schema: dict | None = None, temperature: float = 0.0) -> Reply:
    """Gemini par son endpoint compatible OpenAI (2026-08-29).

    Pourquoi il existe : ce provider ne sert PAS à mesurer. Il sert à ÉCRIRE le
    corpus, générer les captures et poser les étiquettes. La mesure de parité
    reste sur le modèle de production, sinon elle ne mesure plus le produit.
    Écrire le corpus avec une autre famille de modèle est même le but : un
    corpus dérivé du modèle qu'il évalue graverait les défauts de ce modèle
    dans les poids, là où ils ne se corrigent plus en éditant un fichier.

    Les blocs système sont aplatis avec le MÊME séparateur que côté Ollama et
    que côté core (\n\n). Un jour où l'on comparera deux providers sur le même
    cas, la seule variable devra être le modèle, jamais la mise en page.

    ⚠ PIÈGE MESURÉ LE 2026-08-29, et il ne lève aucune erreur. Gemini 3.x
    réfléchit par défaut, et `max_tokens` plafonne la RÉFLEXION PLUS la sortie
    alors que `completion_tokens` ne compte que la sortie visible. Avec
    max_tokens=64, la même question rend un texte VIDE, zéro jeton de sortie et
    `finish_reason=length` : tout le budget est parti dans le raisonnement. Avec
    2048, elle rend « Bruxelles » en 3 jetons. Donc une réponse vide ici se
    diagnostique en remontant le budget AVANT de soupçonner le prompt, et un
    budget serré ne fait pas économiser, il fait perdre l'appel. `reasoning_effort`
    ("low"/"medium"/"high") borne la réflexion ; la valeur "none" est ACCEPTÉE
    par flash-lite et REFUSÉE en HTTP 400 par 3.6-flash, donc on ne peut pas
    l'éteindre partout.

    ⚠ Le cache de Gemini est IMPLICITE : il n'y a pas de `cache_control` à
    poser, le préfixe se met en cache tout seul quand il se répète. On lit donc
    ce qu'il a mordu dans `usage.prompt_tokens_details.cached_tokens` au lieu de
    le décider. Zéro sur un lot entier ne veut pas dire que le cache est cassé,
    ça veut dire que le préfixe a bougé entre deux appels — c'est le même
    diagnostic qu'ailleurs, à la cause près.
    """
    cle = os.environ.get("GEMINI_API_KEY")
    if not cle:
        raise RuntimeError(
            "GEMINI_API_KEY absente. Elle se pose dans sinam-backend/.env, qui "
            "est ignoré par git — jamais dans un fichier suivi.")
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": "\n\n".join(system_blocks)},
                     {"role": "user", "content": user}],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "reasoning_effort": GEMINI_REASONING,
    }
    if schema is not None:
        # Décodage contraint, même intention que le `format` d'Ollama : les
        # valeurs hors schéma deviennent impossibles au lieu d'être corrigées
        # après coup. Gemini refuse certaines constructions JSON Schema ; un
        # refus est une donnée de mesure, il remonte tel quel dans `error`.
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "sortie", "schema": schema, "strict": True},
        }
    req = urllib.request.Request(
        GEMINI_URL, data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json",
                 "authorization": f"Bearer {cle}"})
    t0 = time.time()
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=900).read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"Gemini HTTP {exc.code} : {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Gemini injoignable ({exc})") from exc
    choix = (resp.get("choices") or [{}])[0]
    fin = choix.get("finish_reason")
    usage = resp.get("usage") or {}
    caches = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
    entree = usage.get("prompt_tokens")
    return Reply(
        text=(choix.get("message") or {}).get("content") or "",
        # `length` est l'orthographe OpenAI du `max_tokens` d'Anthropic. Le
        # garde de troncature du harnais ne connaît que le second.
        stop_reason="max_tokens" if fin == "length" else fin,
        latency_s=round(time.time() - t0, 2),
        prompt_tokens=entree,
        output_tokens=usage.get("completion_tokens"),
        # Même clé que côté Anthropic : ce qui a VRAIMENT été facturé plein
        # tarif. `prompt_tokens` inclut déjà le cache chez Gemini, donc la
        # soustraction est ici, pas dans l'addition.
        extra={"uncached_input_tokens": (entree - caches) if entree else None,
               "cached_tokens": caches},
    )
