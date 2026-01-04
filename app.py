import streamlit as st
import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from datetime import datetime
import base64
import io
import pdfplumber
import re
import pandas as pd

# Configuració
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/spreadsheets'  # Nou per Sheets
]
LABEL_NAME = "Factures"
DRIVE_FOLDER_ID = "1jXAN0FrhPu84mwcYIOzmmfdWOt3EwYRA"  # ID de la carpeta "Factures Processades"
SHEET_ID = "POSA_L_ID_DEL_TEUGOOGLE_SHEET_AQUI"  # ID del Sheet (de la URL)

st.set_page_config(page_title="FacturaFlow Pro", layout="centered")
st.markdown("<h1 style='text-align: center; color: #1a73e8;'>FacturaFlow Pro</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; font-style: italic;'>Dades assegurades localment. No perdràs cap revisió.</p>", unsafe_allow_html=True)

tab1, tab2 = st.tabs(["Pujar Factures", "Historial"])

with tab1:
    st.markdown("### Importar des de Gmail (Etiqueta \"Factures\")")
    
    col1, col2 = st.columns(2)
    with col1:
        trimestre = st.selectbox("Trimestre", ["Tots", "1r Trimestre", "2n Trimestre", "3r Trimestre", "4t Trimestre"])
    with col2:
        any = st.selectbox("Any", ["2025", "2024", "2023", "Tots"])
    
    if st.button("Buscant correus..."):
        # Autenticació (igual que abans)
        def authenticate():
            creds = None
            if os.path.exists('token.pickle'):
                with open('token.pickle', 'rb') as token:
                    creds = pickle.load(token)
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                 flow = InstalledAppFlow.from_client_config(
    {
        "web": {
            "client_id": st.secrets["CLIENT_ID"],
            "client_secret": st.secrets["CLIENT_SECRET"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["https://auth.streamlit.app/callback"],
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs"
        }
    },
    SCOPES
)
creds = flow.run_local_server(port=0)
                with open('token.pickle', 'wb') as token:
                    pickle.dump(creds, token)
            return build('gmail', 'v1', credentials=creds), build('drive', 'v3', credentials=creds), build('sheets', 'v4', credentials=creds)
        
        gmail_service, drive_service, sheets_service = authenticate()
        
        # Buscar correus (amb filtre trimestre/any si vols, aquí simplificat)
        query = f"label:{LABEL_NAME} has:attachment filename:pdf"
        results = gmail_service.users().messages().list(userId='me', q=query).execute()
        messages = results.get('messages', [])
        
        if messages:
            with st.spinner("Processant factures amb IA... Extraiem dades automàticament"):
                for msg in messages[:10]:  # Límits per no saturar
                    # Extreure PDF, guardar a Drive, extreure dades, afegir a Sheet (igual que codi anterior)
                    # ... (posa aquí la lògica d'extracció que teníem)
                    st.success(f"Processada: {filename}")
        else:
            st.info("No s'han trobat factures noves.")

with tab2:
    st.markdown("### Historial de Factures Pujades")
    
    # Connecta i llegeix el Sheet
    try:
        sheets_service = ...  # Del authenticate
        result = sheets_service.spreadsheets().values().get(spreadsheetId=SHEET_ID, range="A:G").execute()
        values = result.get('values', [])
        if len(values) > 1:
            df = pd.DataFrame(values[1:], columns=values[0])
            st.dataframe(df, use_container_width=True)
        else:
            st.info("Encara no hi ha factures a l'historial.")
    except:
        st.error("Connecta primer a la pestanya Pujar Factures.")

st.markdown("<p style='text-align: center;'>O bé puja-les manualment</p>", unsafe_allow_html=True)
