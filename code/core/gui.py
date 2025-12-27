import customtkinter as ctk
from tkinter import filedialog, messagebox
import tkinter as tk
from pathlib import Path
import threading
from datetime import datetime
import webbrowser
import subprocess


import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import config
from core.downloader import DownloadManager
from PIL import Image
import os

class YouTubeDownloaderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Kobeni - YT Downloader v3.0")
        self.root.geometry("1100x750")
        
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        try:
            self.root.iconbitmap("app_icon.ico")
        except:
            try:
                self.root.iconbitmap(str(Path(__file__).parent.parent / "app_icon.ico"))
            except Exception as e:
                self.log_message(f"Ícone não encontrado: {e}", "WARNING")
        
        self.manager = None
        self.download_thread = None
        self.current_list_type = "pending"
        self.is_downloading = False
        self.list_box = None
        
        self.setup_ui()
        self.setup_manager()
        self.refresh_periodically()
    
    def open_link(self, url):
        webbrowser.open(url)
        self.log_message(f"Abrindo: {url}")
    
    def setup_manager(self):
        self.manager = DownloadManager(
            log_callback=self.log_message,
            progress_callback=self.update_item_progress
        )
        self.manager.load_database()
        self.log_message("Sistema carregado")
        if self.manager.pending_queue:
            self.log_message(f"Vídeos pendentes: {len(self.manager.pending_queue)}")
        self.refresh_lists()
    
    def setup_ui(self):
        top_frame = ctk.CTkFrame(self.root)
        top_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(top_frame, text="URL do YouTube:", font=("Arial", 11)).pack(side="left", padx=5)
        
        self.url_input = ctk.CTkEntry(
            top_frame, 
            placeholder_text="Cole a URL do YouTube aqui",
            width=400
        )
        self.url_input.pack(side="left", padx=5, fill="x", expand=True)

        self.url_input.bind("<Return>", lambda event: self.add_url())
        self.url_input.bind("<KP_Enter>", lambda event: self.add_url()) 
        
        ctk.CTkButton(
            top_frame, 
            text="Adicionar",
            command=self.add_url,
            width=140,
            fg_color=("green", "darkgreen")
        ).pack(side="left")
        
        opts_frame = ctk.CTkFrame(self.root)
        opts_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(opts_frame, text="Qualidade:", font=("Arial", 10)).pack(side="left", padx=5)
        self.quality_var = ctk.StringVar(value=config.get_quality())
        ctk.CTkOptionMenu(
            opts_frame,
            variable=self.quality_var,
            values=list(config.QUALITIES.keys()),
            width=80
        ).pack(side="left", padx=5)
        
        ctk.CTkButton(
            opts_frame,
            text="Configurações",
            command=self.show_settings,
            width=140
        ).pack(side="right")
        
        tabs_frame = ctk.CTkFrame(self.root)
        tabs_frame.pack(fill="x", padx=10, pady=5)
        
        self.tab_buttons = {}
        tabs_info = [
            ("pending", "NA FILA"),
            ("downloading", "BAIXANDO"),
            ("completed", "PRONTOS"),
            ("failed", "COM ERRO")
        ]
        
        for tab_id, tab_name in tabs_info:
            btn = ctk.CTkButton(
                tabs_frame,
                text=tab_name,
                command=lambda t=tab_id: self.switch_tab(t),
                width=110,
                font=("Arial", 10)
            )
            btn.pack(side="left", padx=5)
            self.tab_buttons[tab_id] = btn
        
        main_frame = ctk.CTkFrame(self.root)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        left_frame = ctk.CTkFrame(main_frame)
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 5))
        
        self.tab_label = ctk.CTkLabel(left_frame, text="NA FILA", font=("Arial", 12, "bold"))
        self.tab_label.pack(fill="x", pady=(0, 5))
        
        list_scroll = ctk.CTkFrame(left_frame)
        list_scroll.pack(fill="both", expand=True)
        
        scrollbar = tk.Scrollbar(list_scroll)
        scrollbar.pack(side="right", fill="y")
        
        self.list_box = tk.Listbox(
            list_scroll,
            bg="#212121",
            fg="#FFFFFF",
            font=("Courier", 9),
            yscrollcommand=scrollbar.set,
            selectmode=tk.SINGLE,
            selectbackground="#2a2a2a",
            selectforeground="#FFFFFF"
        )
        self.list_box.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.list_box.yview)
        
        self.list_box.bind("<Configure>", self.on_list_resize)
        self.list_box.bind("<Button-1>", self.on_list_click)
        self.list_box.bind("<Double-Button-1>", lambda e: self.copy_selected_url())
        
        list_buttons_frame = ctk.CTkFrame(left_frame)
        list_buttons_frame.pack(fill="x", pady=(5, 0))
        
        copy_btn = ctk.CTkButton(
            list_buttons_frame,
            text="Copiar",
            command=self.copy_selected_url,
            width=90
        )
        copy_btn.pack(side="left", padx=2)
        
        self.remove_btn = ctk.CTkButton(
            list_buttons_frame,
            text="Remover",
            command=self.remove_selected,
            width=90,
            fg_color=("red", "darkred")
        )
        self.remove_btn.pack(side="left", padx=2)
        
        self.clear_list_btn = ctk.CTkButton(
            list_buttons_frame,
            text="Limpar Tudo",
            command=self.clear_current_list,
            width=100,
            fg_color=("orange", "darkorange")
        )
        self.clear_list_btn.pack(side="left", padx=2)
        
        right_frame = ctk.CTkFrame(main_frame)
        right_frame.pack(side="right", fill="both", expand=True, padx=(5, 0))
        
        ctk.CTkLabel(right_frame, text="LOG", font=("Arial", 12, "bold")).pack(fill="x", pady=(0, 5))
        
        log_scroll = ctk.CTkFrame(right_frame)
        log_scroll.pack(fill="both", expand=True)
        
        log_scrollbar = tk.Scrollbar(log_scroll)
        log_scrollbar.pack(side="right", fill="y")
        
        self.log_text = tk.Text(
            log_scroll,
            bg="#212121",
            fg="#00FF00",
            font=("Courier", 8),
            yscrollcommand=log_scrollbar.set,
            state="normal"
        )
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scrollbar.config(command=self.log_text.yview)
        
        control_frame = ctk.CTkFrame(self.root)
        control_frame.pack(fill="x", padx=10, pady=10)
        
        self.start_btn = ctk.CTkButton(
            control_frame,
            text="INICIAR",
            command=self.start_download,
            width=100,
            fg_color=("green", "darkgreen"),
            font=("Arial", 11)
        )
        self.start_btn.pack(side="left", padx=5)
        
        self.pause_btn = ctk.CTkButton(
            control_frame,
            text="PAUSAR DOWNLOADS",
            command=self.pause_download,
            width=140,
            state="disabled"
        )
        self.pause_btn.pack(side="left", padx=5)
        
        self.stop_btn = ctk.CTkButton(
            control_frame,
            text="PARAR GERAÇÃO",
            command=self.stop_download,
            width=140,
            fg_color=("red", "darkred"),
            state="disabled"
        )
        self.stop_btn.pack(side="left", padx=5)
        
        ctk.CTkButton(
            control_frame,
            text="LIMPAR LOG",
            command=self.clear_log,
            width=140
        ).pack(side="right")
        
        self.status_label = ctk.CTkLabel(
            control_frame,
            text="Status: Pronto",
            font=("Arial", 10),
            text_color="yellow"
        )
        self.status_label.pack(side="right", padx=5)
        
        footer_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        footer_frame.pack(pady=5)
        
        ctk.CTkLabel(
            footer_frame,
            text="Este software pode violar os Termos de Serviço do YouTube. O desenvolvedor não se responsabiliza pelo uso indevido.",
            font=("Arial", 10, "bold"),
            text_color="orange"
        ).pack()
        
        links_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        links_frame.pack(pady=2)
        
        github_label = tk.Label(
            links_frame,
            text="GitHub",
            font=("Arial", 9),
            fg="lightblue",
            bg="#2b2b2b",
            cursor="hand2"
        )
        github_label.pack(side="left", padx=5)
        github_label.bind("<Button-1>", lambda e: self.open_link("https://github.com/YuReN31"))
        
        tk.Label(
            links_frame,
            text="|",
            font=("Arial", 9),
            fg="gray",
            bg="#2b2b2b"
        ).pack(side="left", padx=5)
        
        facebook_label = tk.Label(
            links_frame,
            text="Facebook",
            font=("Arial", 9),
            fg="lightblue",
            bg="#2b2b2b",
            cursor="hand2"
        )
        facebook_label.pack(side="left", padx=5)
        facebook_label.bind("<Button-1>", lambda e: self.open_link("https://www.facebook.com/yuren.daniel.1"))
        
        ctk.CTkLabel(
            self.root,
            text="Kobeni - YT Downloader v3.0 | Desenvolvido por: YuReN31_",
            font=("Arial", 9, "italic"),
            text_color="gray"
        ).pack(pady=2)
        
        self.switch_tab("pending")
    
    def on_list_resize(self, event):
        if event.widget == self.list_box:
            if hasattr(self, '_resize_timer'):
                self.root.after_cancel(self._resize_timer)
            
            self._resize_timer = self.root.after(200, self.refresh_lists)
    
    def on_list_click(self, event):
        index = self.list_box.nearest(event.y)
        
        if index >= 0:
            item_text = self.list_box.get(index)
            
            if self.current_list_type != "downloading" and "[×]" in item_text:
                bbox = self.list_box.bbox(index)
                if bbox:
                    char_width = 7 
                    text_width = len(item_text) * char_width
                    x_end = bbox[0] + text_width
                    x_start = x_end - 25 
                    
                    if x_start <= event.x <= x_end:
                        self.remove_item_by_index(index)
                        return
            
            self.list_box.selection_clear(0, tk.END)
            self.list_box.selection_set(index)
    
    def remove_item_by_index(self, index):
        queue_map = {
            "pending": self.manager.pending_queue,
            "downloading": self.manager.downloading,
            "completed": self.manager.completed_list,
            "failed": self.manager.failed_list
        }
        
        queue = queue_map.get(self.current_list_type, [])
        
        if index < len(queue):
            item = queue[index]
            
            if messagebox.askyesno("Confirmar", f"Remover '{item['title'][:30]}...'?"):
                queue.pop(index)
                self.manager.save_database()
                self.refresh_lists()
                self.log_message(f"Removido: {item['title'][:50]}...")
        else:
            self.log_message("Erro: Item não encontrado", "ERROR")
    
    def switch_tab(self, tab_id):
        self.current_list_type = tab_id
        
        for btn_id, btn in self.tab_buttons.items():
            if btn_id == tab_id:
                btn.configure(fg_color=("blue", "darkblue"))
            else:
                btn.configure(fg_color=("gray40", "gray30"))
        
        labels = {
            "pending": "NA FILA",
            "downloading": "BAIXANDO",
            "completed": "PRONTOS",
            "failed": "COM ERRO"
        }
        self.tab_label.configure(text=labels.get(tab_id, "LISTA"))
        
        self.refresh_lists()
    
    def refresh_lists(self):
        if not self.list_box:
            return
            
        self.list_box.delete(0, tk.END)
        
        if not self.manager:
            self.list_box.insert(tk.END, f"[Erro: Manager não inicializado]")
            return
        
        queue_map = {
            "pending": self.manager.pending_queue,
            "downloading": self.manager.downloading,
            "completed": self.manager.completed_list,
            "failed": self.manager.failed_list
        }
        
        queue = queue_map.get(self.current_list_type)
        
        if queue is None:
            self.list_box.insert(tk.END, f"[Erro: Lista não encontrada]")
            return
        
        if not queue:
            self.list_box.insert(tk.END, f"[Vazio]")
            return
        
        try:
            list_width_px = self.list_box.winfo_width()
            
            if list_width_px < 10:
                list_width_px = 600
                
            char_width_px = 7 
            max_chars = max(20, list_width_px // char_width_px - 8)
        except:
            max_chars = 80
        
        for idx, item in enumerate(queue):
            quality = item.get('quality', '?')
            size = item.get('file_size', '0 MB')
            title = item.get('title', item.get('youtube_url', '')[:40])
            
            if self.current_list_type == "completed":
                base_text = f"{idx+1}.  [{quality}] - {size}"
                available_chars = max_chars - len(base_text)
                
                if available_chars > 10:
                    if len(title) > available_chars:
                        title_short = title[:available_chars-3] + "..."
                    else:
                        title_short = title
                    text = f"{idx+1}. {title_short} [{quality}] - {size}"
                else:
                    text = f"{idx+1}. [{quality}] - {size}"
                
            elif self.current_list_type == "failed":
                error = item.get('error', 'Erro')
                error_short = error[:15] if len(error) > 15 else error
                base_text = f"{idx+1}.  - ERRO: {error_short}"
                available_chars = max_chars - len(base_text)
                
                if available_chars > 10:
                    if len(title) > available_chars:
                        title_short = title[:available_chars-3] + "..."
                    else:
                        title_short = title
                    text = f"{idx+1}. {title_short} - ERRO: {error_short}"
                else:
                    text = f"{idx+1}. [{quality}] - ERRO: {error_short}"
                
            elif self.current_list_type == "downloading":
                progress = self.manager.download_progress.get(item['id'], 0)
                
                if max_chars < 40:
                    bar_width = 8
                    prefix_len = len(f"{idx+1}.  ") + 6
                    available_for_title = max_chars - prefix_len - bar_width
                elif max_chars < 60:
                    bar_width = 12
                    prefix_len = len(f"{idx+1}.  ") + 6
                    available_for_title = max_chars - prefix_len - bar_width
                else:
                    bar_width = 15
                    prefix_len = len(f"{idx+1}.  ") + 6
                    available_for_title = max_chars - prefix_len - bar_width
                
                available_for_title = max(5, available_for_title)
                
                if len(title) > available_for_title:
                    title_short = title[:available_for_title-3] + "..."
                else:
                    title_short = title
                
                filled = int(bar_width * progress / 100)
                bar = '[' + '█' * filled + ' ' * (bar_width - filled) + ']'
                progress_text = f"{progress:3d}%{bar}"
                
                text = f"{idx+1}. {title_short} {progress_text}"
                
            else:
                base_text = f"{idx+1}.  [{quality}]"
                available_chars = max_chars - len(base_text)
                
                if available_chars > 10:
                    if len(title) > available_chars:
                        title_short = title[:available_chars-3] + "..."
                    else:
                        title_short = title
                    text = f"{idx+1}. {title_short} [{quality}]"
                else:
                    text = f"{idx+1}. [{quality}]"
            
            if self.current_list_type != "downloading":
                text = f"{text}  [×]" 
            
            self.list_box.insert(tk.END, text)
    
    def copy_selected_url(self):
        selection = self.list_box.curselection()
        if not selection:
            messagebox.showinfo("Info", "Selecione um item primeiro")
            return
        
        idx = selection[0]
        queue_map = {
            "pending": self.manager.pending_queue,
            "downloading": self.manager.downloading,
            "completed": self.manager.completed_list,
            "failed": self.manager.failed_list
        }
        
        queue = queue_map.get(self.current_list_type, [])
        if idx < len(queue):
            item = queue[idx]
            
            copy_text = item.get('download_url', item.get('title', ''))
            if copy_text == "In Processing..." or not copy_text:
                copy_text = item.get('youtube_url', item.get('title', ''))
            
            self.root.clipboard_clear()
            self.root.clipboard_append(copy_text)
            
            self.log_message(f"Copiado: {copy_text[:50]}...")
    
    def remove_selected(self):
        selection = self.list_box.curselection()
        if not selection:
            messagebox.showwarning("Aviso", "Selecione um item primeiro")
            return
        
        idx = selection[0]
        self.remove_item_by_index(idx)
    
    def clear_current_list(self):
        if not messagebox.askyesno("Confirmar", f"Limpar TODOS os itens da lista {self.current_list_type}?"):
            return
        
        queue_map = {
            "pending": self.manager.pending_queue,
            "downloading": self.manager.downloading,
            "completed": self.manager.completed_list,
            "failed": self.manager.failed_list
        }
        
        queue = queue_map.get(self.current_list_type, [])
        
        if queue:
            count = len(queue)
            queue.clear()
            self.manager.save_database()
            self.refresh_lists()
            self.log_message(f"Lista {self.current_list_type} limpa ({count} itens removidos)")
        else:
            self.log_message(f"Lista {self.current_list_type} já está vazia")
    
    def add_url(self):
        url = self.url_input.get().strip()
        if not url:
            messagebox.showwarning("Aviso", "Cole uma URL válida")
            return
        
        if "youtube.com" not in url and "youtu.be" not in url:
            messagebox.showerror("Erro", "URL não é do YouTube")
            return
        
        quality = self.quality_var.get()
        self.manager.add_to_queue(url, quality)
        self.url_input.delete(0, tk.END)
        
        self.refresh_lists()
        self.switch_tab("pending")
            

    
    def start_download(self):
        if not self.manager.pending_queue:
            messagebox.showwarning("Aviso", "Nenhum vídeo na fila")
            return
        
        if self.is_downloading:
            messagebox.showwarning("Aviso", "Já está processando")
            return
        
        self.is_downloading = True
        self.start_btn.configure(state="disabled")
        self.pause_btn.configure(state="normal")
        self.stop_btn.configure(state="normal")
        self.status_label.configure(text="Status: Processando...", text_color="orange")
        
        self.download_thread = threading.Thread(
            target=self._process_and_reset,
            daemon=True
        )
        self.download_thread.start()
        
        self.log_message("=== INICIANDO PROCESSAMENTO ===")
    
    def _process_and_reset(self):
        try:
            self.manager.process_queue()
        finally:
            self.is_downloading = False
            self.start_btn.configure(state="normal")
            self.pause_btn.configure(state="disabled")
            self.stop_btn.configure(state="disabled")
            self.status_label.configure(text="Status: Pronto", text_color="yellow")
            self.refresh_lists()
            self.log_message("=== PROCESSAMENTO FINALIZADO ===")
            self.pause_btn.configure(text="PAUSAR DOWNLOADS", command=self.pause_download)
    
    def pause_download(self):
        if self.manager:
            self.manager.pause_downloads()
            self.status_label.configure(text="Status: Downloads pausados", text_color="yellow")
            self.pause_btn.configure(text="RETOMAR DOWNLOADS", command=self.resume_download)
            self.log_message("Downloads pausados")
    
    def resume_download(self):
        if self.manager:
            self.manager.resume_downloads()
            self.status_label.configure(text="Status: Processando...", text_color="orange")
            self.pause_btn.configure(text="PAUSAR DOWNLOADS", command=self.pause_download)
            self.log_message("Downloads retomados")
    
    def stop_download(self):
        if self.manager:
            self.manager.stop_generation()
            self.status_label.configure(text="Status: Parando geração...", text_color="red")
            self.log_message("Parando geração de links...")
            self.pause_btn.configure(text="PAUSAR DOWNLOADS", command=self.pause_download)
    
    def update_item_progress(self, item_id, percent, status):
        if self.current_list_type == "downloading":
            self.refresh_lists()
    
    def log_message(self, msg, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        if config.DEBUG_MODE or level in ["ERROR", "WARNING", "INFO"]:
            log_entry = f"[{timestamp}] {msg}\n"
            self.log_text.insert(tk.END, log_entry)
            self.log_text.see(tk.END)
    
    def clear_log(self):
        self.log_text.delete(1.0, tk.END)
        self.log_message("Log limpo")
    
    def refresh_periodically(self):
        try:
            if not self.is_downloading:
                self.refresh_lists()
        except:
            pass
        self.root.after(1000, self.refresh_periodically)
    
    def show_settings(self):
        settings_window = ctk.CTkToplevel(self.root)
        settings_window.title("Configurações")
        settings_window.geometry("450x390") 
        settings_window.resizable(False, False)

        
        settings_window.transient(self.root)  
        settings_window.grab_set()
        
        def center_window(window):
            window.update_idletasks() 
            
            screen_width = window.winfo_screenwidth()
            screen_height = window.winfo_screenheight()

            window_width = window.winfo_width()
            window_height = window.winfo_height()
            
            x = (screen_width - window_width) // 2
            y = (screen_height - window_height) // 2
            
            if self.root.winfo_exists():
                parent_x = self.root.winfo_x()
                parent_y = self.root.winfo_y()
                parent_width = self.root.winfo_width()
                parent_height = self.root.winfo_height()
                
                x = parent_x + (parent_width - window_width) // 2
                y = parent_y + (parent_height - window_height) // 2
                
                x = max(0, min(x, screen_width - window_width))
                y = max(0, min(y, screen_height - window_height))
            
            window.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        def on_closing():
            settings_window.grab_release() 
            settings_window.destroy()
        
        settings_window.protocol("WM_DELETE_WINDOW", on_closing)
        
        settings_window.lift()  
        settings_window.focus_force()  
        
        settings_window.after(100, lambda: center_window(settings_window))
        
        def open_help():
            help_file = Path(__file__).parent.parent / "ajuda.txt"
            if help_file.exists():
                try:
                    import platform
                    if platform.system() == 'Windows':
                        os.startfile(str(help_file))
                    elif platform.system() == 'Darwin':
                        subprocess.run(['open', str(help_file)])
                    else:
                        subprocess.run(['xdg-open', str(help_file)])
                except Exception as e:
                    self.log_message(f"Erro ao abrir arquivo de ajuda: {e}", "ERROR")
            else:
                self.log_message("Arquivo ajuda.txt não encontrado", "ERROR")
        
        header_frame = ctk.CTkFrame(settings_window)
        header_frame.pack(fill="x", padx=15, pady=(15, 0))
        
        ctk.CTkButton(
            header_frame,
            text="?",
            command=open_help,
            width=30,
            height=30,
            font=("Arial", 14, "bold"),
            fg_color=("gray70", "gray30")
        ).pack(side="right")
        
        settings = config.load_settings()
        
        main_frame = ctk.CTkFrame(settings_window)
        main_frame.pack(fill="both", expand=True, padx=15, pady=(5, 15))
        
        row = 0
        
        ctk.CTkLabel(main_frame, text="Links gerados em paralelo:", font=("Arial", 10)).grid(
            row=row, column=0, sticky="w", padx=5, pady=(0, 2))
        row += 1
        
        links_var = ctk.StringVar(value=str(settings.get('max_simultaneous_links', 2)))
        links_menu = ctk.CTkOptionMenu(main_frame, variable=links_var, values=["1", "2", "3", "4"], width=150)
        links_menu.grid(row=row, column=0, sticky="w", padx=5, pady=(0, 5))
        
        ctk.CTkLabel(main_frame, text="(Recomendo 2)", font=("Arial", 12), text_color="gray").grid(
            row=row, column=1, sticky="w", padx=5, pady=(0, 5))
        row += 1
        
        ctk.CTkLabel(main_frame, text="Vídeos baixados em paralelo:", font=("Arial", 10)).grid(
            row=row, column=0, sticky="w", padx=5, pady=(5, 2))
        row += 1
        
        downloads_var = ctk.StringVar(value=str(settings.get('max_simultaneous_downloads', 2)))
        downloads_menu = ctk.CTkOptionMenu(main_frame, variable=downloads_var, values=["1", "2", "3", "4"], width=150)
        downloads_menu.grid(row=row, column=0, sticky="w", padx=5, pady=(0, 5))

        ctk.CTkLabel(main_frame, text="(Recomendo 4, 2 caso tenho uma net ruim)", font=("Arial", 12), text_color="gray").grid(
            row=row, column=1, sticky="w", padx=5, pady=(0, 5))
        row += 1
        
        ctk.CTkLabel(main_frame, text="Conexões aria2 por arquivo:", font=("Arial", 10)).grid(
            row=row, column=0, sticky="w", padx=5, pady=(5, 2))
        row += 1
        
        aria2_var = ctk.StringVar(value=str(settings.get('aria2_connections', 8)))
        aria2_menu = ctk.CTkOptionMenu(main_frame, variable=aria2_var, values=["1", "2", "4", "8", "16"], width=150)
        aria2_menu.grid(row=row, column=0, sticky="w", padx=5, pady=(0, 5))
        
        ctk.CTkLabel(main_frame, text="(Recomendo 8)", font=("Arial", 12), text_color="gray").grid(
            row=row, column=1, sticky="w", padx=5, pady=(0, 5))
        row += 1
        
        ctk.CTkLabel(main_frame, text="Pasta de Downloads:", font=("Arial", 10)).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=5, pady=(5, 2))
        row += 1
        
        folder_var = ctk.StringVar(value=settings.get('download_folder', ''))
        folder_frame = ctk.CTkFrame(main_frame)
        folder_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=5, pady=(0, 5))
        folder_frame.grid_columnconfigure(0, weight=1)
        
        folder_entry = ctk.CTkEntry(folder_frame, textvariable=folder_var)
        folder_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        def browse_folder():
            folder = filedialog.askdirectory(title="Selecione a pasta de downloads")
            if folder:
                folder_var.set(folder)
        
        ctk.CTkButton(folder_frame, text="...", command=browse_folder, width=40).pack(side="right")
        row += 1
        
        def save():
            settings['max_simultaneous_links'] = int(links_var.get())
            settings['max_simultaneous_downloads'] = int(downloads_var.get())
            settings['aria2_connections'] = int(aria2_var.get())
            settings['download_folder'] = folder_var.get()
            config.save_settings(settings)
            self.log_message("Configurações salvas")
            settings_window.destroy()
        
        ctk.CTkButton(
            main_frame,
            text="SALVAR",
            command=save,
            width=200,
            height=35,
            fg_color=("green", "darkgreen"),
            font=("Arial", 11, "bold")
        ).grid(row=row, column=0, columnspan=2, pady=(20, 0), sticky="n")
        
        main_frame.grid_rowconfigure(row, weight=1) 
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_columnconfigure(1, weight=1)
    
    def start_download(self):
        if not self.manager.pending_queue:
            messagebox.showwarning("Aviso", "Nenhum vídeo na fila")
            return
        
        if self.is_downloading:
            messagebox.showwarning("Aviso", "Já está processando")
            return
        
        self.is_downloading = True
        self.start_btn.configure(state="disabled")
        self.pause_btn.configure(state="normal")
        self.stop_btn.configure(state="normal")
        self.status_label.configure(text="Status: Processando...", text_color="orange")
        
        self.download_thread = threading.Thread(
            target=self._process_and_reset,
            daemon=True
        )
        self.download_thread.start()
        
        self.log_message("=== INICIANDO PROCESSAMENTO ===")
    
    def _process_and_reset(self):
        try:
            self.manager.process_queue()
        finally:
            self.is_downloading = False
            self.start_btn.configure(state="normal")
            self.pause_btn.configure(state="disabled")
            self.stop_btn.configure(state="disabled")
            self.status_label.configure(text="Status: Pronto", text_color="yellow")
            self.refresh_lists()
            self.log_message("=== PROCESSAMENTO FINALIZADO ===")
            self.pause_btn.configure(text="PAUSAR DOWNLOADS", command=self.pause_download)
    
    def pause_download(self):
        if self.manager:
            self.manager.pause_downloads()
            self.status_label.configure(text="Status: Downloads pausados", text_color="yellow")
            self.pause_btn.configure(text="RETOMAR DOWNLOADS", command=self.resume_download)
            self.log_message("Downloads pausados")
    
    def resume_download(self):
        if self.manager:
            self.manager.resume_downloads()
            self.status_label.configure(text="Status: Processando...", text_color="orange")
            self.pause_btn.configure(text="PAUSAR DOWNLOADS", command=self.pause_download)
            self.log_message("Downloads retomados")
    
    def stop_download(self):
        if self.manager:
            self.manager.stop_generation()
            self.status_label.configure(text="Status: Parando geração...", text_color="red")
            self.log_message("Parando geração de links...")
            self.pause_btn.configure(text="PAUSAR DOWNLOADS", command=self.pause_download)
    
    def update_item_progress(self, item_id, percent, status):
        if self.current_list_type == "downloading":
            self.refresh_lists()
    
    def log_message(self, msg, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        if config.DEBUG_MODE or level in ["ERROR", "WARNING", "INFO"]:
            log_entry = f"[{timestamp}] {msg}\n"
            self.log_text.insert(tk.END, log_entry)
            self.log_text.see(tk.END)
    
    def clear_log(self):
        self.log_text.delete(1.0, tk.END)
        self.log_message("Log limpo")
    
    def refresh_periodically(self):
        try:
            if not self.is_downloading:
                self.refresh_lists()
        except:
            pass
        self.root.after(1000, self.refresh_periodically)

def run_gui():
    root = ctk.CTk()
    app = YouTubeDownloaderGUI(root)
    root.mainloop()

if __name__ == "__main__":
    run_gui()