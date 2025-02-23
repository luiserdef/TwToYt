import os
import time
import pickle
import sys
import json
import traceback
import re
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.http import MediaFileUpload

RESOURCES_PATH = 2

if RESOURCES_PATH == 1: #Google Colab with google drive
    CLIENT_SECRETS_PATH = "/content/drive/MyDrive/Colab Notebooks/client_secrets.json"
    VIDEO_LIST = "/content/drive/MyDrive/Colab Notebooks/video_list.txt"
    YOUTUBE_CREDS_PATH = "/content/drive/MyDrive/Colab Notebooks/youtube_creds.pkl"
    UPLOAD_FOLDER = "/content/"

if RESOURCES_PATH == 2: #DigitalOcean Droplets
    CLIENT_SECRETS_PATH = "/root/resources/client_secrets.json"
    VIDEO_LIST = "/root/resources/video_list.txt"
    YOUTUBE_CREDS_PATH = "/root/resources/youtube_creds.pkl"
    UPLOAD_FOLDER = "/root/VODS/" 

# Ruta de archivo que guardará los print del script
log_file = open("/root/resources/output_prints.log", "w")
sys.stdout = log_file

# Función para imprimir en el archivo log
def print_flush(*args, **kwargs):
    print(*args, **kwargs)
    sys.stdout.flush()

# Obtiene el tamaño del archivo en MB
def file_size(file_path):    
    file_size = os.path.getsize(file_path)
    file_size_mb = file_size / (1024 * 1024)
    return f"{file_size_mb:.2f} MB"

# Carga las credenciales guardadas de YouTube
with open(YOUTUBE_CREDS_PATH, "rb") as token:
    creds_data = pickle.load(token)

    # Verificar si 'client_id' y 'client_secret' están presentes en los datos de las credenciales
    if "client_id" not in creds_data or "client_secret" not in creds_data:
        # Si no están, obtenerlos del archivo client_secrets.json
        with open(CLIENT_SECRETS_PATH, "r") as client_secrets_file:
            client_secrets = json.load(client_secrets_file)
            creds_data["client_id"] = client_secrets["installed"]["client_id"]
            creds_data["client_secret"] = client_secrets["installed"]["client_secret"]

    # Crear el objeto de credenciales con los campos necesarios
    creds = Credentials(
        token=creds_data["access_token"],
        refresh_token=creds_data["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=creds_data["client_id"],
        client_secret=creds_data["client_secret"],
        scopes=creds_data["scope"]
    )

    # Refrescar el token si es necesario
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

# Crear el servicio de YouTube
youtube = build("youtube", "v3", credentials=creds)
print_flush("✅ Conectado a YouTube con credenciales.")

# Lee la lista de videos
try:    
    with open(VIDEO_LIST, "r") as file:
        video_lines = file.readlines()
except Exception as e:
    print_flush(f"❌ Ocurrió un error al leer la lista de videos.")
    #Detiene todo el proceso
    traceback.print_exc()
    sys.exit(1)

def clean_title(title,output_filename):
    title = title.strip()  # Elimina espacios extras
    title = re.sub(r'[<>:"/\\|?*]', '', title)  # Quita caracteres inválidos del título
    title = re.sub(r'[^\x00-\x7F]+', '', title)  # Elimina caracteres no ASCII (emojis y similares)
    title = title[:100]  # Limita a los primeros 100 caracteres (limite para titulos en youtube)
    return title if title.strip() else f"{output_filename} - Video sin titulo"


def uploadToYoutube(output_filename,title):
    try:
        request = youtube.videos().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": clean_title(title,output_filename),
                    "description": "**Agrega Descripción*",
                    "tags": ["Twitch","Youtube"], #cambiar
                    "categoryId": "20" #cambiar
                },
                "status": {"privacyStatus": "private"} #cambiar
            },
            media_body=MediaFileUpload(output_filename, resumable=True)
        )
        response = request.execute()
        print_flush(f"✅ Video subido con éxito: {response['id']}")
        return True
    except Exception as e:
        print_flush(f"❌ Error al subir el video {title}: {e}")
        return False 

def downloadVideo(output_filename,url,index):
    # Descargar el video desde Twitch
    try:
        os.system(f'yt-dlp -o "{output_filename}" -f best "{url}"')
        return True
    except Exception as e:
        print_flush(f"❌ Error al descargar el video {index + 1}: {e}, saltando...")
        return False

    # Verificar si el archivo se descargó correctamente
    if not os.path.exists(output_filename):
        print_flush(f"❌ No se pudo descargar el video {index + 1}, saltando...")
        return False

# Iteración que procesa cada video
for index, line in enumerate(video_lines):
    line = line.strip()
    if not line:
        print_flush(f"error al leer registro: linea {index}")
        continue

    # Separa por '^'
    title, url, download_status, upload_status = line.split('^')

    # Verifica si el video ya fue subido
    if download_status == "downloaded" and upload_status == "uploaded":
        print_flush(f"✅ El archivo video_{index}.mp4 - {title[:20]}... ya ha sido subido. Saltando...")
        continue

    output_filename = f"{UPLOAD_FOLDER}video_{index}.mp4"

    # Verificar si el archivo ya existe y si no está marcado como "subido"
    if os.path.exists(output_filename):
        if os.path.exists(output_filename) and download_status == "downloaded" and upload_status != "uploaded":
            print_flush(f"✅ El video {title[:20]}... ya está descargado pero no subido.")
        else: 
            if os.path.exists(output_filename):
                print_flush(f"❌ El video {title[:20]}... se descargo mal. Borrando...")
                os.remove(output_filename)
            print_flush(f"🔻 Descargando video {index + 1}/{len(video_lines)} de Twitch: {title[:20]}...")
            
            download_start_time = time.time()  # Registrar el tiempo de inicio de la descarga
            if downloadVideo(output_filename,url,index):   
                download_duration = time.time() - download_start_time  # Calcular duración
                print_flush(f"✅ Video descargado en {download_duration:.2f} segundos. {file_size(output_filename)}")             

                download_status = "downloaded"
                video_lines[index] = f"{title}^ {url}^{download_status}^{upload_status}\n"
                # Guardar los cambios en el archivo twitch_collections.txt
                with open(VIDEO_LIST, "w") as file:
                    file.writelines(video_lines)
            else:
                continue

    # Si el video no ha sido descargado, proceder a descargarlo
    elif not os.path.exists(output_filename):
        print_flush(f"🔻 Descargando video {index + 1}/{len(video_lines)} de Twitch: {title[:20]}...")

        download_start_time = time.time()  # Registrar el tiempo de inicio de la descarga
        if downloadVideo(output_filename,url,index):
            download_duration = time.time() - download_start_time  # Calcular duración
            print_flush(f"✅ Video descargado en {download_duration:.2f} segundos. {file_size(output_filename)}") 
            
            download_status = "downloaded"
            video_lines[index] = f"{title}^ {url}^{download_status}^{upload_status}\n"
            # Guardar los cambios en el archivo twitch_collections.txt
            with open(VIDEO_LIST, "w") as file:
                file.writelines(video_lines)
        else:
            continue

    # Subir a YouTube
    print_flush(f"🚀 Subiendo {output_filename} a YouTube...")

    upload_start_time = time.time()  # Registrar el tiempo de inicio de la subida
    if not uploadToYoutube(output_filename,title):
        #Detiene todo el proceso
        traceback.print_exc()
        sys.exit(1)

    upload_duration = time.time() - upload_start_time  # Calcular duración
    print_flush(f"✅ Video subido en {upload_duration:.2f} segundos.")

    # Actualizar la línea para marcar el video como subido
    upload_status = "uploaded"
    video_lines[index] = f"{title}^ {url}^{download_status}^{upload_status}\n"
    # Guardar los cambios en el archivo twitch_collections.txt
    with open(VIDEO_LIST, "w") as file:
        file.writelines(video_lines)

    # Borrar el video local para liberar espacio
    os.remove(output_filename)

    # Esperar unos segundos antes de continuar con el siguiente
    time.sleep(10)

print_flush("✅ Todos los videos han sido procesados.")

