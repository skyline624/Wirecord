"""
Stockage persistant des clés vues.

Ce module fournit un mécanisme de stockage persistant pour suivre
les clés déjà rencontrées, utile pour éviter les doublons et
gérer l'état entre les sessions.
"""

import json
import os
import fcntl
from pathlib import Path
from typing import Set, Optional, List
from datetime import datetime


class KeyStore:
    """Stockage persistant des clés vues avec gestion de l'historique.
    
    Cette classe gère un ensemble de clés persistant sur disque,
    avec une limite sur le nombre de clés conservées et un mécanisme
    de verrouillage pour les accès concurrents.
    
    Attributes:
        filepath: Chemin du fichier de stockage JSON
        max_keys: Nombre maximum de clés à conserver
        _keys: Ensemble des clés en mémoire
        _lock_file: Descripteur du fichier de verrouillage
    """
    
    DEFAULT_MAX_KEYS: int = 3000
    
    def __init__(
        self, 
        filepath: Path,
        max_keys: int = DEFAULT_MAX_KEYS
    ) -> None:
        """Initialise le KeyStore avec le fichier spécifié.
        
        Args:
            filepath: Chemin du fichier JSON de stockage
            max_keys: Nombre maximum de clés à conserver (défaut: 3000)
            
        Raises:
            ValueError: Si max_keys est négatif ou nul
            OSError: Si le répertoire parent ne peut pas être créé
        """
        if max_keys <= 0:
            raise ValueError(f"max_keys doit être positif, reçu: {max_keys}")
        
        self.filepath: Path = Path(filepath)
        self.max_keys: int = max_keys
        self._keys: Set[str] = set()
        self._lock_file: Optional[int] = None
        
        # Assurer l'existence du répertoire parent
        self._ensure_directory()
        
        # Charger les données existantes
        self._load()
    
    def _ensure_directory(self) -> None:
        """Crée le répertoire parent si nécessaire."""
        try:
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise OSError(
                f"Impossible de créer le répertoire {self.filepath.parent}: {e}"
            ) from e
    
    def _acquire_lock(self) -> None:
        """Acquiert un verrou exclusif sur le fichier de stockage."""
        lock_path = self.filepath.with_suffix('.lock')
        try:
            self._lock_file = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
            fcntl.flock(self._lock_file, fcntl.LOCK_EX)
        except OSError as e:
            raise OSError(f"Impossible d'acquérir le verrou: {e}") from e
    
    def _release_lock(self) -> None:
        """Libère le verrou sur le fichier de stockage."""
        if self._lock_file is not None:
            try:
                fcntl.flock(self._lock_file, fcntl.LOCK_UN)
                os.close(self._lock_file)
                self._lock_file = None
            except OSError:
                pass  # Ignorer les erreurs lors de la libération
    
    def _load(self) -> None:
        """Charge les clés depuis le fichier de stockage.
        
        Si le fichier n'existe pas ou est corrompu, initialise
        avec un ensemble vide.
        """
        if not self.filepath.exists():
            self._keys = set()
            return
        
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            if not isinstance(data, dict):
                raise ValueError("Format JSON invalide: objet attendu")
                
            keys_list = data.get('keys', [])
            if not isinstance(keys_list, list):
                raise ValueError("Format JSON invalide: 'keys' doit être une liste")
            
            self._keys = set(str(k) for k in keys_list)
            
        except json.JSONDecodeError as e:
            # Fichier corrompu, sauvegarder une copie et recommencer
            self._backup_corrupted_file()
            self._keys = set()
        except (OSError, ValueError) as e:
            print(f"Erreur chargement KeyStore: {e}")
            self._keys = set()
    
    def _backup_corrupted_file(self) -> None:
        """Sauvegarde un fichier corrompu avant de l'écraser."""
        if self.filepath.exists():
            backup_path = self.filepath.with_suffix(
                f'.corrupted.{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
            )
            try:
                self.filepath.rename(backup_path)
                print(f"Fichier corrompu sauvegardé: {backup_path}")
            except OSError:
                pass
    
    def save(self) -> None:
        """Sauvegarde les clés dans le fichier de stockage.
        
        Conserve uniquement les max_keys les plus récentes.
        Utilise un verrouillage pour éviter les conflits d'accès.
        """
        self._acquire_lock()
        try:
            # Convertir en liste et garder les plus récentes
            keys_list: List[str] = list(self._keys)
            if len(keys_list) > self.max_keys:
                keys_list = keys_list[-self.max_keys:]
            
            data = {
                'keys': keys_list,
                'metadata': {
                    'saved_at': datetime.now().isoformat(),
                    'count': len(keys_list),
                    'max_keys': self.max_keys
                }
            }
            
            # Écriture atomique via fichier temporaire
            temp_path = self.filepath.with_suffix('.tmp')
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # Remplacement atomique
            temp_path.replace(self.filepath)
            
        except (OSError, json.JSONEncodeError) as e:
            raise OSError(f"Erreur sauvegarde KeyStore: {e}") from e
        finally:
            self._release_lock()
    
    def add(self, key: str) -> bool:
        """Ajoute une clé à l'ensemble.
        
        Args:
            key: La clé à ajouter
            
        Returns:
            True si la clé était nouvelle, False si déjà présente
        """
        if not isinstance(key, str):
            key = str(key)
        
        is_new = key not in self._keys
        self._keys.add(key)
        
        # Auto-sauvegarde si la taille dépasse la limite
        if len(self._keys) > self.max_keys * 1.1:  # 10% de marge
            self.save()
        
        return is_new
    
    def add_many(self, keys: List[str]) -> int:
        """Ajoute plusieurs clés à l'ensemble.
        
        Args:
            keys: Liste des clés à ajouter
            
        Returns:
            Nombre de clés effectivement ajoutées (nouvelles)
        """
        added = 0
        for key in keys:
            if self.add(key):
                added += 1
        return added
    
    def __contains__(self, key: str) -> bool:
        """Vérifie si une clé est présente.
        
        Args:
            key: La clé à rechercher
            
        Returns:
            True si la clé existe, False sinon
        """
        return str(key) in self._keys
    
    def __len__(self) -> int:
        """Retourne le nombre de clés stockées."""
        return len(self._keys)
    
    def clear(self) -> None:
        """Vide l'ensemble des clés et sauvegarde."""
        self._keys.clear()
        self.save()
    
    def get_stats(self) -> dict:
        """Retourne des statistiques sur le stockage.
        
        Returns:
            Dictionnaire avec les statistiques
        """
        return {
            'total_keys': len(self._keys),
            'max_keys': self.max_keys,
            'utilization': len(self._keys) / self.max_keys * 100,
            'filepath': str(self.filepath)
        }
    
    def __enter__(self) -> 'KeyStore':
        """Support du context manager."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Sauvegarde automatique à la sortie du contexte."""
        self.save()
