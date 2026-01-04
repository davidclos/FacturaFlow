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
    current_year = datetime.now().year
    # Creem una llista: [Tots, Any següent, Any actual, Any passat, l'altre...]
    llista_anys = ["Tots"] + [str(y) for y in range(current_year + 1, current_year - 4, -1)]
    
    col1, col2 = st.columns(2)
    with col1:
        trimestre = st.selectbox("Trimestre", ["Tots", "1r Trimestre", "2n Trimestre", "3r Trimestre", "4t Trimestre"])
    with col2:
        # Ara la llista d'anys s'actualitza sola
        any = st.selectbox("Any", llista_anys)

    if st.button("Buscant correus..."):
        gmail_service, drive_service, sheets_service = authenticate()

        # Decidim el nom de la carpeta segons el que has triat
        if any == "Tots":
            nom_carpeta = "Factures Generals"
        elif trimestre == "Tots":
            nom_carpeta = f"Factures {any}"
        else:
            nom_carpeta = f"Factures {trimestre} {any}"

        # Busquem o creem aquesta carpeta específica
        folder_id, folder_link = get_or_create_quarter_folder(drive_service, nom_carpeta)
        st.info(f"📂 Treballant a la carpeta: **{nom_carpeta}**")

        # Filtres de data
        date_query = ""
        if any != "Tots":
            if trimestre == "Tots": date_query = f" after:{any}/01/01 before:{int(any)+1}/01/01"
            elif trimestre == "1r Trimestre": date_query = f" after:{any}/01/01 before:{any}/04/01"
            elif trimestre == "2n Trimestre": date_query = f" after:{any}/04/01 before:{any}/07/01"
            elif trimestre == "3r Trimestre": date_query = f" after:{any}/07/01 before:{any}/10/01"
            elif trimestre == "4t Trimestre": date_query = f" after:{any}/10/01 before:{int(any)+1}/01/01"
        
        query = f'label:{LABEL_NAME} has:attachment filename:pdf{date_query}'
        results = gmail_service.users().messages().list(userId="me", q=query).execute()
        messages = results.get("messages", [])

        if not messages:
            st.warning("No s'han trobat correus amb els filtres seleccionats.")
            st.stop()

        st.write(f"🔎 Analitzant {len(messages)} correus...")
        
        progress_bar = st.progress(0)
        historial_rows = []
        count_success = 0
        
        for i, msg in enumerate(messages):
            try:
                msg_data = gmail_service.users().messages().get(userId="me", id=msg["id"]).execute()
                payload = msg_data["payload"]
                parts = payload.get("parts", [])
                
                headers = payload["headers"]
                date_str = next((h["value"] for h in headers if h["name"] == "Date"), "")

                for part in parts:
                    if part.get("filename", "").lower().endswith(".pdf"):
                        att_id = part["body"]["attachmentId"]
                        att = gmail_service.users().messages().attachments().get(userId="me", messageId=msg["id"], id=att_id).execute()
                        file_data = base64.urlsafe_b64decode(att["data"])
                        filename = part["filename"]

                        # --- PUJADA A DRIVE (A LA CARPETA DEL TRIMESTRE) ---
                        file_metadata = {"name": filename, "parents": [folder_id]}
                        media = MediaIoBaseUpload(io.BytesIO(file_data), mimetype='application/pdf')
                        file = drive_service.files().create(body=file_metadata, media_body=media, fields="id").execute()
                        drive_link = f"https://drive.google.com/file/d/{file['id']}/view"

                        # --- LECTURA DADES ---
                        with pdfplumber.open(io.BytesIO(file_data)) as pdf:
                            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
                        
                        total_match = re.search(r'Total[:\s]*([\d.,]+)\s*€?', text, re.I)
                        total_val = total_match.group(1).replace(",", ".") if total_match else "0.00"
                        
                        prov_match = re.search(r'(?:Proveïdor|Emissor)[:\s]*(.+)', text, re.I)
                        proveidor_val = prov_match.group(1).strip() if prov_match else "Desconegut"

                        historial_rows.append([filename, date_str[:10], total_val, proveidor_val, "Processada", drive_link, datetime.now().strftime("%Y-%m-%d %H:%M")])
                        count_success += 1

            except Exception as e:
                print(f"Error al correu {msg['id']}: {e}")
            
            progress_bar.progress((i + 1) / len(messages))

        if historial_rows:
            sheets_service.spreadsheets().values().append(spreadsheetId=SHEET_ID, range="A1", valueInputOption="RAW", body={"values": historial_rows}).execute()
            
            st.success(f"✅ Fet! {count_success} factures guardades correctament.")
            st.markdown(f"### [📂 Ves a la carpeta: {nom_carpeta}]({folder_link})")
        else:
            st.warning("S'han trobat correus, però cap tenia un PDF vàlid o hi ha hagut errors.")

# ===================== HISTORIAL =====================
with tab2:
    if st.button("Actualitzar historial"):
        try:
            _, _, sheets_service = authenticate()
            result = sheets_service.spreadsheets().values().get(spreadsheetId=SHEET_ID, range="A:G").execute()
            values = result.get("values", [])
            if len(values) > 1:
                st.dataframe(pd.DataFrame(values[1:], columns=values[0]), use_container_width=True)
            else:
                st.info("Historial buit.")
        except:
            st.error("Error carregant historial.")
