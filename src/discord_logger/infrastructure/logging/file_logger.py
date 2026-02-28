"""
Logger écriture fichiers avec rotation journalière.

Ce module fournit un système de logging vers fichiers avec
rotation automatique basée sur la date.
"""

import os
import gzip
import shutil
from pathlib import Path
from datetime import datetime, date
from typing import Optional, Dict, TextIO
from threading import Lock


class FileLogger:
    """Logger écriture fichiers avec rotation journalière.
    
    Cette classe gère l'écriture des logs vers des fichiers texte,
    avec rotation automatique basée sur la date. Chaque canal peut
    avoir son propre fichier de log.
    
    Attributes:
        log_dir: Répertoire des fichiers de log
        _files: Cache des fichiers ouverts par canal
        _current_date: Date courante pour la rotation
        _lock: Verrou pour thread-safety
    """
    
    def __init__(self, log_dir: Path) -> None:
        """Initialise le logger avec le répertoire spécifié.
        
        Args:
            log_dir: Chemin du répertoire pour les fichiers de log
            
        Raises:
            OSError: Si le répertoire ne peut pas être créé
        """
        self.log_dir: Path = Path(log_dir)
        self._files: Dict[Optional[str], TextIO] = {}
        self._current_date: date = date.today()
        self._lock: Lock = Lock()
        
        self._ensure_log_dir()
    
    def _ensure_log_dir(self) -> None:
        """Crée le répertoire de logs s'il n'existe pas."""
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise OSError(f"Impossible de créer le répertoire {self.log_dir}: {e}") from e
    
    def _get_log_file(self, channel_id: Optional[str] = None) -> Path:
        """Obtient le chemin du fichier de log pour un canal.
        
        Vérifie si une rotation est nécessaire (changement de date).
        
        Args:
            channel_id: Identifiant du canal (None pour le log global)
            
        Returns:
            Chemin du fichier de log
        """
        current_date = date.today()
        
        if current_date != self._current_date:
            with self._lock:
                if current_date != self._current_date:
                    self._rotate_logs()
                    self._current_date = current_date
        
        date_str = current_date.strftime("%Y%m%d")
        
        if channel_id:
            filename = f"channel_{channel_id}_{date_str}.log"
        else:
            filename = f"all_messages_{date_str}.log"
        
        return self.log_dir / filename
    
    def _rotate_logs(self) -> None:
        """Effectue la rotation des logs (appelé au changement de date).
        
        Ferme tous les fichiers ouverts et compresse les anciens logs
        si nécessaire.
        """
        # Fermer tous les fichiers ouverts
        for channel_id, file_handle in list(self._files.items()):
            try:
                file_handle.flush()
                file_handle.close()
            except OSError as e:
                print(f"Erreur fermeture fichier {channel_id}: {e}")
        
        self._files.clear()
        
        # Compression des logs de la veille
        self._compress_old_logs()
    
    def _compress_old_logs(self) -> None:
        """Compresse les logs de plus d'un jour."""
        if not self.log_dir.exists():
            return
        
        yesterday = (date.today()).strftime("%Y%m%d")
        
        for log_file in self.log_dir.glob("*.log"):
            # Ne pas compresser les logs du jour
            if yesterday in log_file.name:
                continue
            
            gzip_path = log_file.with_suffix('.log.gz')
            if gzip_path.exists():
                continue  # Déjà compressé
            
            try:
                with open(log_file, 'rb') as f_in:
                    with gzip.open(gzip_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                log_file.unlink()  # Supprimer l'original
            except OSError as e:
                print(f"Erreur compression {log_file}: {e}")
    
    def _open_file(self, channel_id: Optional[str]) -> TextIO:
        """Ouvre ou récupère un fichier de log pour un canal.
        
        Args:
            channel_id: Identifiant du canal
            
        Returns:
            Descripteur de fichier ouvert en mode append
        """
        with self._lock:
            if channel_id in self._files:
                return self._files[channel_id]
            
            log_path = self._get_log_file(channel_id)
            
            try:
                file_handle = open(log_path, 'a', encoding='utf-8', buffering=1)
                self._files[channel_id] = file_handle
                return file_handle
            except OSError as e:
                raise OSError(f"Impossible d'ouvrir {log_path}: {e}") from e
    
    def log(self, message: str, channel_id: Optional[str] = None) -> None:
        """Écrit un message dans le fichier de log.
        
        Args:
            message: Le message à écrire
            channel_id: Canal cible (None pour log global)
            
        Raises:
            OSError: Si l'écriture échoue
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {message}\n"
        
        try:
            file_handle = self._open_file(channel_id)
            file_handle.write(log_line)
            file_handle.flush()
        except OSError as e:
            raise OSError(f"Erreur écriture log: {e}") from e
    
    def log_json(self, data: dict, channel_id: Optional[str] = None) -> None:
        """Écrit des données JSON dans le fichier de log.
        
        Args:
            data: Dictionnaire à sérialiser en JSON
            channel_id: Canal cible (None pour log global)
        """
        import json
        try:
            json_line = json.dumps(data, ensure_ascii=False)
            self.log(json_line, channel_id)
        except (TypeError, json.JSONEncodeError) as e:
            self.log(f"[ERREUR JSON] {e}: {str(data)}", channel_id)
    
    def close(self, channel_id: Optional[str] = None) -> None:
        """Ferme le fichier de log pour un canal spécifique ou tous.
        
        Args:
            channel_id: Canal à fermer (None pour tous)
        """
        with self._lock:
            if channel_id is None:
                # Fermer tous les fichiers
                for cid, file_handle in list(self._files.items()):
                    try:
                        file_handle.flush()
                        file_handle.close()
                    except OSError as e:
                        print(f"Erreur fermeture fichier {cid}: {e}")
                self._files.clear()
            elif channel_id in self._files:
                try:
                    self._files[channel_id].flush()
                    self._files[channel_id].close()
                except OSError as e:
                    print(f"Erreur fermeture fichier {channel_id}: {e}")
                del self._files[channel_id]
    
    def get_log_files(self) -> list:
        """Liste tous les fichiers de log présents.
        
        Returns:
            Liste des chemins de fichiers de log
        """
        if not self.log_dir.exists():
            return []
        
        log_files = []
        for ext in ['.log', '.log.gz']:
            log_files.extend(self.log_dir.glob(f'*{ext}'))
        
        return sorted(log_files)
    
    def get_stats(self) -> dict:
        """Retourne des statistiques sur les logs.
        
        Returns:
            Dictionnaire avec les statistiques
        """
        files = self.get_log_files()
        total_size = sum(f.stat().st_size for f in files if f.exists())
        
        return {
            'log_dir': str(self.log_dir),
            'open_files': len(self._files),
            'total_files': len(files),
            'total_size_bytes': total_size,
            'current_date': self._current_date.isoformat()
        }
    
    def __enter__(self) -> 'FileLogger':
        """Support du context manager."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Ferme tous les fichiers à la sortie du contexte."""
        self.close()
    
    def __del__(self) -> None:
        """Destructeur: assure la fermeture des fichiers."""
        try:
            self.close()
        except:
            pass  # Ignorer les erreurs dans le destructeur
