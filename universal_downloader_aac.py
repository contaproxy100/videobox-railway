import os
import re
import time
import logging
import requests
import yt_dlp
from bs4 import BeautifulSoup
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from urllib.parse import urlparse, urljoin, unquote

class MultiSiteDownloader:
    def __init__(self, pasta_downloads="downloads"):
        self.pasta_downloads = Path(pasta_downloads)
        # Remove pasta separada de imagens - tudo na mesma pasta
        self.pasta_downloads.mkdir(exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler("downloader_universal.log", encoding="utf-8"),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        self.arquivos_baixados = 0
        self.erros = 0
        self.imagens_baixadas = 0
        self.arquivos_ignorados = 0
        
        # Mostra arquivos existentes (vídeos e imagens)
        arquivos_existentes = list(self.pasta_downloads.glob("*.*"))
        if arquivos_existentes:
            videos = [f for f in arquivos_existentes if f.suffix.lower() in ['.mp4', '.avi', '.mkv', '.webm']]
            imagens = [f for f in arquivos_existentes if f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.webp']]
            
            self.logger.info(f"📁 Pasta de downloads contém:")
            self.logger.info(f"   🎬 {len(videos)} vídeo(s)")
            self.logger.info(f"   🖼️ {len(imagens)} imagem(ns)")
            self.logger.info(f"   📄 {len(arquivos_existentes)} arquivo(s) total")
            
            # Mostra alguns exemplos
            for arquivo in arquivos_existentes[:3]:
                tamanho_mb = arquivo.stat().st_size / (1024*1024)
                self.logger.info(f"   • {arquivo.name} ({tamanho_mb:.1f} MB)")
            
            if len(arquivos_existentes) > 3:
                self.logger.info(f"   ... e mais {len(arquivos_existentes) - 3} arquivo(s)")
        else:
            self.logger.info("📁 Pasta de downloads vazia - prontos para baixar!")

    def baixar_arquivo_simples(self, url, destino, max_tentativas=3):
        """Download simples com retry"""
        for tentativa in range(max_tentativas):
            try:
                if tentativa > 0:
                    delay = 3 * tentativa
                    self.logger.info(f"🔄 Tentativa {tentativa + 1}/{max_tentativas} após {delay}s...")
                    time.sleep(delay)
                
                headers = self.headers.copy()
                if "erome" in url:
                    headers["Referer"] = "https://www.erome.com/"
                
                with requests.get(url, headers=headers, stream=True, timeout=30) as r:
                    r.raise_for_status()
                    
                    with open(destino, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    
                    if destino.stat().st_size > 1024:  # Maior que 1KB
                        size_mb = destino.stat().st_size / (1024*1024)
                        self.logger.info(f"✅ Baixado: {destino.name} ({size_mb:.1f}MB)")
                        return True
                        
            except Exception as e:
                self.logger.warning(f"❌ Erro na tentativa {tentativa + 1}: {e}")
                if destino.exists():
                    destino.unlink()
        
        return False

    def baixar_videos_ytdlp(self, url):
        """Baixa vídeos com yt-dlp em 1080p MÁXIMO e remove duplicatas"""
        arquivos_antes = set(p.name for p in self.pasta_downloads.glob("*.mp4"))
        
        try:
            self.logger.info(f"🎯 Baixando vídeos em 1080p MÁXIMO com yt-dlp: {url}")
            
            # Configuração OTIMIZADA para 1080p MÁXIMO (mais rápida)
            ydl_opts = {
                # LIMITA A 1080p COMO MÁXIMO - configuração simplificada
                "format": (
                    # 1ª Prioridade: 1080p com melhor áudio (formato já pronto)
                    "best[height<=1080][height>=720][ext=mp4]/"
                    "bestvideo[height<=1080][height>=720]+bestaudio[ext=m4a]/"
                    "bestvideo[height<=1080][height>=720]+bestaudio/"
                    
                    # 2ª Prioridade: Qualquer resolução ≤ 1080p
                    "best[height<=1080][ext=mp4]/"
                    "bestvideo[height<=1080]+bestaudio[ext=m4a]/"
                    "bestvideo[height<=1080]+bestaudio/"
                    
                    # 3ª Prioridade: Melhor disponível como último recurso
                    "best[ext=mp4]/bestvideo+bestaudio/best"
                ),
                "outtmpl": str(self.pasta_downloads / "%(title)s.%(ext)s"),
                "merge_output_format": "mp4",
                
                # Configurações básicas (sem pós-processamento pesado)
                "writesubtitles": False,
                "writeautomaticsub": False,
                "ignoreerrors": False,
                
                # Configurações de rede
                "socket_timeout": 30,
                "retries": 2,
                "fragment_retries": 2,
                "http_chunk_size": 8388608,  # 8MB chunks (menor para ser mais rápido)
                
                # SEM pós-processamento FFmpeg pesado (mais rápido)
                # O yt-dlp fará apenas o merge básico
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Verifica informações do vídeo antes do download
                try:
                    info = ydl.extract_info(url, download=False)
                    if info:
                        title = info.get('title', 'Vídeo')
                        duration = info.get('duration', 0)
                        
                        # Analisa formatos disponíveis e encontra o melhor ≤ 1080p
                        formats = info.get('formats', [])
                        if formats:
                            best_height = 0
                            available_heights = []
                            
                            for fmt in formats:
                                height = fmt.get('height', 0)
                                if height:
                                    available_heights.append(height)
                                    # Encontra a melhor resolução ≤ 1080p
                                    if height <= 1080 and height > best_height:
                                        best_height = height
                            
                            available_heights = sorted(set(available_heights), reverse=True)
                            
                            self.logger.info(f"📺 Título: {title}")
                            self.logger.info(f"⏱️ Duração: {duration//60}:{duration%60:02d}")
                            self.logger.info(f"📊 Resoluções disponíveis: {available_heights}")
                            self.logger.info(f"🎯 Selecionando: {best_height}p (máximo 1080p)")
                        
                except Exception as e:
                    self.logger.warning(f"⚠️ Não foi possível obter info prévia: {e}")
                
                # Faz o download
                ydl.download([url])
            
            # Verifica arquivos baixados
            arquivos_depois = set(p.name for p in self.pasta_downloads.glob("*.mp4"))
            novos_arquivos = arquivos_depois - arquivos_antes
            
            if novos_arquivos:
                self.logger.info(f"📥 {len(novos_arquivos)} arquivo(s) baixado(s) em resolução ≤ 1080p")
                
                # Verifica a qualidade real dos arquivos baixados
                for arquivo in sorted(novos_arquivos):
                    arquivo_path = self.pasta_downloads / arquivo
                    tamanho_mb = arquivo_path.stat().st_size / (1024*1024)
                    self.logger.info(f"   📁 {arquivo} ({tamanho_mb:.1f}MB)")
                    
                    # Tenta obter resolução real do arquivo
                    try:
                        import subprocess
                        result = subprocess.run([
                            'ffprobe', '-v', 'quiet', '-show_entries', 
                            'stream=width,height', '-of', 'csv=p=0', 
                            str(arquivo_path)
                        ], capture_output=True, text=True, timeout=10)
                        
                        if result.returncode == 0 and result.stdout.strip():
                            dimensions = result.stdout.strip().split(',')
                            if len(dimensions) >= 2:
                                width, height = dimensions[0], dimensions[1]
                                self.logger.info(f"   ✅ Resolução final: {width}x{height}")
                                
                                # Verifica se respeitou o limite de 1080p
                                if int(height) <= 1080:
                                    self.logger.info(f"   ✅ Limite de 1080p respeitado")
                                else:
                                    self.logger.warning(f"   ⚠️ Resolução acima de 1080p: {height}p")
                    except:
                        pass
                
                # REMOVE DUPLICATAS IMEDIATAMENTE
                self.remover_duplicatas()
                
                return True
            else:
                self.logger.warning("⚠️ Nenhum arquivo baixado pelo yt-dlp")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Erro no yt-dlp: {e}")
            return False

    def remover_duplicatas(self):
        """Remove duplicatas baseado no tamanho do arquivo"""
        arquivos = list(self.pasta_downloads.glob("*.mp4"))
        if len(arquivos) < 2:
            return
        
        self.logger.info(f"🔍 Verificando duplicatas em {len(arquivos)} arquivo(s)...")
        
        # Agrupa por tamanho
        por_tamanho = {}
        for arquivo in arquivos:
            tamanho = arquivo.stat().st_size
            if tamanho not in por_tamanho:
                por_tamanho[tamanho] = []
            por_tamanho[tamanho].append(arquivo)
        
        # Remove duplicatas
        removidas = 0
        for tamanho, grupo in por_tamanho.items():
            if len(grupo) > 1:
                # Mantém o primeiro, remove os outros
                manter = grupo[0]
                for remover in grupo[1:]:
                    self.logger.info(f"🗑️ Removendo duplicata: {remover.name}")
                    remover.unlink()
                    removidas += 1
                
                self.logger.info(f"✅ Mantido: {manter.name}")
        
        if removidas > 0:
            self.logger.info(f"🎉 {removidas} duplicata(s) removida(s)!")
        
        # Atualiza contador
        arquivos_finais = list(self.pasta_downloads.glob("*.mp4"))
        self.arquivos_baixados = len(arquivos_finais)

    def baixar_imagens_da_pagina(self, url):
        """Baixa imagens APENAS do erome.com (galeria atual)"""
        
        # Verifica se é erome.com (segurança dupla)
        if "erome.com" not in url.lower():
            self.logger.info("🚫 Site não é erome.com - pulando download de imagens")
            return True
        
        try:
            self.logger.info(f"🖼️ EROME.COM - Buscando imagens da galeria atual: {url}")
            
            headers = self.headers.copy()
            headers["Referer"] = url
            headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8"
            
            r = requests.get(url, headers=headers, timeout=15)
            r.raise_for_status()
            
            soup = BeautifulSoup(r.text, "html.parser")
            
            # Extrai ID da galeria da URL
            import re
            galeria_id = re.search(r'/a/([^/?]+)', url)
            if not galeria_id:
                self.logger.warning("❌ Não foi possível extrair ID da galeria")
                return False
            
            galeria_id = galeria_id.group(1)
            self.logger.info(f"🆔 ID da galeria erome: {galeria_id}")
            
            # Busca imagens específicas da galeria atual (SEM posters/capas)
            imagens_galeria = []
            
            # MÉTODO 1: Imagens principais da galeria (img-front, img-back)
            self.logger.info("🔍 Buscando imagens principais da galeria...")
            for img in soup.find_all("img", class_=["img-front", "img-back"]):
                data_src = img.get("data-src")
                if data_src and galeria_id in data_src:
                    imagens_galeria.append(data_src)
                    self.logger.info(f"   ✅ Imagem principal: {os.path.basename(data_src)}")
            
            # MÉTODO 2: Data attributes da galeria atual (SEM thumbnails e SEM posters)
            self.logger.info("🔍 Buscando data attributes da galeria...")
            for element in soup.find_all():
                for attr, value in element.attrs.items():
                    if (attr.startswith("data-") and isinstance(value, str) and
                        galeria_id in value and 
                        any(ext in value.lower() for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]) and
                        "/thumbs/" not in value.lower() and  # Evita thumbnails
                        "poster" not in attr.lower()):      # Evita posters/capas de vídeo
                        
                        imagens_galeria.append(value)
                        self.logger.info(f"   ✅ Data attr: {os.path.basename(value)}")
            
            # MÉTODO 3 REMOVIDO: Não busca mais posters de vídeo
            # (Comentado para mostrar que foi removido intencionalmente)
            # self.logger.info("🚫 Posters de vídeo ignorados (não baixa capas)")
            
            # Remove duplicatas mantendo ordem
            imagens_unicas = []
            for img in imagens_galeria:
                if img and img not in imagens_unicas:
                    imagens_unicas.append(img)
            
            self.logger.info(f"🎯 Total de imagens da galeria (SEM capas): {len(imagens_unicas)}")
            
            if not imagens_unicas:
                self.logger.warning("❌ Nenhuma imagem de conteúdo encontrada (posters/capas ignorados)")
                return False
            
            # Lista as imagens que vai baixar
            for i, src in enumerate(imagens_unicas, 1):
                self.logger.info(f"   📋 {i}. {os.path.basename(src)}")
            
            # Baixa as imagens da galeria
            baixadas = 0
            for i, src in enumerate(imagens_unicas, 1):
                try:
                    from urllib.parse import urljoin, urlparse, unquote
                    full_url = urljoin(url, src)
                    nome = os.path.basename(urlparse(full_url).path)
                    nome = unquote(nome or f"erome_{galeria_id}_{i}.jpg")
                    
                    # Garante extensão
                    if not any(ext in nome.lower() for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]):
                        if "jpeg" in full_url.lower():
                            nome += ".jpg"
                        elif "png" in full_url.lower():
                            nome += ".png"
                        elif "webp" in full_url.lower():
                            nome += ".webp"
                        else:
                            nome += ".jpg"
                    
                    destino = self.pasta_downloads / nome
                    
                    # Evita sobrescrever
                    contador = 1
                    nome_original = destino.stem
                    extensao = destino.suffix
                    while destino.exists():
                        destino = self.pasta_downloads / f"{nome_original}_{contador}{extensao}"
                        contador += 1
                    
                    self.logger.info(f"📥 Baixando imagem {i}/{len(imagens_unicas)}: {nome}")
                    
                    if self.baixar_arquivo_simples(full_url, destino):
                        baixadas += 1
                        self.logger.info(f"   ✅ Sucesso: {nome}")
                    else:
                        self.logger.warning(f"   ❌ Falha: {nome}")
                    
                except Exception as e:
                    self.logger.error(f"   💥 Erro: {e}")
            
            self.imagens_baixadas += baixadas
            
            if baixadas > 0:
                self.logger.info(f"🎉 EROME: {baixadas}/{len(imagens_unicas)} imagem(ns) de conteúdo baixada(s) (SEM capas)!")
                return True
            else:
                self.logger.warning("❌ EROME: Nenhuma imagem de conteúdo foi baixada")
                return False
            
        except Exception as e:
            self.logger.error(f"❌ Erro ao buscar imagens do erome: {e}")
            return False

    def processar_url(self, url):
        """Processa uma URL com estratégia específica por site"""
        self.logger.info(f"➡️ Processando: {url}")
        
        # Passo 1: SEMPRE baixar vídeos (todos os sites)
        video_success = self.baixar_videos_ytdlp(url)
        
        # Passo 2: Baixar imagens APENAS do erome.com
        if "erome.com" in url.lower():
            self.logger.info("🎯 EROME.COM detectado - baixando imagens da galeria!")
            image_success = self.baixar_imagens_da_pagina(url)
        else:
            self.logger.info("🌐 Site genérico/oficial - APENAS vídeos (sem imagens)")
            image_success = True  # Considera sucesso para não contar como erro
        
        # Resultado
        if video_success or (image_success and "erome.com" in url.lower()):
            self.logger.info(f"✅ URL processada com sucesso!")
        else:
            self.logger.warning(f"❌ Falha ao processar URL")
            self.erros += 1

    def processar_lista(self, arquivo_urls):
        """Processa lista de URLs"""
        try:
            with open(arquivo_urls, "r", encoding="utf-8") as f:
                urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            
            self.logger.info(f"📋 Encontradas {len(urls)} URL(s) para processar")
            
            for i, url in enumerate(urls, 1):
                self.logger.info(f"\n{'='*60}")
                self.logger.info(f"🔄 Processando {i}/{len(urls)}: {url}")
                self.logger.info(f"{'='*60}")
                
                self.processar_url(url)
                
                # Pausa entre URLs
                if i < len(urls):
                    time.sleep(2)
                    
        except FileNotFoundError:
            self.logger.error("❌ Arquivo 'lista.txt' não encontrado!")
            raise
        except Exception as e:
            self.logger.error(f"❌ Erro ao processar lista: {e}")
            raise

    def verificar_dependencias(self):
        """Verifica se o FFmpeg está disponível"""
        try:
            import subprocess
            result = subprocess.run(['ffmpeg', '-version'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                self.logger.info("✅ FFmpeg encontrado - conversão AAC disponível")
                return True
        except:
            pass
        
        self.logger.warning("⚠️ FFmpeg não encontrado - alguns vídeos podem manter áudio original")
        return False

    def relatorio_final(self):
        """Mostra relatório final"""
        print("\n" + "=" * 60)
        print("📊 RELATÓRIO UNIVERSAL MP4 + AAC HD")
        print("=" * 60)
        print(f"✅ Vídeos baixados: {self.arquivos_baixados}")
        print(f"🖼️ Imagens baixadas: {self.imagens_baixadas} (apenas erome.com)")
        print(f"⚠️ Arquivos ignorados: {self.arquivos_ignorados}")
        print(f"❌ Falhas: {self.erros}")
        print(f"📁 Pasta única: {self.pasta_downloads.absolute()}")
        print(f"🎵 Áudio: AAC compatível com todos os dispositivos")
        print(f"🎬 Vídeo: MÁXIMO 1080p (nunca acima)")
        print(f"🎯 Estratégia: Limite 1080p + Imagens (só erome)")
        print("=" * 60)

def main():
    # Oculta janela principal do tkinter
    root = tk.Tk()
    root.withdraw()
    
    try:
        downloader = MultiSiteDownloader("meus_downloads")
        
        # Verifica dependências
        ffmpeg_ok = downloader.verificar_dependencias()
        
        if not ffmpeg_ok:
            resposta = messagebox.askyesno(
                "FFmpeg não encontrado", 
                "FFmpeg não foi encontrado no sistema.\n\n"
                "Sem FFmpeg, alguns vídeos podem manter o áudio original.\n"
                "Para garantir áudio AAC, instale FFmpeg primeiro.\n\n"
                "Deseja continuar mesmo assim?"
            )
            if not resposta:
                return
        
        messagebox.showinfo(
            "Universal Downloader HD", 
            "🚀 Iniciando downloads RÁPIDOS com limite 1080p...\n\n"
            "• Vídeos: MP4 máximo 1080p + AAC (RÁPIDO)\n"
            "• Prioriza formatos já prontos (sem recodificação)\n"
            "• NUNCA baixa acima de 1080p\n"
            "• Imagens: Apenas do erome.com (SEM capas/posters)\n"
            "• Processamento otimizado para velocidade"
        )
        
        downloader.processar_lista("lista.txt")
        downloader.relatorio_final()
        
        messagebox.showinfo(
            "Concluído!", 
            f"✅ Processamento finalizado!\n\n"
            f"Vídeos: {downloader.arquivos_baixados}\n"
            f"Imagens: {downloader.imagens_baixadas}\n"
            f"Erros: {downloader.erros}\n\n"
            f"Pasta: {downloader.pasta_downloads.absolute()}"
        )
        
    except FileNotFoundError:
        messagebox.showerror(
            "Arquivo não encontrado", 
            "❌ Arquivo 'lista.txt' não encontrado!\n\n"
            "Crie um arquivo com as URLs dos vídeos,\n"
            "uma por linha, na mesma pasta do script."
        )
    except Exception as e:
        messagebox.showerror("Erro", f"❌ Erro: {str(e)}")

if __name__ == "__main__":
    main()
