import json
import subprocess
import re
import time
import threading
from pathlib import Path
from datetime import datetime
import logging
import shutil

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import config
from core.generator import LinkGenerator

log_file = config.LOGS_FOLDER / f"download_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class DownloadManager:
    def __init__(self, log_callback=None, progress_callback=None):
        self.log_callback = log_callback or self._default_log
        self.progress_callback = progress_callback or self._default_progress
        
        self.pending_queue = []
        self.processing_queue = []
        self.download_queue = []
        self.downloading = []
        self.completed_list = []
        self.failed_list = []
        
        self.paused = False
        self.stopped = False
        self.active_generators = 0
        self.download_progress = {}
        self.active_downloads = []
        self.active_processes = {}
        
        self.aria2_temp_folder = None
    
    def _default_log(self, msg, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        logger.log(getattr(logging, level, logging.INFO), msg)
        if config.DEBUG_MODE or level in ["ERROR", "WARNING"]:
            print(f"[{timestamp}] [{level}] {msg}")
    
    def _default_progress(self, item_id, percent, status=""):
        pass
    
    def log(self, msg, level="INFO"):
        self.log_callback(msg, level)
    
    def progress(self, item_id, percent, status=""):
        self.download_progress[item_id] = percent
        self.progress_callback(item_id, percent, status)
    
    def _ensure_aria2_temp_folder(self):
        if not self.aria2_temp_folder:
            download_folder = config.get_download_folder()
            self.aria2_temp_folder = download_folder / "aria2c_temp"
            self.aria2_temp_folder.mkdir(exist_ok=True)
            self.log(f"Pasta temporária aria2c criada: {self.aria2_temp_folder}", "DEBUG")
        return self.aria2_temp_folder
    
    def _move_from_temp_to_final(self, temp_file, final_file):
        try:
            if temp_file.exists():
                if final_file.exists():
                    final_file.unlink()
                shutil.move(str(temp_file), str(final_file))
                self.log(f"Arquivo movido para: {final_file.name}", "DEBUG")
                return True
        except Exception as e:
            self.log(f"Erro ao mover arquivo: {str(e)[:50]}", "ERROR")
        return False
    
    def add_to_queue(self, youtube_url, quality="480p"):
        item = {
            'id': f"yt_{int(time.time() * 1000)}",
            'youtube_url': youtube_url,
            'quality': quality,
            'title': youtube_url[:50],
            'status': 'pending',
            'download_url': None,
            'file_size': '0 MB',
            'error': None,
            'retry_count': 0,
            'download_retry_count': 0,
            'last_retry_time': 0
        }
        
        self.pending_queue.append(item)
        self.save_database()
        self.log(f"Vídeo adicionado na fila: {youtube_url[:50]}... (Qualidade: {quality})")
        return item['id']
    
    def _clean_filename(self, filename):
        invalid_chars = r'[\/:*?"<>|]'
        cleaned = re.sub(invalid_chars, '', filename)
        
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        if len(cleaned) > 100:
            cleaned = cleaned[:100]
            
        return cleaned
    
    def _find_aria2(self):
        if config.ARIA2C_PATH.exists():
            return str(config.ARIA2C_PATH)
        
        try:
            result = subprocess.run(['aria2c', '--version'], 
                                  capture_output=True, 
                                  timeout=5)
            if result.returncode == 0:
                return 'aria2c'
        except:
            pass
        
        return None
    
    def _parse_aria2_progress(self, output):
        if not output:
            return 0
        
        pattern = r'\((\d+)%\)'
        match = re.search(pattern, output)
        if match:
            return int(match.group(1))
        
        pattern2 = r'(\d+)%\s+'
        match2 = re.search(pattern2, output)
        if match2:
            return int(match2.group(1))
        
        pattern3 = r'(\d+\.?\d?)%'
        match3 = re.search(pattern3, output)
        if match3:
            try:
                return int(float(match3.group(1)))
            except:
                return 0
        
        return 0
    
    def _find_item_by_id(self, item_id):
        all_items = (self.pending_queue + self.processing_queue + 
                     self.download_queue + self.downloading + 
                     self.completed_list + self.failed_list)
        
        for item in all_items:
            if item.get('id') == item_id:
                return item
        return None
    
    def _generator_worker(self, quality):
        generator = LinkGenerator(log_callback=self.log_callback)
        
        max_links_to_generate = config.get_max_downloads() * 2
        link_count = 0
        
        while not self.stopped and self.pending_queue and link_count < max_links_to_generate:
            if self.stopped:
                break
                
            item = None
            try:
                if self.pending_queue:
                    item = self.pending_queue.pop(0)
                else:
                    break
            except:
                time.sleep(1)
                continue
            
            if self.stopped:
                if item:
                    self.pending_queue.insert(0, item)
                break
            
            current_time = time.time()
            if item.get('last_attempt', 0) > current_time - 30:
                self.log(f"Aguardando antes de reprocessar: {item.get('title', 'item')[:30]}...", "DEBUG")
                self.pending_queue.append(item)
                time.sleep(5)
                continue
            
            item['last_attempt'] = current_time
            self.processing_queue.append(item)
            item['status'] = 'processing'
            self.save_database()
            
            item_quality = item.get('quality', quality)
            self.log(f"Gerando link: {item['youtube_url'][:50]}... ({item_quality})")
            
            try:
                result = generator.generate_link(item['youtube_url'], item_quality)
                
                if result:
                    item.update(result)
                    item['status'] = 'ready_to_download'
                    item['download_url'] = result['download_url']
                    item['file_size'] = result.get('file_size', '0 MB')
                    item['title'] = result['title']
                    item['retry_count'] = 0
                    
                    self.processing_queue.remove(item)
                    self.download_queue.append(item)
                    
                    self.progress(item['id'], 100, f"Link pronto")
                    self.log(f"Link gerado: {item['title'][:50]}...")
                else:
                    item['retry_count'] = item.get('retry_count', 0) + 1
                    
                    if item['retry_count'] <= 2:
                        self.log(f"Falha ao gerar link, recolocando na fila (tentativa {item['retry_count']}/3)", "WARNING")
                        self.pending_queue.insert(0, item)
                        time.sleep(10)
                    else:
                        item['status'] = 'failed'
                        item['error'] = "Falha após 3 tentativas"
                        
                        if item in self.processing_queue:
                            self.processing_queue.remove(item)
                        self.failed_list.append(item)
                        
                        self.progress(item['id'], 0, f"Erro: {item['error']}")
                        self.log(f"Erro ao gerar link após 3 tentativas", "ERROR")
            
            except Exception as e:
                item['status'] = 'failed'
                item['error'] = str(e)[:80]
                
                if item in self.processing_queue:
                    self.processing_queue.remove(item)
                self.failed_list.append(item)
                
                self.progress(item['id'], 0, f"Erro: {item['error']}")
                self.log(f"Erro ao gerar link: {item['error']}", "ERROR")
            
            self.save_database()
            link_count += 1
            time.sleep(2)
        
        self.active_generators -= 1
        self.log(f"Gerador finalizou. Links gerados: {link_count}", "DEBUG")
    
    def _generate_additional_links(self, num_links, quality):
        if not self.pending_queue or num_links <= 0:
            return
        
        self.log(f"Gerando {num_links} links adicionais...", "DEBUG")
        
        threads = []
        for _ in range(min(num_links, len(self.pending_queue))):
            thread = threading.Thread(
                target=self._single_generator_worker,
                args=(quality,),
                daemon=True
            )
            thread.start()
            threads.append(thread)
            time.sleep(0.5)
        
        for thread in threads:
            try:
                thread.join(timeout=300)
            except:
                pass
    
    def _single_generator_worker(self, quality):
        generator = LinkGenerator(log_callback=self.log_callback)
        
        if not self.pending_queue or self.stopped:
            return
        
        item = None
        try:
            if self.pending_queue:
                item = self.pending_queue.pop(0)
            else:
                return
        except:
            return
        
        if self.stopped:
            if item:
                self.pending_queue.insert(0, item)
            return
        
        current_time = time.time()
        if item.get('last_attempt', 0) > current_time - 30:
            self.log(f"Aguardando antes de reprocessar link adicional", "DEBUG")
            self.pending_queue.append(item)
            return
        
        item['last_attempt'] = current_time
        self.processing_queue.append(item)
        item['status'] = 'processing'
        self.save_database()
        
        item_quality = item.get('quality', quality)
        
        try:
            result = generator.generate_link(item['youtube_url'], item_quality)
            
            if result:
                item.update(result)
                item['status'] = 'ready_to_download'
                item['download_url'] = result['download_url']
                item['file_size'] = result.get('file_size', '0 MB')
                item['title'] = result['title']
                item['retry_count'] = 0
                
                self.processing_queue.remove(item)
                self.download_queue.append(item)
                
                self.progress(item['id'], 100, f"Link pronto")
                self.log(f"Link adicional gerado: {item['title'][:50]}...", "DEBUG")
            else:
                item['retry_count'] = item.get('retry_count', 0) + 1
                
                if item['retry_count'] <= 2:
                    self.pending_queue.insert(0, item)
                else:
                    item['status'] = 'failed'
                    item['error'] = "Falha após 3 tentativas"
                    
                    if item in self.processing_queue:
                        self.processing_queue.remove(item)
                    self.failed_list.append(item)
                    
                    self.progress(item['id'], 0, f"Erro: {item['error']}")
        
        except Exception as e:
            item['status'] = 'failed'
            item['error'] = str(e)[:80]
            
            if item in self.processing_queue:
                self.processing_queue.remove(item)
            self.failed_list.append(item)
            
            self.progress(item['id'], 0, f"Erro: {item['error']}")
        
        self.save_database()
    
    def _download_with_retry(self, item, max_retries=5):
        aria2_path = self._find_aria2()
        if not aria2_path:
            item['status'] = 'failed'
            item['error'] = 'aria2c não encontrado'
            self.failed_list.append(item)
            return False
        
        download_folder = config.get_download_folder()
        temp_folder = self._ensure_aria2_temp_folder()
        
        title_clean = self._clean_filename(item['title'])
        filename = f"{title_clean} [{item['quality']}]"
        
        ext = '.m4a' if item['quality'] in ['48k', '128k'] else '.mp4'
        filename += ext
        
        final_filepath = download_folder / filename
        temp_filepath = temp_folder / filename
        
        for attempt in range(max_retries):
            try:
                if not item['download_url'] or not item['download_url'].startswith('http'):
                    self.log(f"URL inválida para download", "WARNING")
                    time.sleep(5)
                    continue
                
                current_time = time.time()
                if item.get('last_retry_time', 0) > current_time - 10:
                    time.sleep(10)
                
                cmd = [
                    aria2_path,
                    '-x', '16',
                    '-s', '16',
                    '-k', '2M',
                    '-o', filename,
                    '-d', str(temp_folder),
                    '--check-certificate=false',
                    '--retry-wait=5',
                    '--max-tries=5',
                    '--timeout=60',
                    '--connect-timeout=30',
                    '--max-file-not-found=5',
                    '--allow-overwrite=true',
                    '--auto-file-renaming=false',
                    '--continue=true',
                    item['download_url']
                ]
                
                self.log(f"Tentativa {attempt + 1}/{max_retries}: Baixando {filename[:50]}...")
                


                startupinfo = None
                creationflags = 0

                if sys.platform == 'win32':
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = subprocess.SW_HIDE
                    
                    creationflags = subprocess.CREATE_NO_WINDOW

                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                    encoding='utf-8',
                    errors='ignore',
                    startupinfo=startupinfo,
                    creationflags=creationflags
                )
                
                self.active_processes[item['id']] = process
                last_progress = self.download_progress.get(item['id'], 0)
                last_update_time = time.time()
                
                while True:
                    if self.stopped:
                        process.terminate()
                        del self.active_processes[item['id']]
                        return False
                    
                    if self.paused:
                        while self.paused and not self.stopped:
                            time.sleep(1)
                        if self.stopped:
                            process.terminate()
                            del self.active_processes[item['id']]
                            return False
                    
                    output = process.stdout.readline()
                    
                    if output == '' and process.poll() is not None:
                        break
                    
                    if output:
                        percent = self._parse_aria2_progress(output)
                        current_time = time.time()
                        
                        if percent > last_progress or current_time - last_update_time > 2:
                            last_progress = percent
                            last_update_time = current_time
                            self.progress(item['id'], percent, f"Baixando")
                    
                    time.sleep(0.1)
                
                stdout, stderr = process.communicate()
                del self.active_processes[item['id']]
                
                if process.returncode == 0 and temp_filepath.exists():
                    moved = self._move_from_temp_to_final(temp_filepath, final_filepath)
                    if moved and final_filepath.exists():
                        filesize = final_filepath.stat().st_size / (1024 * 1024)
                        item['status'] = 'completed'
                        item['file_size'] = f"{filesize:.2f} MB"
                        
                        self.progress(item['id'], 100, f"Pronto")
                        self.log(f"Download completo: {filename}")
                        return True
                    else:
                        error_msg = "Falha ao mover arquivo da pasta temporária"
                        self.log(f"Tentativa {attempt + 1} falhou: {error_msg}", "WARNING")
                else:
                    error_msg = ""
                    if stderr:
                        error_msg = stderr[:150]
                    elif stdout:
                        error_msg = stdout[:150]
                    
                    if not error_msg:
                        error_msg = "Erro desconhecido"
                    
                    if 'Unrecognized URI' in error_msg or 'unsupported protocol' in error_msg:
                        self.log(f"URL de download inválida ou expirada", "ERROR")
                        item['error'] = "URL inválida/Expirada"
                        return False
                    elif 'No such file or directory' in error_msg or 'Not Found' in error_msg:
                        self.log(f"Arquivo não encontrado no servidor", "ERROR")
                        item['error'] = "Arquivo não encontrado"
                        if attempt < max_retries - 1:
                            item['download_retry_count'] = item.get('download_retry_count', 0) + 1
                            item['last_retry_time'] = time.time()
                            time.sleep(10)
                            continue
                    else:
                        self.log(f"Tentativa {attempt + 1} falhou: {error_msg}", "WARNING")
                        
                        if attempt < max_retries - 1:
                            item['download_retry_count'] = item.get('download_retry_count', 0) + 1
                            item['last_retry_time'] = time.time()
                            wait_time = min(30, 5 * (attempt + 1))
                            self.log(f"Aguardando {wait_time} segundos antes de tentar novamente...", "INFO")
                            time.sleep(wait_time)
                            continue
            
            except subprocess.TimeoutExpired:
                self.log(f"Timeout na tentativa {attempt + 1}", "WARNING")
                if attempt < max_retries - 1:
                    time.sleep(10)
            except Exception as e:
                self.log(f"Erro na tentativa {attempt + 1}: {str(e)[:80]}", "ERROR")
                if attempt < max_retries - 1:
                    time.sleep(10)
        
        item['status'] = 'failed'
        if not item.get('error'):
            item['error'] = f"Falhou após {max_retries} tentativas"
        return False
    
    def _download_worker(self, item):
        item['status'] = 'downloading'
        self.downloading.append(item)
        self.save_database()
        
        self.progress(item['id'], 0, f"Iniciando download")
        
        success = self._download_with_retry(item, max_retries=5)
        
        if success:
            self.downloading.remove(item)
            self.completed_list.append(item)
            self.progress(item['id'], 100, f"Download completo")
        else:
            self.downloading.remove(item)
            self.failed_list.append(item)
            self.progress(item['id'], 0, f"Falhou")
            self.log(f"Erro no download: {item.get('error', 'Erro desconhecido')}", "ERROR")
        
        if self.pending_queue and not self.stopped and not self.paused:
            active_downloads = len(self.downloading)
            max_downloads = config.get_max_downloads()
            links_needed = max(0, max_downloads - active_downloads - len(self.download_queue))
            
            if links_needed > 0:
                self._generate_additional_links(links_needed, config.get_quality())
        
        self.save_database()

    def reset_state(self):
        self.stopped = False
        self.active_generators = 0
        
        self.log("Estado de geração resetado", "INFO")
    
    def process_queue(self):
        self.stopped = False
        
        self.log("Iniciando processamento da fila...")
        
        if not self.pending_queue:
            self.log("Fila vazia")
            return
        
        max_downloads = config.get_max_downloads()
        max_generators = min(config.get_max_links(), max_downloads)
        generator_threads = []
        
        self.active_generators = max_generators
        quality = config.get_quality()
        
        self.log(f"Gerando {len(self.pending_queue)} links ({max_generators} paralelo)...")
        
        for _ in range(max_generators):
            thread = threading.Thread(
                target=self._generator_worker,
                args=(quality,),
                daemon=True
            )
            thread.start()
            generator_threads.append(thread)
            time.sleep(0.5)
        
        for thread in generator_threads:
            try:
                thread.join(timeout=600)
            except:
                pass
        
        self.log(f"Links gerados: {len(self.download_queue)} prontos, {len(self.failed_list)} erros")
        
        if self.stopped:
            self.log("Processamento interrompido pelo usuário")
            return
        
        if not self.download_queue:
            self.log("Nenhum vídeo pronto para download")
            return
        
        max_downloads = config.get_max_downloads()
        self.log(f"Baixando {len(self.download_queue)} vídeos ({max_downloads} paralelo)...")
        
        download_threads = []
        items_to_download = self.download_queue.copy()
        
        while items_to_download and not self.stopped:
            if len(items_to_download) < max_downloads * 2 and self.pending_queue:
                self._generate_additional_links(max_downloads - len(items_to_download), quality)
                items_to_download = self.download_queue.copy()
            
            if len([t for t, _ in download_threads if t.is_alive()]) < max_downloads:
                item = items_to_download.pop(0)
                
                thread = threading.Thread(
                    target=self._download_worker,
                    args=(item,),
                    daemon=True
                )
                thread.start()
                download_threads.append((thread, item))
                
                time.sleep(1)
            else:
                time.sleep(0.5)
            
            download_threads = [(t, i) for t, i in download_threads if t.is_alive()]
        
        for thread, _ in download_threads:
            try:
                thread.join(timeout=1800)
            except:
                pass
        
        self.download_queue.clear()
        self.pending_queue.clear()
        self.downloading.clear()
        
        self.log(f"Processamento completo: {len(self.completed_list)} sucesso, {len(self.failed_list)} erros")
        self.save_database()
    
    def pause_downloads(self):
        self.paused = True
        self.log("Downloads pausados - aguardando para retomar")
    
    def resume_downloads(self):
        self.paused = False
        self.log("Downloads retomados")
    
    def stop_generation(self):
        self.stopped = True
        
        for item_id, process in list(self.active_processes.items()):
            item = self._find_item_by_id(item_id)
            if item and item.get('status') == 'processing':
                try:
                    process.terminate()
                    self.log(f"Processo de geração {item_id} terminado", "DEBUG")
                except:
                    pass
        
        self.log("Geração de links parada - downloads continuarão até terminar")
    
    def save_database(self):
        try:
            data = {
                'pending': self.pending_queue,
                'processing': self.processing_queue,
                'download_ready': self.download_queue,
                'downloading': self.downloading,
                'completed': self.completed_list,
                'failed': self.failed_list,
                'timestamp': datetime.now().isoformat()
            }
            
            with open(config.DATABASE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.log(f"Erro ao salvar database: {e}", "ERROR")
    
    def load_database(self):
        try:
            if config.DATABASE_FILE.exists():
                with open(config.DATABASE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.pending_queue = data.get('pending', [])
                    self.processing_queue = data.get('processing', [])
                    self.download_queue = data.get('download_ready', [])
                    self.downloading = data.get('downloading', [])
                    self.completed_list = data.get('completed', [])
                    self.failed_list = data.get('failed', [])
                    self.log(f"Database carregado: {len(self.pending_queue)} pendentes")
        except Exception as e:
            self.log(f"Erro ao carregar database: {e}", "ERROR")
