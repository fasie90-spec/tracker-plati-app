import json
import base64
import hashlib 
from enum import Enum
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import streamlit as st

# --- DEFINIȚII ȘI CLASE ---
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

class TipTranzactie(Enum):
    VENIT = "Venit"
    CHELTUIALA = "Cheltuiala"

class PlataRecurenta:
    def __init__(self, nume_plata, suma, scadenta, categorie, locatie, valuta, status=StatusPlata.NEACHITAT):
        self.id_plata = 1
        self.status = status
        self.nume_plata = nume_plata
        self.suma = suma
        self.scadenta = scadenta
        self.categorie = categorie
        self.locatie = locatie
        self.valuta = valuta

class Tranzactie:
    def __init__(self, id_tranzactie, suma, categorie, data, tip):
        self.id_tranzactie = id_tranzactie
        self.suma = suma
        self.categorie = categorie
        self.data = data
        self.tip = tip

# --- SECURITATE ȘI API ---
@st.cache_data(ttl=43200) # Cache la API 12 ore pentru a nu bloca serverul
def extrage_curs_valutar():
    try:
        r = requests.get("https://open.er-api.com/v6/latest/RON", timeout=5)
        rate = r.json().get('rates', {})
        # API-ul ne dă 1 RON = X EUR. Facem invers (1/X) ca să aflăm cursul de schimb clasic
        return {
            "RON": 1.0,
            "EUR": 1 / rate.get("EUR", 0.20),
            "USD": 1 / rate.get("USD", 0.22),
            "GBP": 1 / rate.get("GBP", 0.17)
        }
    except Exception:
        # Fallback de siguranță dacă pică netul
        return {"RON": 1.0, "EUR": 4.97, "USD": 4.60, "GBP": 5.80}

@st.cache_resource 
def get_google_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

def criptare_parola(parola):
    return hashlib.sha256(parola.encode('utf-8')).hexdigest()

def genereaza_cheie_criptare(parola, utilizator):
    salt = utilizator.encode('utf-8')
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
    return Fernet(base64.urlsafe_b64encode(kdf.derive(parola.encode('utf-8'))))

def autentificare(username, parola, client):
    try:
        sheet = client.open("BazaDate_Plati").worksheet("Conturi")
        for r in sheet.get_all_records():
            if str(r.get("Utilizator", "")).lower() == username.lower() and str(r.get("Parola", "")) == criptare_parola(parola):
                return True
        return False
    except gspread.exceptions.WorksheetNotFound:
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
        
        for r in sheet_conturi.get_all_records():
            if str(r.get("Utilizator", "")).lower() == username:
                return False, "Acest nume de utilizator este deja luat!"
        
        sheet_conturi.append_row([username, criptare_parola(parola)])
        
        # Creăm cele 2 tabele: Plăți și Tranzacții
        foi_existente = [ws.title for ws in sheet_principal.worksheets()]
        if username not in foi_existente:
            sheet_principal.add_worksheet(title=username, rows=100, cols=2).append_row(["ID", "Date_Criptate"])
        if f"{username}_tranzactii" not in foi_existente:
            sheet_principal.add_worksheet(title=f"{username}_tranzactii", rows=100, cols=2).append_row(["ID", "Date_Criptate"])
            
        return True, "Contul a fost creat cu succes!"
    except Exception as e:
        return False, f"Eroare DB: {e}"

# --- MANAGER PLĂȚI RECURENTE ---
class ManagerPlati:
    def __init__(self, utilizator, parola_clara, client):
        self.id_curent = 1
        self.lista_plati = []
        self.utilizator = utilizator.lower()
        self.fernet = genereaza_cheie_criptare(parola_clara, self.utilizator)
        self.foaie = client.open("BazaDate_Plati").worksheet(self.utilizator)
        self.rate_valutare = extrage_curs_valutar() # Aducem API-ul
        self.incarca_date()

    def adauga_plata(self, nume, suma, scadenta, categorie, locatie, valuta):
        p = PlataRecurenta(nume, suma, scadenta, categorie, locatie, valuta)
        p.id_plata = self.id_curent
        self.lista_plati.append(p)
        self.id_curent += 1
        self.salveaza_date()

    def editeaza_plata(self, id_plata, n_nume, n_suma, n_scadenta, n_cat, n_loc, n_val):
        for p in self.lista_plati:
            if p.id_plata == id_plata:
                p.nume_plata, p.suma, p.scadenta, p.categorie, p.locatie, p.valuta = n_nume, n_suma, n_scadenta, n_cat, n_loc, n_val
                self.salveaza_date()
                return

    def actualizeaza_status(self, id_plata, status_nou):
        for p in self.lista_plati:
            if p.id_plata == id_plata:
                p.status = status_nou
                self.salveaza_date()
                return

    def sterge_plata(self, id_plata):
        self.lista_plati = [p for p in self.lista_plati if p.id_plata != id_plata]
        self.salveaza_date()

    def get_total_ron(self, filtru_status=None):
        total = 0
        for p in self.lista_plati:
            if filtru_status and p.status.value != filtru_status.value: continue
            # Acum conversia e DINAMICĂ folosind datele de pe internet
            total += p.suma * self.rate_valutare.get(p.valuta.value, 1)
        return total

    def actualizeaza_luna_noua(self):
        for p in self.lista_plati:
            p.status = StatusPlata.NEACHITAT
        self.salveaza_date()
    
    def salveaza_date(self):
        date = [["ID", "Date_Criptate"]]
        for p in self.lista_plati:
            dict_date = {"nume": p.nume_plata, "suma": p.suma, "scadenta": p.scadenta, "categorie": p.categorie.value, "locatie": p.locatie.value, "valuta": p.valuta.value, "status": p.status.value}
            criptat = self.fernet.encrypt(json.dumps(dict_date).encode('utf-8')).decode('utf-8')
            date.append([p.id_plata, criptat])
        self.foaie.clear()
        self.foaie.update(values=date, range_name="A1")

    def incarca_date(self):
        randuri = self.foaie.get_all_records()
        if not randuri: return
        for d in randuri:
            try:
                dict_date = json.loads(self.fernet.decrypt(d["Date_Criptate"].encode('utf-8')).decode('utf-8'))
                p = PlataRecurenta(dict_date["nume"], float(dict_date["suma"]), int(dict_date["scadenta"]), CategoriePlata(dict_date["categorie"]), LocatiePlata(dict_date["locatie"]), ValutaPlata(dict_date["valuta"]), StatusPlata(dict_date["status"]))
                p.id_plata = int(d["ID"])
                self.lista_plati.append(p)
            except Exception: pass
        if self.lista_plati: self.id_curent = max([p.id_plata for p in self.lista_plati]) + 1

# --- MANAGER TRANZACȚII ZILNICE (PORTOFEL) ---
class ManagerTranzactii:
    def __init__(self, utilizator, parola_clara, client):
        self.id_curent = 1
        self.lista_tranzactii = []
        self.utilizator = utilizator.lower()
        self.fernet = genereaza_cheie_criptare(parola_clara, self.utilizator)
        
        sheet_principal = client.open("BazaDate_Plati")
        nume_foaie = f"{self.utilizator}_tranzactii"
        
        # Căutare manuală și sigură (ignorând litere mari/mici)
        toate_foile = sheet_principal.worksheets()
        foaie_gasita = None
        for f in toate_foile:
            if f.title.lower() == nume_foaie.lower():
                foaie_gasita = f
                break
                
        if foaie_gasita:
            self.foaie = foaie_gasita
        else:
            self.foaie = sheet_principal.add_worksheet(title=nume_foaie, rows=100, cols=2)
            self.foaie.append_row(["ID", "Date_Criptate"])
            
        self.incarca_date()

    def adauga_tranzactie(self, suma, categorie, data, tip):
        t = Tranzactie(self.id_curent, suma, categorie, data, tip)
        self.lista_tranzactii.append(t)
        self.id_curent += 1
        self.salveaza_date()
        
    def sterge_tranzactie(self, id_tranzactie):
        self.lista_tranzactii = [t for t in self.lista_tranzactii if t.id_tranzactie != id_tranzactie]
        self.salveaza_date()

    def calculeaza_sold(self):
        sold = 0
        for t in self.lista_tranzactii:
            if t.tip == TipTranzactie.VENIT: sold += t.suma
            elif t.tip == TipTranzactie.CHELTUIALA: sold -= t.suma
        return sold

    def salveaza_date(self):
        date = [["ID", "Date_Criptate"]]
        for t in self.lista_tranzactii:
            dict_date = {"suma": t.suma, "categorie": t.categorie, "data": t.data, "tip": t.tip.value}
            criptat = self.fernet.encrypt(json.dumps(dict_date).encode('utf-8')).decode('utf-8')
            date.append([t.id_tranzactie, criptat])
        self.foaie.clear()
        self.foaie.update(values=date, range_name="A1")

    def incarca_date(self):
        randuri = self.foaie.get_all_records()
        if not randuri: return
        for d in randuri:
            try:
                dict_date = json.loads(self.fernet.decrypt(d["Date_Criptate"].encode('utf-8')).decode('utf-8'))
                t = Tranzactie(int(d["ID"]), float(dict_date["suma"]), dict_date["categorie"], dict_date["data"], TipTranzactie(dict_date["tip"]))
                self.lista_tranzactii.append(t)
            except Exception: pass

        if self.lista_tranzactii: self.id_curent = max([t.id_tranzactie for t in self.lista_tranzactii]) + 1

