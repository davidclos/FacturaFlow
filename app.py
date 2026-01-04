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

# ===================== CONFIGURACIÓ =====================
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets"
]

LABEL_NAME = "Factures"
DRIVE_FOLDER_ID = "1jXAN0FrhPu84mwcYIOzmmfdWOt3EwYRA"
SHEET_ID = "1fS6cyXxMgjimNHCykATd8t3uoVTo3TxhEikMkPxrR0w"  # El teu ID

st.set_page_config(page_title="FacturaFlow Pro", layout="centered")
st.markdown("<h1 style='text-align: center; color: #1a73e8;'>FacturaFlow Pro</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; font-style: italic;'>Dades assegurades localment. No perdràs cap revisió.</p>", unsafe_allow_html=True)

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
            # Configuració del flow amb redirect_uri forçat
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
            flow.redirect_uri = "https://facturaflow-fqzgmmmztxoc8a5ilixoof.streamlit.app"  # FORÇAT AQUÍ

            auth_url, _ = flow.authorization_url(
                prompt="consent",
                access_type="offline"
            )

            st.markdown("**Autoritza l'app amb Google:**")
            st.markdown(f"[{auth_url}]({auth_url})")

            st.info("Obre l'enllaç, accepta els permisos i copia el codi que et dona Google.")

            code = st.text_input("Enganxa aquí el codi d'autorització:", type="password")

            if code:
                try:
                    flow.fetch_token(code=code)
                    creds = flow.credentials
                    with open(token_path, "wb") as token:
                        pickle.dump(creds, token)
                    st.success("Connectat correctament a Google!")
                except Exception as e:
                    st.error(f"Error: {e}")
                    st.stop()
            else:
                st.warning("Cal el codi per continuar.")
                st.stop()

    gmail_service = build("gmail", "v1", credentials=creds)
    drive_service = build("drive", "v3", credentials=creds)
    sheets_service = build("sheets", "v4", credentials=creds)
    return gmail_service, drive_service, sheets_service

# ===================== PUJAR FACTURES =====================
with tab1:
    st.markdown("### Importar des de Gmail (Etiqueta \"Factures\")")

    col1, col2 = st.columns(2)
    with col1:
        trimestre = st.selectbox("Trimestre", ["Tots", "1r Trimestre", "2n Trimestre", "3r Trimestre", "4t Trimestre"])
    with col2:
        any = st.selectbox("Any", ["Tots", "2025", "2024", "2023"])

    if st.button("Buscant correus..."):
        gmail_service, drive_service, sheets_service = authenticate()

        query = f'label:{LABEL_NAME} has:attachment filename:pdf'
        results = gmail_service.users().messages().list(userId="me", q=query).execute()
        messages = results.get("messages", [])

        if not messages:
            st.info("No s'han trobat factures PDF a l'etiqueta Factures.")
            st.stop()

        st.write(f"Trobats {len(messages)} correus amb factures.")

        with st.spinner("Processant..."):
            historial_rows = []
            for msg in messages:
                msg_data = gmail_service.users().messages().get(userId="me", id=msg["id"]).execute()
                payload = msg_data["payload"]
                headers = payload["headers"]
                subject = next((h["value"] for h in headers if h["name"] == "Subject"), "Sense assumpte")
                date_str = next((h["value"] for h in headers if h["name"] == "Date"), "")

                parts = payload.get("parts", [])
                for part in parts:
                    if part.get("filename", "").lower().endswith(".pdf"):
                        att_id = part["body"]["attachmentId"]
                        att = gmail_service.users().messages().attachments().get(userId="me", messageId=msg["id"], id=att_id).execute()
                        file_data = base64.urlsafe_b64decode(att["data"])
                        filename = part["filename"]

                        # Guardar a Drive
                        file_metadata = {"name": filename, "parents": [DRIVE_FOLDER_ID]}
                        media = io.BytesIO(file_data)
                        file = drive_service.files().create(body=file_metadata, media_body=media, fields="id").execute()
                        drive_link = f"https://drive.google.com/file/d/{file['id']}/view"

                        # Extreure total i proveïdor
                        with pdfplumber.open(io.BytesIO(file_data)) as pdf:
                            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
                        total = re.search(r'Total[:\s]*([\d.,]+)\s*€?', text, re.I)
                        total_val = total.group(1).replace(",", ".") if total else "0.00"
                        proveidor = re.search(r'(?:Proveïdor|Emissor)[:\s]*(.+)', text, re.I)
                        proveidor_val = proveidor.group(1).strip() if proveidor else "Desconegut"

                        historial_rows.append([filename, date_str[:10], total_val, proveidor_val, "Processada", drive_link, datetime.now().strftime("%Y-%m-%d %H:%M")])

                        st.success(f"{filename} processada i guardada a Drive")

            if historial_rows:
                sheets_service.spreadsheets().values().append(spreadsheetId=SHEET_ID, range="A1", valueInputOption="RAW", body={"values": historial_rows}).execute()
                st.success("Historial actualitzat a Google Sheets!")

# ===================== HISTORIAL =====================
with tab2:
    st.markdown("### Historial de Factures Pujades")
    if st.button("Actualitzar historial"):
        try:
            _, _, sheets_service = authenticate()
            result = sheets_service.spreadsheets().values().get(spreadsheetId=SHEET_ID, range="A:G").execute()
            values = result.get("values", [])
            if len(values) > 1:
                df = pd.DataFrame(values[1:], columns=values[0])
                st.dataframe(df, use_container_width=True)
            else:
                st.info("Encara no hi ha factures a l'historial.")
        except Exception as e:
            st.error("Error carregant l'historial. Autentica't primer.")

st.markdown("<p style='text-align: center;'>O bé puja-les manualment</p>", unsafe_allow_html=True)
