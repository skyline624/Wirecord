# Exploitation Wirecord

Le déploiement utilise `/root/discord/wirecord`, Python 3.13, mitmproxy et le client Discord sous Xvfb. Le code se développe dans `D:\developpement\wirecord`. Le compte est exclusivement Jarl Panda (`462628780574375936`). Les identifiants et URL de webhook restent dans `config.json`, jamais dans Git.

## Configuration et état

Depuis le dossier du projet, utiliser `venv/bin/python -m discordless` sur Linux, `python -m discordless` dans l'environnement Windows. `--config CHEMIN` précède la sous-commande.

```text
python -m discordless check-config
python -m discordless status
python -m discordless status --json
python -m discordless deliveries --status uncertain
python -m discordless recover --channel ID
python -m discordless recover --channel ID --execute
```

`recover` simule par défaut. `--execute` archive et alimente la file ; seul le travailleur de production effectue les envois. Les sept canaux configurés sont les seuls accessibles à cette commande. Le rattrapage automatique s'exécute au démarrage, à la reconnexion et toutes les cinq minutes. Les dates JSON sont UTC ; l'affichage opérateur est en heure de Paris.

Champs ajoutés : `state_path` (défaut `state/wirecord.sqlite3`), `delivery_enabled` (défaut false), `recovery_enabled` (true), `recovery_since` (`2026-09-08T16:24:00Z`), `recovery_interval` (300 secondes), et `rule_id`/`label` par règle. Garder les rule_id stables après initialisation. Toute nouvelle règle exige une réconciliation `recover --channel ID --bootstrap --execute` avant ses premiers envois. Les champs existants sont conservés ; les destinations doivent être explicites pour vérifier les accusés d'envoi.

La base SQLite stocke les contenus nécessaires à la livraison, les références Discord, les checkpoints et les erreurs. Elle doit bénéficier des mêmes droits restreints que l'archive. Elle ne contient pas les tokens. Un message enregistré comme envoyé n'est jamais renvoyé automatiquement. Une réponse d'envoi perdue devient incertaine ; le moteur recherche une correspondance unique dans la destination, sans renvoi aveugle.

```text
python -m discordless deliveries --id 42 --action confirm --destination-id ID_DISCORD --execute
python -m discordless deliveries --id 42 --action retry --execute
```

La confirmation vérifie le message destination. Le retry est une décision opérateur explicite après inspection : il peut créer un doublon si le premier envoi avait réussi sans réponse. Les erreurs bloquées ou incertaines retiennent les messages suivants de la destination afin de conserver leur ordre. Après correction d'une permission, relancer la récupération, puis résoudre les livraisons bloquées concernées.

## Supervision et sauvegardes

`wirecord.service` surveille le proxy, Discord et la santé Gateway (grâce 120 s, trois intervalles sans ACK). Aucun redémarrage n'est déclenché parce qu'un salon reste silencieux. Trois tentatives sont autorisées sur quinze minutes. Après correction d'un démarrage bloqué : `systemctl reset-failed wirecord && systemctl start wirecord`.

`wirecord-backup.timer` lance une sauvegarde à 04:00 Europe/Paris. Chaque sauvegarde contient une copie SQLite cohérente, les préfixes complets des flux Gateway, les réponses archivées référencées, la configuration, le code et les unités de service. Elle est vérifiée avant la rétention : sept jours distincts et quatre semaines distinctes, sans supprimer les derniers fichiers en cas d'échec de création. Les sauvegardes restent sur le même VPS conformément au choix utilisateur.

```text
python -m discordless backup
python -m discordless backup --verify backups/NOM.tar.gz
python -m discordless backup --verify backups/NOM.tar.gz --restore /root/restore-wirecord-test
```

La restauration exige un dossier vide. Elle ne remplace jamais automatiquement la production. Les liens de pièces jointes sont conservés ; cela ne constitue pas une sauvegarde systématique des fichiers distants eux-mêmes.

Les journaux tournent quotidiennement ou au-delà de 100 Mo, avec sept rotations compressées. Le contrôle de taille est exécuté chaque minute ; le seuil peut être brièvement dépassé entre deux contrôles. Les journaux de diagnostic sont secondaires à l'archive et au journal SQLite transactionnel.

## Validation et retour arrière

Tests : `python -m pytest -q -o addopts=`. Les tests de supervision s'exécutent sous Linux. Le venv Linux de validation est séparé du venv de production.

Avant installation : sauvegarde complète vérifiée, copies du code/configuration/unités, puis migration avec `delivery_enabled=false`. Exécuter le bootstrap et vérifier les lignes envoyées/incertaines avant d'activer les envois. Le bootstrap importe les preuves de transfert précédentes et réconcilie les destinations ; l'archive entière n'est pas une file d'envoi.

En cas de rollback, arrêter la version courante, conserver sa base SQLite et l'archive, restaurer code et unités précédentes puis neutraliser les règles de transfert de l'ancienne configuration. Relancer la capture seule. Une ancienne version ne connaît pas le journal SQLite : ne réactiver ses transferts qu'après une nouvelle réconciliation. Les sauvegardes antérieures ne doivent jamais remplacer les nouveaux messages capturés pendant la bascule.
