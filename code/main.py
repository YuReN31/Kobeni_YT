import sys
import os
from pathlib import Path

if sys.platform == 'win32':
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except:
        pass

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

def cleanup_old_logs():

    try:
        logs_dir = Path(__file__).parent / "logs"
        
        if not logs_dir.exists():
            logs_dir.mkdir(exist_ok=True)
            return 0
        
        log_files = list(logs_dir.glob("download_*.log"))
        
        if len(log_files) <= 30:
            return 0
        
        log_files.sort(key=lambda x: x.stat().st_mtime)
        
        files_to_delete = len(log_files) - 30
        

        files_removed = 0
        for i in range(files_to_delete):
            try:
                file_path = log_files[i]
                file_path.unlink()
                files_removed += 1
            except Exception:
                pass
        
        return files_removed
        
    except Exception:
        return 0

def main():
    print("\n" + "█"*60)
    print("█" + " "*58 + "█")
    print("█" + "Kobeni YT Downloader v3.0".center(58) + "█")
    print("█" + "By: YuReN31_".center(58) + "█")
    print("█" + "github.com/yuReN31".center(58) + "█")
    print("█" + " "*58 + "█")
    print("█"*60 + "\n")

    print("Verificando dependências...")
    
    try:
        __import__("customtkinter")
        print("✓ CustomTkinter")
    except ImportError:
        print("✗ CustomTkinter - Instale: pip install customtkinter")
        input("Pressione ENTER para sair...")
        sys.exit(1)
    
    try:
        __import__("requests")
        print("✓ Requests")
    except ImportError:
        print("✗ Requests - Instale: pip install requests")
        input("Pressione ENTER para sair...")
        sys.exit(1)
    
    print("\nVerificando aria2c...")
    
    try:
        from core.config import config
        if config.ARIA2C_PATH.exists():
            print("✓ aria2c encontrado")
        else:
            print("aria2c não encontrado")
            print(f"  Coloque aria2c.exe em: {config.ARIA2C_PATH}")
    except:
        print("Não foi possível verificar aria2c")
    
    print("\nIniciando interface gráfica...")
    
    try:
        cleanup_old_logs()
        
        from core.gui import run_gui
        run_gui()
    except Exception as e:
        print(f"\n✗ Erro ao iniciar: {e}")
        input("\nPressione ENTER para sair...")
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nAplicação interrompida")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Erro inesperado: {e}")
        input("\nPressione ENTER para sair...")

        sys.exit(1)
