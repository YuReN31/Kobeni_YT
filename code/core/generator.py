import requests
import json
import re
import time
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import config

class LinkGenerator:
    def __init__(self, log_callback=None):
        self.log_callback = log_callback or self._default_log
        self.proxy_url = "https://ytdown.to/proxy.php"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Origin': 'https://ytdown.to',
            'Referer': 'https://ytdown.to/pt2/',
            'X-Requested-With': 'XMLHttpRequest'
        })
        self.session.timeout = (10, 30)
    
    def _default_log(self, msg, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [{level}] {msg}")
    
    def log(self, msg, level="INFO"):
        self.log_callback(msg, level)
    
    def get_video_data(self, youtube_url, max_retries=2):
        for attempt in range(max_retries):
            try:
                self.log(f"Obtendo dados do vídeo (tentativa {attempt+1}/{max_retries})...", "DEBUG")
                
                payload = {'url': youtube_url}
                try:
                    response = self.session.post(self.proxy_url, data=payload, timeout=15)
                    response.raise_for_status()
                except requests.exceptions.Timeout:
                    self.log(f"Timeout na conexão (15s) tentativa {attempt+1}", "ERROR")
                    if attempt < max_retries - 1:
                        time.sleep(2)
                    continue
                except requests.exceptions.ConnectionError:
                    self.log(f"Erro de conexão tentativa {attempt+1}", "ERROR")
                    if attempt < max_retries - 1:
                        time.sleep(3)
                    continue
                
                try:
                    data = response.json()
                except json.JSONDecodeError:
                    self.log(f"Resposta não é JSON válido", "ERROR")
                    if attempt < max_retries - 1:
                        time.sleep(2)
                    continue
                
                if 'api' not in data:
                    self.log("Resposta inválida da API (sem 'api' field)", "ERROR")
                    if attempt < max_retries - 1:
                        time.sleep(2)
                    continue
                
                api = data['api']
                
                if api.get('status') == 'ERROR':
                    error_msg = api.get('message', 'Erro desconhecido')
                    self.log(f"Erro da API: {error_msg}", "ERROR")
                    if attempt < max_retries - 1:
                        time.sleep(2)
                    continue
                
                if not api.get('mediaItems'):
                    self.log("Nenhum formato de mídia encontrado", "ERROR")
                    if attempt < max_retries - 1:
                        time.sleep(2)
                    continue
                
                self.log(f"Dados obtidos com sucesso", "INFO")
                
                video_info = {
                    'title': api.get('title', 'Vídeo'),
                    'channel': api.get('userInfo', {}).get('name', 'Desconhecido'),
                    'duration': api.get('mediaItems', [{}])[0].get('mediaDuration', ''),
                    'formats': self._parse_formats(api.get('mediaItems', []))
                }
                
                self.log(f"Vídeo: {video_info['title'][:50]}...", "INFO")
                return video_info
            
            except Exception as e:
                self.log(f"Erro inesperado: {str(e)[:60]}", "ERROR")
                if attempt < max_retries - 1:
                    time.sleep(3)
        
        self.log(f"Falha após {max_retries} tentativas", "ERROR")
        return None
    
    def _parse_formats(self, media_items):
        formats = []
        
        for idx, item in enumerate(media_items):
            if not item.get('mediaUrl'):
                continue
                
            fmt = {
                'type': item.get('type', 'unknown'),
                'quality': item.get('mediaQuality', ''),
                'resolution': item.get('mediaRes', ''),
                'extension': item.get('mediaExtension', ''),
                'file_size': item.get('mediaFileSize', 'unknown'),
                'processing_url': item.get('mediaUrl', ''),
                'resolution_numeric': self._extract_resolution(item.get('mediaRes', '')),
                'bitrate': self._extract_bitrate(item.get('mediaQuality', ''))
            }
            
            if fmt['processing_url']:
                formats.append(fmt)
        
        return formats
    
    def _extract_resolution(self, resolution_str):
        if not resolution_str:
            return 0
        
        if 'x' in resolution_str:
            try:
                height = resolution_str.split('x')[1]
                return int(height)
            except:
                return 0
        
        match = re.search(r'(\d+)', resolution_str)
        if match:
            return int(match.group(1))
        
        return 0
    
    def _extract_bitrate(self, quality_str):
        if not quality_str:
            return 0
        
        match = re.search(r'(\d+)', quality_str)
        if match:
            return int(match.group(1))
        
        return 0
    
    def get_download_url(self, processing_url, quality_name, timeout=None, attempt=1):
        if timeout is None:
            timeout = 60  
        
        start_time = time.time()
        last_percent = -1
        max_retries = 2 
        
        self.log(f"Processando {quality_name} (tentativa {attempt}/{max_retries})...", "INFO")
        
        if not processing_url or not processing_url.startswith('http'):
            self.log(f"URL de processamento inválida: {processing_url[:50]}...", "ERROR")
            return None
        
        while time.time() - start_time < timeout:
            try:
                response = self.session.get(processing_url, timeout=10)
                response.raise_for_status()
                
                try:
                    data = response.json()
                except:
                    self.log(f"Resposta não é JSON válido", "WARNING")
                    time.sleep(2)
                    continue
                
                percent_str = data.get('percent', '0%')
                file_url = data.get('fileUrl', '')
                
                is_completed = False
                percent_num = 0
                
                if isinstance(percent_str, str):
                    percent_str_lower = percent_str.strip().lower()
                    if percent_str_lower == 'completed' or percent_str_lower == '100%':
                        is_completed = True
                        percent_num = 100
                    else:
                        percent_num = self._parse_percent(percent_str)
                        is_completed = percent_num == 100
                else:
                    percent_num = int(percent_str)
                    is_completed = percent_num == 100
                
                if is_completed or file_url:
                    if file_url and file_url.startswith('http'):
                        self.log(f"Link pronto: {quality_name}", "INFO")
                        return file_url
                    elif is_completed:
                        self.log(f"Processamento completo mas sem URL, tentando novamente...", "WARNING")
                        if time.time() - start_time < timeout - 5:
                            time.sleep(2)
                            continue
                
                if percent_num != last_percent and percent_num > 0:
                    last_percent = percent_num
                    if percent_num < 100:
                        self.log(f"Progresso: {percent_num}%", "DEBUG")
                
                if percent_num == 0 and time.time() - start_time > 20:
                    self.log(f"Sem progresso por 20 segundos", "WARNING")
                    break
                
                time.sleep(3)
            
            except requests.exceptions.Timeout:
                self.log(f"Timeout ao verificar progresso", "WARNING")
                time.sleep(3)
            except requests.exceptions.ConnectionError:
                self.log(f"Erro de conexão ao verificar progresso", "WARNING")
                time.sleep(5)
            except Exception as e:
                self.log(f"Erro: {str(e)[:40]}", "WARNING")
                time.sleep(3)
        
        self.log(f"Timeout {timeout}s para {quality_name}", "WARNING")
        
        if attempt < max_retries:
            self.log(f"Nova tentativa em 5 segundos...", "WARNING")
            time.sleep(5)
            return self.get_download_url(processing_url, quality_name, timeout, attempt + 1)
        
        return None
    
    def _parse_percent(self, percent_str):
        try:
            if isinstance(percent_str, str):
                cleaned = percent_str.strip().rstrip('%')
                if cleaned.isdigit():
                    return int(cleaned)
                return 0
            return int(percent_str)
        except:
            return 0
    
    def generate_link(self, youtube_url, quality="480p"):
        self.log(f"Iniciando geração de link para {quality}", "INFO")
        
        video_info = self.get_video_data(youtube_url, max_retries=2)
        if not video_info:
            self.log(f"Falha ao obter dados do vídeo", "ERROR")
            return None
        
        self.log(f"Procurando qualidade {quality}...", "DEBUG")
        
        target_format = None
        quality_num = self._extract_resolution(quality)
        
        for fmt in video_info['formats']:
            if fmt['resolution_numeric'] == quality_num:
                target_format = fmt
                self.log(f"Qualidade encontrada: {fmt['type']} {fmt['resolution'] or fmt['quality']}", "INFO")
                break
        
        if not target_format:
            for fmt in video_info['formats']:
                quality_str = (fmt['quality'] or fmt['resolution']).lower()
                if quality.lower() in quality_str:
                    target_format = fmt
                    self.log(f"Qualidade encontrada por texto: {fmt['type']} {fmt['resolution'] or fmt['quality']}", "INFO")
                    break
        
        if not target_format and video_info['formats']:
            target_format = video_info['formats'][0]
            self.log(f"Usando primeiro formato disponível: {target_format['type']} {target_format['resolution'] or target_format['quality']}", "WARNING")
        
        if not target_format:
            self.log(f"Nenhum formato disponível", "ERROR")
            return None
        
        if not target_format.get('processing_url'):
            self.log(f"URL de processamento não disponível", "ERROR")
            return None
        
        self.log(f"Processando vídeo no servidor...", "INFO")
        download_url = self.get_download_url(target_format['processing_url'], quality)
        
        if not download_url:
            self.log(f"Falha ao obter URL de download", "ERROR")
            return None
        
        if not download_url.startswith('http'):
            self.log(f"URL final inválida", "ERROR")
            return None
        
        result = {
            'title': video_info['title'],
            'channel': video_info['channel'],
            'quality': quality,
            'file_size': target_format['file_size'],
            'extension': target_format['extension'],
            'download_url': download_url,
            'timestamp': datetime.now().isoformat()
        }
        
        self.log(f"Link gerado com sucesso: {result['title'][:50]}...", "INFO")
        
        return result