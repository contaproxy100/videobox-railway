from flask import Flask, request, jsonify
import os
import uuid
import threading
import time
import sys
import subprocess
import json

app = Flask(__name__)

# CORS manual (sem dependências externas)
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# Diretórios
BASE_DIR = '/home/contavideostt700/video_downloader'
DOWNLOADS_DIR = os.path.join(BASE_DIR, 'downloads')
SCRIPT_PATH = os.path.join(BASE_DIR, 'universal_downloader_aac.py')

# Garantir que pasta downloads existe
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# Jobs em andamento
active_jobs = {}

@app.route('/api/health')
def health_check():
    """Health check da API"""
    script_exists = os.path.exists(SCRIPT_PATH)
    
    return jsonify({
        "status": "ok",
        "message": "VideoBox API Final - v6.0",
        "python_version": sys.version.split()[0],
        "script_found": script_exists,
        "script_path": SCRIPT_PATH if script_exists else "Not found",
        "active_jobs": len(active_jobs),
        "features": ["yt-dlp", "real_downloads", "universal_script"] if script_exists else ["yt-dlp", "real_downloads"]
    })

@app.route('/api/process', methods=['POST'])
def process_video():
    """Processar URL de vídeo"""
    try:
        data = request.get_json()
        if not data or 'url' not in data:
            return jsonify({"error": "URL não fornecida"}), 400
        
        url = data['url'].strip()
        if not url:
            return jsonify({"error": "URL vazia"}), 400
        
        # Gerar ID único para o job
        job_id = str(uuid.uuid4())[:8]
        
        # Registrar job
        active_jobs[job_id] = {
            "status": "processing",
            "url": url,
            "progress": 0,
            "created_at": time.time(),
            "files": []
        }
        
        # Iniciar processamento em thread separada
        thread = threading.Thread(target=process_video_worker, args=(job_id, url))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            "success": True,
            "job_id": job_id,
            "message": "Processamento iniciado",
            "status_url": f"/api/status/{job_id}"
        })
        
    except Exception as e:
        return jsonify({"error": f"Erro no processamento: {str(e)}"}), 500

def process_video_worker(job_id, url):
    """Worker para processar vídeo em background"""
    try:
        # Atualizar progresso
        active_jobs[job_id]["progress"] = 10
        active_jobs[job_id]["message"] = "Iniciando download..."
        
        # Tentar usar script universal primeiro
        if os.path.exists(SCRIPT_PATH):
            success = try_universal_script(job_id, url)
            if success:
                return
        
        # Fallback: usar yt-dlp diretamente
        success = try_ytdlp(job_id, url)
        
        if not success:
            active_jobs[job_id]["status"] = "error"
            active_jobs[job_id]["message"] = "Falha no download"
            
    except Exception as e:
        active_jobs[job_id]["status"] = "error"
        active_jobs[job_id]["message"] = f"Erro: {str(e)}"

def try_universal_script(job_id, url):
    """Tentar usar script universal"""
    try:
        active_jobs[job_id]["progress"] = 30
        active_jobs[job_id]["message"] = "Usando script universal..."
        
        # Criar pasta para este job
        job_dir = os.path.join(DOWNLOADS_DIR, job_id)
        os.makedirs(job_dir, exist_ok=True)
        
        # Executar script universal
        cmd = [sys.executable, SCRIPT_PATH, url, job_dir]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            # Sucesso - listar arquivos baixados
            files = []
            if os.path.exists(job_dir):
                for filename in os.listdir(job_dir):
                    if filename.endswith(('.mp4', '.webm', '.mkv', '.mp3', '.m4a', '.jpg', '.png')):
                        filepath = os.path.join(job_dir, filename)
                        size = os.path.getsize(filepath)
                        files.append({
                            "name": filename,
                            "size": format_size(size),
                            "download_url": f"/api/download/{job_id}/{filename}",
                            "type": get_file_type(filename)
                        })
            
            active_jobs[job_id]["status"] = "completed"
            active_jobs[job_id]["progress"] = 100
            active_jobs[job_id]["message"] = "Download concluído"
            active_jobs[job_id]["files"] = files
            return True
            
    except Exception as e:
        print(f"Erro no script universal: {e}")
    
    return False

def try_ytdlp(job_id, url):
    """Fallback usando yt-dlp"""
    try:
        active_jobs[job_id]["progress"] = 50
        active_jobs[job_id]["message"] = "Usando yt-dlp..."
        
        # Criar pasta para este job
        job_dir = os.path.join(DOWNLOADS_DIR, job_id)
        os.makedirs(job_dir, exist_ok=True)
        
        # Comando yt-dlp
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--format", "best[height<=1080]",
            "--output", os.path.join(job_dir, "%(title)s.%(ext)s"),
            "--no-playlist",
            url
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            # Listar arquivos baixados
            files = []
            if os.path.exists(job_dir):
                for filename in os.listdir(job_dir):
                    if filename.endswith(('.mp4', '.webm', '.mkv')):
                        filepath = os.path.join(job_dir, filename)
                        size = os.path.getsize(filepath)
                        files.append({
                            "name": filename,
                            "size": format_size(size),
                            "download_url": f"/api/download/{job_id}/{filename}",
                            "type": "video"
                        })
            
            active_jobs[job_id]["status"] = "completed"
            active_jobs[job_id]["progress"] = 100
            active_jobs[job_id]["message"] = "Download concluído com yt-dlp"
            active_jobs[job_id]["files"] = files
            return True
            
    except Exception as e:
        print(f"Erro no yt-dlp: {e}")
    
    return False

@app.route('/api/status/<job_id>')
def get_status(job_id):
    """Verificar status do job"""
    if job_id not in active_jobs:
        return jsonify({"error": "Job não encontrado"}), 404
    
    job = active_jobs[job_id]
    
    # Limpar jobs antigos (mais de 1 hora)
    if time.time() - job["created_at"] > 3600:
        cleanup_job(job_id)
        return jsonify({"error": "Job expirado"}), 404
    
    return jsonify({
        "job_id": job_id,
        "status": job["status"],
        "progress": job["progress"],
        "message": job.get("message", ""),
        "completed": job["status"] in ["completed", "error"],
        "files": job.get("files", [])
    })

@app.route('/api/download/<job_id>/<filename>')
def download_file(job_id, filename):
    """Download de arquivo"""
    try:
        if job_id not in active_jobs:
            return jsonify({"error": "Job não encontrado"}), 404
        
        filepath = os.path.join(DOWNLOADS_DIR, job_id, filename)
        if not os.path.exists(filepath):
            return jsonify({"error": "Arquivo não encontrado"}), 404
        
        return send_file(filepath, as_attachment=True)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def cleanup_job(job_id):
    """Limpar arquivos do job"""
    try:
        if job_id in active_jobs:
            del active_jobs[job_id]
        
        job_dir = os.path.join(DOWNLOADS_DIR, job_id)
        if os.path.exists(job_dir):
            import shutil
            shutil.rmtree(job_dir)
    except:
        pass

def format_size(bytes_size):
    """Formatar tamanho em bytes"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} TB"

def get_file_type(filename):
    """Determinar tipo do arquivo"""
    ext = filename.lower().split('.')[-1]
    if ext in ['mp4', 'webm', 'mkv', 'avi']:
        return 'video'
    elif ext in ['mp3', 'm4a', 'wav', 'flac']:
        return 'audio'
    elif ext in ['jpg', 'jpeg', 'png', 'gif']:
        return 'image'
    else:
        return 'unknown'

# Para PythonAnywhere
application = app

if __name__ == '__main__':
    app.run(debug=True)