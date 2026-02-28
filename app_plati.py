import streamlit as st
import os
import json
import base64
import hashlib 
import csv
import io
import gspread
from enum import Enum
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta

# --- LIBRĂRII NOI PENTRU SECURITATE ȘI COOKIES ---
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import extra_streamlit_components as stx

st.set_page_config(page_title="Monitorizare Plăți", page_icon="💳", layout="centered")

# --- 1. DEFINIȚIILE ENUM ȘI CLASA DE DATE ---

class StatusPlata(Enum):
    ACHITAT = "Achitat"
    NEACHITAT = "Neachitat"

class LocatiePlata(Enum):
    ONLINE = "Online"
    FIZIC = "Fizic"

class CategoriePlata(Enum):
    UTILITATI = "Utilitati" 
    SUBSCRIPTII = "Abonamente"
    CREDIT = "Credit"
    DIVERSE = "Diverse"

class ValutaPlata(Enum):
    RON = "RON"
    EUR = "EUR"
    USD = "USD"
    GBP = "GBP"

class PlataRecurenta:
    def __init__(self, nume_plata: str, suma: float, scadenta: int, categorie: CategoriePlata, locatie: LocatiePlata, valuta: ValutaPlata, status=StatusPlata.NEACHITAT) -> None:
        self.id_plata = 1
        self.status = status
        self.nume_plata = nume_plata
        self.suma = suma
        self.scadenta = scadenta
        self.categorie = categorie
        self.locatie = locatie
        self.valuta = valuta


# --- 2. SECURITATE: CRIPTARE ȘI COOKIES ---

@st.cache_resource 
def get_google_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

# Inițializăm managerul de cookies fără cache, direct în script
cookie_manager = stx.CookieManager()

def criptare_parola(parola):
    return hashlib.sha256(parola.encode('utf-8')).hexdigest()

def genereaza_cheie_criptare(parola, utilizator):
    # Generăm o cheie unică și extrem de puternică folosind parola și numele ca "sare" (salt)
    salt = utilizator.encode('utf-8')
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000
    )
    key = base64.urlsafe_b64encode(kdf.derive(parola.encode('utf-8')))
    return Fernet(key)

def autentificare(username, parola, client):
    try:
        sheet = client.open("BazaDate_Plati").worksheet("Conturi")
        records = sheet.get_all_records()
        for r in records:
            if str(r.get("Utilizator", "")).lower() == username.lower():
                if str(r.get("Parola", "")) == criptare_parola(parola):
                    return True
        return False
    except gspread.exceptions.WorksheetNotFound:
        sheet_principal = client.open("BazaDate_Plati")
        sheet_conturi = sheet_principal.add_worksheet(title="Conturi", rows=100, cols=2)
        sheet_conturi.append_row(["Utilizator", "Parola"])
        return False

def inregistrare(username, parola, client):
    username = username.lower().strip()
    try:
        sheet_principal = client.open("BazaDate_Plati")
        try:
            sheet_conturi = sheet_principal.worksheet("Conturi")
        except gspread.exceptions.WorksheetNotFound:
            sheet_conturi = sheet_principal.add_worksheet(title="Conturi", rows=100, cols=2)
            sheet_conturi.append_row(["Utilizator", "Parola"])
        
        records = sheet_conturi.get_all_records()
        for r in records:
            if str(r.get("Utilizator", "")).lower() == username:
                return False, "Acest nume de utilizator este deja luat!"
        
        sheet_conturi.append_row([username, criptare_parola(parola)])
        
        try:
            sheet_principal.worksheet(username)
        except gspread.exceptions.WorksheetNotFound:
            # Acum tabelul are doar ID și Date_Criptate pentru intimitate maximă
            noua_foaie = sheet_principal.add_worksheet(title=username, rows=100, cols=2)
            noua_foaie.append_row(["ID", "Date_Criptate"])
            
        return True, "Contul a fost creat cu succes!"
    except Exception as e:
        return False, f"Eroare de conexiune la baza de date: {e}"


# --- 3. MANAGERUL DE PLĂȚI ---

class ManagerPlati:
    def __init__(self, utilizator, parola_clara, client):
        self.id_curent = 1
        self.lista_plati = []
        self.utilizator = utilizator.lower()
        self.parola_clara = parola_clara
        
        # Instantiem modulul de criptare/decriptare
        self.fernet = genereaza_cheie_criptare(parola_clara, self.utilizator)
        
        self.client = client
        sheet_principal = self.client.open("BazaDate_Plati")
        self.foaie_user = sheet_principal.worksheet(self.utilizator)
        self.incarca_date()

    def adauga_plata(self, nume, suma, scadenta, categorie, locatie, valuta):
        plata_noua = PlataRecurenta(nume, suma, scadenta, categorie, locatie, valuta)
        plata_noua.id_plata = self.id_curent
        self.lista_plati.append(plata_noua)
        self.id_curent += 1
        self.salveaza_date()

    def editeaza_plata(self, id_plata, nume_nou, suma_noua, scadenta_noua, cat_noua, loc_noua, val_noua):
        for plata in self.lista_plati:
            if plata.id_plata == id_plata:
                plata.nume_plata = nume_nou
                plata.suma = suma_noua
                plata.scadenta = scadenta_noua
                plata.categorie = cat_noua
                plata.locatie = loc_noua
                plata.valuta = val_noua
                self.salveaza_date()
                return

    def actualizeaza_status(self, id_plata, status_nou):
        for plata in self.lista_plati:
            if plata.id_plata == id_plata:
                plata.status = status_nou
                self.salveaza_date()
                return

    def sterge_plata(self, id_plata):
        for plata in self.lista_plati:
            if plata.id_plata == id_plata:
                self.lista_plati.remove(plata)
                self.salveaza_date()
                return

    def actualizeaza_luna_noua(self):
        for plata in self.lista_plati:
            plata.status = StatusPlata.NEACHITAT
        self.salveaza_date()

    def get_total_ron(self, filtru_status=None):
        total = 0
        for plata in self.lista_plati:
            if filtru_status and plata.status.value != filtru_status.value:
                continue
            if plata.valuta.value == ValutaPlata.RON.value:
                total += plata.suma
            elif plata.valuta.value == ValutaPlata.EUR.value:
                total += plata.suma * 5.10
            elif plata.valuta.value == ValutaPlata.USD.value:
                total += plata.suma * 4.33
            elif plata.valuta.value == ValutaPlata.GBP.value:
                total += plata.suma * 5.83
        return total

    def salveaza_date(self):
        date_pentru_tabel = [["ID", "Date_Criptate"]]
        for p in self.lista_plati:
            # Transformăm datele într-un dicționar, apoi în string
            date_dict = {
                "nume": p.nume_plata, "suma": p.suma, "scadenta": p.scadenta,
                "categorie": p.categorie.value, "locatie": p.locatie.value,
                "valuta": p.valuta.value, "status": p.status.value
            }
            json_str = json.dumps(date_dict)
            
            # Criptăm string-ul
            sir_criptat = self.fernet.encrypt(json_str.encode('utf-8')).decode('utf-8')
            date_pentru_tabel.append([p.id_plata, sir_criptat])
        
        try:
            self.foaie_user.clear()
            self.foaie_user.update(values=date_pentru_tabel, range_name="A1") 
        except Exception as e:
            st.error(f"Eroare la salvarea in Google Sheets: {e}")

    def incarca_date(self):
        try:
            toate_randurile = self.foaie_user.get_all_records()
            self.lista_plati = []
            
            # Verificăm dacă fișierul este gol
            if not toate_randurile:
                return
                
            # VERIFICARE TRANZIȚIE: Suntem pe formatul vechi sau pe cel nou criptat?
            if "Nume" in toate_randurile[0]:
                # --- SUNTEM PE FORMATUL VECHI ---
                st.warning("🔄 Baza ta de date este actualizată la noul format securizat. Te rugăm să aștepți câteva secunde...")
                
                for d in toate_randurile:
                    p = PlataRecurenta(
                        str(d["Nume"]), float(d["Suma"]), int(d["Scadenta"]),
                        CategoriePlata(str(d["Categorie"])), LocatiePlata(str(d["Modalitate de Plata"])),
                        ValutaPlata(str(d["Valuta"])), StatusPlata(str(d["Status"]))
                    )
                    p.id_plata = int(d["ID"])
                    self.lista_plati.append(p)
                
                # Salvăm imediat datele înapoi, dar de data asta vor trece prin 
                # funcția salveaza_date() care le va CRIPTA automat!
                self.salveaza_date()
                st.success("✅ Securizarea s-a încheiat cu succes! Te rugăm să reîncarci pagina (Refresh).")
                
            else:
                # --- SUNTEM PE FORMATUL NOU (CRIPTAT) ---
                for d in toate_randurile:
                    id_plata = int(d["ID"])
                    sir_criptat = d["Date_Criptate"]
                    
                    # Decriptăm șirul și îl refacem dicționar
                    json_str = self.fernet.decrypt(sir_criptat.encode('utf-8')).decode('utf-8')
                    date_dict = json.loads(json_str)
                    
                    p = PlataRecurenta(
                        date_dict["nume"], float(date_dict["suma"]), int(date_dict["scadenta"]),
                        CategoriePlata(date_dict["categorie"]), LocatiePlata(date_dict["locatie"]),
                        ValutaPlata(date_dict["valuta"]), StatusPlata(date_dict["status"])
                    )
                    p.id_plata = id_plata
                    self.lista_plati.append(p)

            # Setăm ID-ul curent pentru următoarele plăți
            if self.lista_plati:
                self.id_curent = max([p.id_plata for p in self.lista_plati]) + 1
                
        except Exception as e:
            st.error(f"Eroare la încărcarea sau descifrarea datelor: {e}")

# --- 4. INTERFAȚA WEB (STREAMLIT) ---

google_client = get_google_client()

# Inițializare variabile de stare
if 'logat' not in st.session_state:
    st.session_state.logat = False
    st.session_state.user = ""
    st.session_state.parola = ""
if 'toast_mesaj' not in st.session_state:
    st.session_state.toast_mesaj = None

# Verificare Cookie pentru Autologin
token_cookie = cookie_manager.get(cookie="auth_token")
if token_cookie and not st.session_state.logat:
    try:
        user_c, pass_c = token_cookie.split("::")
        if autentificare(user_c, pass_c, google_client):
            st.session_state.logat = True
            st.session_state.user = user_c
            st.session_state.parola = pass_c
            st.rerun()
    except Exception:
        pass

# --- Afișare Toast-uri Restante (după reîncărcarea paginii) ---
if st.session_state.toast_mesaj:
    st.toast(st.session_state.toast_mesaj, icon="✅")
    st.session_state.toast_mesaj = None

# --- Gatekeeper: Sistem de Login & Înregistrare ---
if not st.session_state.logat:
    st.title("🔐 Acces Aplicație")
    
    tab_login, tab_register = st.tabs(["🔑 Autentificare", "📝 Creare Cont Nou"])
    
    with tab_login:
        with st.form("login_form"):
            user_login = st.text_input("Utilizator")
            pass_login = st.text_input("Parolă", type="password")
            btn_login = st.form_submit_button("Intră în cont")
            
            if btn_login:
                if autentificare(user_login, pass_login, google_client):
                    st.session_state.logat = True
                    st.session_state.user = user_login.lower()
                    st.session_state.parola = pass_login
                    
                    # Salvăm Cookie-ul (expiră în fix 30 de zile)
                    data_expirare = datetime.now() + timedelta(days=30)
                    cookie_manager.set("auth_token", f"{user_login.lower()}::{pass_login}", key="set_auth", expires_at=data_expirare)
                    
                    # AM ȘTERS st.rerun() DE AICI!
                else:
                    st.error("Utilizator inexistent sau parolă incorectă!")
                    
    with tab_register:
        with st.form("register_form"):
            st.write("Creează-ți un spațiu privat și securizat pentru facturi")
            new_user = st.text_input("Alege un Nume de Utilizator")
            new_pass = st.text_input("Alege o Parolă", type="password")
            new_pass_confirm = st.text_input("Confirmă Parola", type="password")
            btn_register = st.form_submit_button("Creează Cont")
            
            if btn_register:
                if new_pass != new_pass_confirm:
                    st.error("Parolele nu coincid!")
                elif not new_user or not new_pass:
                    st.error("Te rog completează toate câmpurile.")
                else:
                    success, mesaj = inregistrare(new_user, new_pass, google_client)
                    if success:
                        st.success(mesaj + " Acum te poți loga din tab-ul de Autentificare.")
                    else:
                        st.error(mesaj)
                        
    # Oprim codul AICI doar dacă utilizatorul încă NU s-a logat cu succes
    if not st.session_state.logat:
        st.stop()

# --- Aplicatia Principala ---
if 'manager' not in st.session_state:
    st.session_state.manager = ManagerPlati(st.session_state.user, st.session_state.parola, google_client)

manager = st.session_state.manager

st.sidebar.title(f"Salut, {st.session_state.user.capitalize()}!")
meniu = st.sidebar.radio("Meniu", ["Vezi Plăți & Statistici", "Adaugă Plată", "Resetare Lunară & Export", "Logout"])

if meniu == "Logout":
    st.session_state.logat = False
    cookie_manager.delete("auth_token", key="del_auth")
    del st.session_state.manager
    st.rerun()

# --- PAGINA 1: ADAUGĂ PLATĂ ---
if meniu == "Adaugă Plată":
    st.header("📝 Adaugă o Plată Nouă")
    
    with st.form("form_adaugare"):
        c1, c2 = st.columns(2)
        with c1:
            nume = st.text_input("Nume Plată")
            suma = st.number_input("Suma", min_value=0.0, step=10.0)
            valuta = st.selectbox("Valuta", [v.value for v in ValutaPlata])
        with c2:
            scadenta = st.number_input("Ziua Scadenței (1-31)", min_value=1, max_value=31)
            categorie = st.selectbox("Categorie", [c.value for c in CategoriePlata])
            locatie = st.selectbox("Locație", [l.value for l in LocatiePlata])
            
        if st.form_submit_button("Salvează"):
            if not nume:
                st.error("Numele este obligatoriu!")
            else:
                manager.adauga_plata(nume, suma, scadenta, CategoriePlata(categorie), LocatiePlata(locatie), ValutaPlata(valuta))
                st.session_state.toast_mesaj = f"Plata {nume} a fost adăugată!"
                st.rerun()

# --- PAGINA 2: VEZI PLĂȚI ---
elif meniu == "Vezi Plăți & Statistici":
    st.header("📊 Situația Ta Financiară")
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Total General", f"{manager.get_total_ron():.2f} RON")
    c2.metric("Rămas de Plată", f"{manager.get_total_ron(StatusPlata.NEACHITAT):.2f} RON", delta_color="inverse")
    c3.metric("Deja Achitat", f"{manager.get_total_ron(StatusPlata.ACHITAT):.2f} RON")
    
    st.divider()
    ziua_azi = datetime.now().day

    

    if not manager.lista_plati:
        st.info("Nu ai facturi de plată.")
    else:
        for plata in manager.lista_plati:
            with st.container(border=True):
                # Am adăugat o coloană mică (col_edit) fix lângă nume
                col1, col_edit, col2, col3, col4 = st.columns([2, 0.5, 1, 1.5, 1])
                
                col1.markdown(f"""
                <div style='line-height: 1.3;'>
                    <span style='font-size: 1.35rem; font-weight: 800; color: #2e86c1;'>{plata.nume_plata}</span><br>
                    <span style='font-size: 0.85rem; color: gray;'>📂 {plata.categorie.value} | 📍 {plata.locatie.value}</span>
                </div>
                """, unsafe_allow_html=True)
                
                # --- AICI E NOUL BUTON DE EDITARE ---
                with col_edit:
                    with st.popover("✏️"):
                        st.markdown(f"**Editează {plata.nume_plata}**")
                        with st.form(f"edit_form_{plata.id_plata}"):
                            n_nume = st.text_input("Nume", value=plata.nume_plata)
                            n_suma = st.number_input("Suma", value=float(plata.suma), step=10.0)
                            
                            v_list = [v.value for v in ValutaPlata]
                            n_valuta = st.selectbox("Valuta", v_list, index=v_list.index(plata.valuta.value))
                            
                            n_scadenta = st.number_input("Ziua scadenței", value=plata.scadenta, min_value=1, max_value=31)
                            
                            c_list = [c.value for c in CategoriePlata]
                            n_cat = st.selectbox("Categorie", c_list, index=c_list.index(plata.categorie.value))
                            
                            l_list = [l.value for l in LocatiePlata]
                            n_loc = st.selectbox("Locație", l_list, index=l_list.index(plata.locatie.value))
                            
                            btn_salveaza = st.form_submit_button("Salvează Modificările", use_container_width=True)
                            if btn_salveaza:
                                manager.editeaza_plata(plata.id_plata, n_nume, n_suma, n_scadenta, CategoriePlata(n_cat), LocatiePlata(n_loc), ValutaPlata(n_valuta))
                                st.session_state.toast_mesaj = "Datele au fost actualizate cu succes!"
                                st.rerun()
                                
                        # Butonul de ștergere e separat, sub formular
                        if st.button("🗑️ Șterge plată", key=f"del_{plata.id_plata}", type="primary", use_container_width=True):
                            manager.sterge_plata(plata.id_plata)
                            st.session_state.toast_mesaj = "Plata a fost ștearsă!"
                            st.rerun()
                # ------------------------------------
                
                col2.markdown(f"""
                <div style='margin-top: 10px;'>
                    <span style='font-size: 1.2rem; font-weight: 700;'>{plata.suma}</span> 
                    <span style='font-size: 0.9rem;'>{plata.valuta.value}</span>
                </div>
                """, unsafe_allow_html=True)
                
                if plata.status.value == StatusPlata.ACHITAT.value:
                    col3.success("✅ ACHITAT")
                else:
                    zile_ramase = plata.scadenta - ziua_azi
                    if zile_ramase < 0:
                        col3.error(f"🚨 Întârziat ({abs(zile_ramase)} zile)")
                    elif zile_ramase == 0:
                        col3.error("⚠️ Scadent AZI!")
                    elif 1 <= zile_ramase <= 3:
                        col3.warning(f"⏳ Încă {zile_ramase} zile")
                    else:
                        col3.info(f"📅 Scadență: ziua {plata.scadenta}")

                if plata.status.value == StatusPlata.NEACHITAT.value:
                    if col4.button("💸 Achită", key=f"pay_{plata.id_plata}"):
                        manager.actualizeaza_status(plata.id_plata, StatusPlata.ACHITAT)
                        st.session_state.toast_mesaj = f"Ai marcat {plata.nume_plata} ca achitat!"
                        st.rerun()
                else:
                    if col4.button("↩️ Anulează", key=f"unpay_{plata.id_plata}"):
                        manager.actualizeaza_status(plata.id_plata, StatusPlata.NEACHITAT)
                        st.rerun()

# --- PAGINA 3: RESETARE LUNARĂ & EXPORT CSV ---
elif meniu == "Resetare Lunară & Export":
    st.header("🔄 Închidere Lună & Export")
    st.write("Deși pe Google Sheets datele sunt criptate, aici poți descărca istoricul tău perfect lizibil în format Excel (CSV).")
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Nume Plata", "Suma", "Valuta", "Scadenta", "Categorie", "Modalitate de Plata", "Status"])
    
    for p in manager.lista_plati:
        writer.writerow([p.id_plata, p.nume_plata, p.suma, p.valuta.value, p.scadenta, p.categorie.value, p.locatie.value, p.status.value])
    
    csv_data = output.getvalue()
    
    luni_romana = {1:"ianuarie", 2:"februarie", 3:"martie", 4:"aprilie", 5:"mai", 6:"iunie", 
                7:"iulie", 8:"august", 9:"septembrie", 10:"octombrie", 11:"noiembrie", 12:"decembrie"}
    luna_curenta = luni_romana[datetime.now().month]
    nume_fisier = f"{luna_curenta}-plati.csv"

    st.subheader("Pasul 1: Salvează istoricul")
    st.download_button(
        label="📥 Descarcă Raportul Lunii (CSV)",
        data=csv_data,
        file_name=nume_fisier,
        mime="text/csv",
        help="Descarcă tabelul cu plățile înainte să le resetezi."
    )
    
    st.divider()
    
    st.subheader("Pasul 2: Curăță pentru luna nouă")
    st.warning("Atenție: Această acțiune va reseta toate plățile înapoi la 'NEACHITAT'.")
    if st.button("🔄 Resetează Statusurile"):
        manager.actualizeaza_luna_noua()
        st.session_state.toast_mesaj = "Toate statusurile au fost resetate!"
        st.rerun()



