"""
Tests unitaires pour gateway_logger.py - Logger de messages Gateway.
"""

import pytest
import os
import json
import hashlib
import tempfile
from datetime import datetime
from unittest.mock import patch, MagicMock, mock_open
import sys

# Importer le module avec son chemin
sys.path.insert(0, '/home/pc/devellopement/discordless')
import gateway_logger


@pytest.mark.unit
class TestSeenIdsPersistence:
    """Tests pour la persistance des IDs vus."""
    
    def test_load_seen_ids_empty(self, temp_dir, monkeypatch):
        """Test le chargement quand le fichier n'existe pas."""
        monkeypatch.setattr(gateway_logger, 'PERSISTENCE_FILE', os.path.join(temp_dir, '.seen_keys.json'))
        result = gateway_logger.load_seen_ids()
        assert result == set()
    
    def test_load_seen_ids_valid(self, temp_dir, monkeypatch):
        """Test le chargement d'un fichier valide."""
        monkeypatch.setattr(gateway_logger, 'PERSISTENCE_FILE', os.path.join(temp_dir, '.seen_keys.json'))
        data = {'keys': ['key1', 'key2', 'key3']}
        with open(gateway_logger.PERSISTENCE_FILE, 'w') as f:
            json.dump(data, f)
        result = gateway_logger.load_seen_ids()
        assert result == {'key1', 'key2', 'key3'}
    
    def test_load_seen_ids_invalid_json(self, temp_dir, monkeypatch):
        """Test le chargement avec JSON invalide."""
        monkeypatch.setattr(gateway_logger, 'PERSISTENCE_FILE', os.path.join(temp_dir, '.seen_keys.json'))
        with open(gateway_logger.PERSISTENCE_FILE, 'w') as f:
            f.write('invalid json')
        result = gateway_logger.load_seen_ids()
        assert result == set()
    
    def test_save_seen_ids(self, temp_dir, monkeypatch):
        """Test la sauvegarde des IDs."""
        monkeypatch.setattr(gateway_logger, 'PERSISTENCE_FILE', os.path.join(temp_dir, '.seen_keys.json'))
        monkeypatch.setattr(gateway_logger, 'seen_message_keys', {'key1', 'key2'})
        gateway_logger.save_seen_ids()
        
        assert os.path.exists(gateway_logger.PERSISTENCE_FILE)
        with open(gateway_logger.PERSISTENCE_FILE, 'r') as f:
            data = json.load(f)
        assert 'keys' in data
        assert 'last_saved' in data


@pytest.mark.unit
class TestDirectoryManagement:
    """Tests pour la gestion des répertoires."""
    
    def test_ensure_dirs(self, temp_dir, monkeypatch):
        """Test la création des répertoires."""
        logs_dir = os.path.join(temp_dir, 'logs', 'messages')
        monkeypatch.setattr(gateway_logger, 'LOGS_DIR', logs_dir)
        gateway_logger.ensure_dirs()
        assert os.path.exists(logs_dir)


@pytest.mark.unit
class TestLogFilename:
    """Tests pour la génération des noms de fichier."""
    
    def test_get_log_filename_all(self, temp_dir, monkeypatch):
        """Test le nom de fichier pour tous les messages."""
        monkeypatch.setattr(gateway_logger, 'LOGS_DIR', temp_dir)
        today = datetime.now().strftime("%Y%m%d")
        result = gateway_logger.get_log_filename()
        assert f'all_messages_{today}.log' in result
    
    def test_get_log_filename_channel(self, temp_dir, monkeypatch):
        """Test le nom de fichier pour un canal spécifique."""
        monkeypatch.setattr(gateway_logger, 'LOGS_DIR', temp_dir)
        today = datetime.now().strftime("%Y%m%d")
        result = gateway_logger.get_log_filename('123456789')
        assert f'channel_123456789_{today}.log' in result


@pytest.mark.unit
class TestDateManagement:
    """Tests pour la gestion des dates."""
    
    def test_get_current_date(self):
        """Test le format de la date actuelle."""
        result = gateway_logger.get_current_date()
        assert len(result) == 8  # YYYYMMDD
        assert result.isdigit()


@pytest.mark.unit
class TestLogRotation:
    """Tests pour la rotation des logs."""
    
    def test_rotate_logs_new_day(self, temp_dir, monkeypatch):
        """Test la rotation quand la date change."""
        monkeypatch.setattr(gateway_logger, 'LOGS_DIR', temp_dir)
        
        old_date = '20240101'
        monkeypatch.setattr(gateway_logger, 'last_log_date', old_date)
        monkeypatch.setattr(gateway_logger, 'log_files', {})
        
        with patch.object(gateway_logger, 'get_current_date', return_value='20240102'):
            gateway_logger.rotate_logs_if_needed()
            assert gateway_logger.last_log_date == '20240102'


@pytest.mark.unit
class TestWriteLog:
    """Tests pour l'écriture des logs."""
    
    def test_write_log_basic(self, temp_dir, monkeypatch):
        """Test l'écriture d'un log basique."""
        monkeypatch.setattr(gateway_logger, 'LOGS_DIR', temp_dir)
        monkeypatch.setattr(gateway_logger, 'log_files', {})
        monkeypatch.setattr(gateway_logger, 'last_log_date', datetime.now().strftime("%Y%m%d"))
        
        message_data = {
            'timestamp': '2024-01-15T10:30:00.000Z',
            'channel_id': '987654321098765432',
            'username': 'testuser',
            'content': 'Hello, World!'
        }
        
        gateway_logger.write_log(message_data)
        
        today = datetime.now().strftime("%Y%m%d")
        log_file = os.path.join(temp_dir, f'all_messages_{today}.log')
        assert os.path.exists(log_file)
        
        with open(log_file, 'r') as f:
            content = f.read()
        assert 'testuser' in content
        assert 'Hello, World!' in content


@pytest.mark.unit
class TestPayloadProcessing:
    """Tests pour le traitement des payloads."""
    
    def test_convert_payload_bytes(self):
        """Test la conversion de bytes."""
        result = gateway_logger.convert_payload(b'test')
        assert result == 'test'
    
    def test_convert_payload_bytes_invalid_utf8(self):
        """Test la conversion de bytes invalides."""
        result = gateway_logger.convert_payload(b'\xff\xfe')
        assert isinstance(result, str)
    
    def test_convert_payload_list(self):
        """Test la conversion de liste."""
        result = gateway_logger.convert_payload([b'test1', b'test2'])
        assert result == ['test1', 'test2']
    
    def test_convert_payload_dict(self):
        """Test la conversion de dict."""
        result = gateway_logger.convert_payload({b'key': b'value'})
        assert result == {'key': 'value'}
    
    def test_process_payload_not_dict(self):
        """Test le traitement d'un payload non-dict."""
        result = gateway_logger.process_payload("not a dict", None)
        assert result is None
    
    def test_process_payload_wrong_type(self):
        """Test le traitement avec mauvais type de message."""
        payload = {'t': 'MESSAGE_UPDATE', 'd': {}}
        result = gateway_logger.process_payload(payload, None)
        assert result is None
    
    def test_process_payload_invalid_data(self):
        """Test le traitement avec données invalides."""
        payload = {'t': 'MESSAGE_CREATE', 'd': 'not a dict'}
        result = gateway_logger.process_payload(payload, None)
        assert result is None
    
    def test_process_payload_valid(self, monkeypatch):
        """Test le traitement d'un payload valide."""
        monkeypatch.setattr(gateway_logger, 'seen_message_keys', set())
        
        payload = {
            't': 'MESSAGE_CREATE',
            'd': {
                'id': '123456789',
                'channel_id': '987654321',
                'timestamp': '2024-01-15T10:30:00.000Z',
                'author': {'username': 'testuser'},
                'content': 'Hello!'
            }
        }
        
        result = gateway_logger.process_payload(payload, None)
        
        assert result is not None
        assert result['id'] == '123456789'
        assert result['username'] == 'testuser'
        assert result['content'] == 'Hello!'
    
    def test_process_payload_deduplication(self, monkeypatch):
        """Test la déduplication des messages."""
        monkeypatch.setattr(gateway_logger, 'seen_message_keys', set())
        
        payload = {
            't': 'MESSAGE_CREATE',
            'd': {
                'id': '123456789',
                'channel_id': '987654321',
                'timestamp': '2024-01-15T10:30:00.000Z',
                'author': {'username': 'testuser'},
                'content': 'Hello!'
            }
        }
        
        # Premier traitement
        result1 = gateway_logger.process_payload(payload, None)
        assert result1 is not None
        
        # Second traitement avec même contenu
        result2 = gateway_logger.process_payload(payload, None)
        assert result2 is None
    
    def test_scan_gateway_files(self, temp_dir, monkeypatch):
        """Test le scan des fichiers gateway."""
        monkeypatch.setattr(gateway_logger, 'GATEWAYS_DIR', temp_dir)
        
        # Créer des fichiers de test
        with open(os.path.join(temp_dir, 'test1_data'), 'w') as f:
            f.write('data1')
        with open(os.path.join(temp_dir, 'test2_data'), 'w') as f:
            f.write('data2')
        
        result = gateway_logger.scan_gateway_files()
        assert len(result) == 2
        assert any('test1_data' in f for f in result)
        assert any('test2_data' in f for f in result)
