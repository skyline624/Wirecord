# Validation du déploiement du 14 septembre 2026

- Branche locale : `fix/wirecord-reliability-20260914` ; état initial du VPS conservé dans le commit `de0a905`.
- Tests initiaux : 97 succès. Version fiabilisée : 128 succès sous Linux/Python 3.13 ; les trois tests de superviseur sont réservés à Linux.
- Compte Gateway vérifié : Jarl Panda, `462628780574375936` ; capture active et réponses ACK reçues au-delà de la grâce de démarrage.
- Sept règles inchangées quant aux sources et destinations. Libellés enrichis avec les vrais noms des serveurs.
- Bootstrap : dix transferts historiques importés (1 Représentants, 7 Sibylla, 2 Recherche), tous marqués envoyés ; aucune republication.
- Test réel utilisateur : source `1549065050529075201`, destination `1549065085698310216`, compte Jarl Panda, instantané natif présent, une seule copie vérifiée dans Discord, une seule tentative, délai 8,385 secondes. La date de capture Gateway correspond à celle du message source.
- Sauvegarde initiale restaurée dans un dossier isolé : 20 320 fichiers vérifiés. Base SQLite, index, préfixes Gateway et fichiers REST inclus.
- Export complet de l'archive restaurée : succès, 931 conversations et 207 536 messages uniques. Sur les 11 530 messages récupérés précédemment, un a depuis été supprimé sur Discord : événement `MESSAGE_DELETE` vérifié le 14 septembre à 14:08:23 UTC (Gateway 1361, message `1548967947664363623`). L'exporteur conserve son comportement d'exclusion des messages supprimés ; le message reste présent dans la sauvegarde brute. Aucune absence inexpliquée.
- Dernière sauvegarde vérifiée de la version déployée : `/root/backups/wirecord-daily/wirecord-20260914T143454-046471710-utc.tar.gz`.
- Après un cycle de rattrapage automatique supplémentaire, le test utilisateur est toujours présent une seule fois ; checkpoint avancé jusqu'à son identifiant, onze livraisons confirmées au total, aucune attente ou erreur.
- Sauvegardes quotidiennes : 04:00 Europe/Paris, rétention sept jours et quatre semaines. Rotation des logs vérifiée ; logrotate installé car absent du VPS.
- Retour arrière capture seule : `/root/backups/wirecord-deploy-20260914T142454Z/rollback.py`. Il préserve la base de livraisons actuelle et les archives.

Les transferts à résultat incertain ne sont jamais renvoyés sans preuve ou décision explicite. Les fichiers joints distants restent représentés par leurs liens ; la sauvegarde ne télécharge pas systématiquement leur contenu.

Le compte de développement conserve `delivery_enabled=false`. En production, la capture, le rattrapage et les envois sont activés.
