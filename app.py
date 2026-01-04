import streamlit as st
import os
import pickle
import base64
import io
import pdfplumber
import re
import pandas as pd
from datetime import datetime
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from googleapiclient.http import MediaIoBaseUpload

# ===================== CONFIGURACIÓ =====================
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets"
]

LABEL_NAME = "Factures"
SHEET_ID = "1fS6cyXxMgjimNHCykATd8t3uoVTo3TxhEikMkPxrR0w"

st.set_page_config(page_title="FacturaFlow Pro", layout="centered")
st.markdown("<h1 style='text-align: center; color: #1a73e8;'>FacturaFlow Pro</h1>", unsafe_allow_html=True)

tab1, tab2 = st.tabs(["Pujar Factures", "Historial"])

# ===================== AUTENTICACIÓ =====================
def authenticate():
    creds = None
    token_path = "token.pickle"

    if os.path.exists(token_path):
        with open(token_path, "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            client_config = {
                "web": {
                    "client_id": st.secrets["CLIENT_ID"],
                    "client_secret": st.secrets["CLIENT_SECRET"],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                    "redirect_uris": ["https://facturaflow-fqzgmmmztxoc8a5ilixoof.streamlit.app"]
                }
            }
            flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            flow.redirect_uri = "https://facturaflow-fqzgmmmztxoc8a5ilixoof.streamlit.app"
            
            query_params = st.query_params
            auth_code = query_params.get("code")
            
            if auth_code:
                flow.fetch_token(code=auth_code)
                creds = flow.credentials
                with open(token_path, "wb") as token:
                    pickle.dump(creds, token)
                st.query_params.clear()
                st.rerun()
            else:
                auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
                st.warning("⚠️ Autorització necessària.")
                st.markdown(f"[👉 **Connectar amb Google**]({auth_url})", unsafe_allow_html=True)
                st.stop()

    return (build("gmail", "v1", credentials=creds), 
            build("drive", "v3", credentials=creds), 
            build("sheets", "v4", credentials=creds))

# ===================== CARPETA INTEL·LIGENT PER TRIMESTRE =====================
def get_or_create_quarter_folder(drive_service, folder_name):
    # 1. Busquem si ja existeix una carpeta amb aquest nom EXACTE
    query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
    results = drive_service.files().list(q=query, spaces='drive', fields='files(id, webViewLink)').execute()
    files = results.get('files', [])
    
    if files:
        # Si la trobem, perfecte! Tornem el seu ID
        return files[0]['id'], files[0]['webViewLink']
    else:
        # Si no existeix, LA CREEM
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        file = drive_service.files().create(body=file_metadata, fields='id, webViewLink').execute()
        return file['id'], file['webViewLink']

# ===================== PUJAR FACTURES =====================
with tab1:
    st.markdown("### Importar des de Gmail")
    
    # --- CÀLCUL AUTOMÀTIC D'ANYS ---
    # Agafem l'any actual del sistema (ex: 2026)
    current_year =
