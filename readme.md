# Wirecord 3.1

Wirecord archive le trafic Discord reçu par mitmproxy et transfère les messages des salons configurés. La capture brute conserve le format compatible avec les exporteurs JSON et HTML du projet.

La version 3.1 ajoute une file SQLite persistante, le rattrapage automatique des salons surveillés, les encarts en mode webhook, la supervision de Discord/Gateway et les sauvegardes vérifiées.

## Installation

Python 3.10 minimum ; la production est validée sous Linux avec Python 3.13. Le client Discord et Xvfb sont nécessaires sur le VPS.

```bash
python3 -m venv venv
venv/bin/python -m pip install -e '.[dev]'
cp config.example.json config.json
venv/bin/python -m discordless check-config
```

Renseigner les identifiants réels et les destinations explicites. Les transferts natifs et les récupérations utilisent exclusivement Jarl Panda. Le token est lu dans le stockage du client local ou fourni dans la configuration privée ; il n'est jamais affiché.

## Exploitation

```bash
venv/bin/python -m discordless status
venv/bin/python -m discordless status --json
venv/bin/python -m discordless recover
venv/bin/python -m discordless deliveries --status uncertain
venv/bin/python -m discordless backup
```

`recover` est une simulation sans mutation par défaut. `--execute` archive puis alimente la file persistante ; seul le runtime de production envoie. `--bootstrap --execute` initialise une règle en comparant les messages sources aux preuves de transfert et aux destinations. Les envois sont désactivés par défaut jusqu'à cette initialisation.

Les erreurs et envois incertains restent visibles et retiennent les messages suivants de la destination. Un message confirmé envoyé n'est pas renvoyé. Les mises à jour utilisent une notification liée au transfert d'origine en mode webhook ; les transferts natifs conservent leur instantané.

Voir [le guide d'exploitation](docs/operations.md) pour la configuration, les commandes de résolution, les sauvegardes et le retour arrière. Les anciens scripts de republication sont désactivés et leurs sources conservées en fichiers `.legacy`.

## Architecture

Capture REST/Gateway → archive brute + journal SQLite → travailleur de livraison → Discord.

La récupération périodique utilise la même archive et le même journal que la capture directe. Elle se limite aux sources configurées et garde un checkpoint distinct de l'état des livraisons. Les règles sont identifiées par un `rule_id` stable.

Le service systemd supervise le proxy et Discord ; un watchdog vérifie les réponses Gateway. Les sauvegardes quotidiennes sont vérifiées par SHA-256 avant application de la rétention.

## Export et tests

```bash
venv/bin/python exporter.py dcejson-exporter
venv/bin/python exporter.py html-exporter
venv/bin/python exporter.py htmeml-exporter
venv/bin/python -m pytest -q -o addopts=
```

Les tests simulent l'API et les pannes réseau. Les tests du superviseur nécessitent Linux. Les données, tokens, journaux, fichiers SQLite et sauvegardes ne doivent pas être committés.
