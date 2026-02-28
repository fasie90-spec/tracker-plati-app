import streamlit as st
import extra_streamlit_components as stx
from datetime import datetime, timedelta
import plotly.express as px
import pandas as pd

# Importăm tot din noul nostru "creier" backend
from backend import (
    get_google_client, autentificare, inregistrare, extrage_curs_valutar,
    ManagerPlati, ManagerTranzactii, StatusPlata, ValutaPlata, CategoriePlata, LocatiePlata, TipTranzactie
)

st.set_page_config(page_title="Personal Finance Hub", page_icon="🏦", layout="centered")
cookie_manager = stx.CookieManager()
google_client = get_google_client()

# --- INITIALIZARE STARE ---
if 'logat' not in st.session_state:
    st.session_state.logat = False
    st.session_state.user = ""
    st.session_state.parola = ""
if 'toast_mesaj' not in st.session_state:
    st.session_state.toast_mesaj = None

token_cookie = cookie_manager.get(cookie="auth_token")
if token_cookie and not st.session_state.logat:
    try:
        user_c, pass_c = token_cookie.split("::")
        if autentificare(user_c, pass_c, google_client):
            st.session_state.logat = True
            st.session_state.user = user_c
            st.session_state.parola = pass_c
            st.rerun()
    except Exception: pass

if st.session_state.toast_mesaj:
    st.toast(st.session_state.toast_mesaj, icon="✅")
    st.session_state.toast_mesaj = None

# --- ECRAN LOGIN ---
if not st.session_state.logat:
    st.title("🔐 Acces Personal Finance Hub")
    tab_login, tab_register = st.tabs(["🔑 Autentificare", "📝 Creare Cont Nou"])
    
    with tab_login:
        with st.form("login_form"):
            user_login = st.text_input("Utilizator")
            pass_login = st.text_input("Parolă", type="password")
            if st.form_submit_button("Intră în cont"):
                if autentificare(user_login, pass_login, google_client):
                    st.session_state.logat = True
                    st.session_state.user, st.session_state.parola = user_login.lower(), pass_login
                    cookie_manager.set("auth_token", f"{user_login.lower()}::{pass_login}", key="set_auth", expires_at=datetime.now() + timedelta(days=30))
                else:
                    st.error("Utilizator inexistent sau parolă incorectă!")
                    
    with tab_register:
        with st.form("register_form"):
            new_user = st.text_input("Alege un Nume de Utilizator")
            new_pass = st.text_input("Alege o Parolă", type="password")
            new_pass_confirm = st.text_input("Confirmă Parola", type="password")
            if st.form_submit_button("Creează Cont"):
                if new_pass != new_pass_confirm: st.error("Parolele nu coincid!")
                elif not new_user or not new_pass: st.error("Completează toate câmpurile.")
                else:
                    succes, mesaj = inregistrare(new_user, new_pass, google_client)
                    if succes: st.success(mesaj + " Acum te poți loga.")
                    else: st.error(mesaj)
    st.stop()

# --- INSTANȚIERE MANAGERI ---
if 'manager_plati' not in st.session_state:
    st.session_state.manager_plati = ManagerPlati(st.session_state.user, st.session_state.parola, google_client)
    st.session_state.manager_tranz = ManagerTranzactii(st.session_state.user, st.session_state.parola, google_client)

mgr_plati = st.session_state.manager_plati
mgr_tranz = st.session_state.manager_tranz

# --- MENIU LATERAL ---
st.sidebar.title(f"Salut, {st.session_state.user.capitalize()}! 🚀")
st.sidebar.info(f"💶 Curs actualizat: 1 EUR = {mgr_plati.rate_valutare['EUR']:.2f} RON")

meniu = st.sidebar.radio("Meniu Principal", [
    "📊 Dashboard Analytics", 
    "💳 Facturi & Scadențe", 
    "💰 Portofel (Cashflow)", 
    "Logout"
])

if meniu == "Logout":
    st.session_state.logat = False
    cookie_manager.delete("auth_token", key="del_auth")
    st.rerun()

# ==========================================
# 📊 PAGINA 1: DASHBOARD & ANALYTICS
# ==========================================
if meniu == "📊 Dashboard Analytics":
    st.header("📊 Privire de Ansamblu")
    
    sold_curent = mgr_tranz.calculeaza_sold()
    ramas_facturi = mgr_plati.get_total_ron(StatusPlata.NEACHITAT)
    buget_real = sold_curent - ramas_facturi
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Bani in Portofel", f"{sold_curent:.2f} RON")
    c2.metric("Facturi Neachitate", f"{ramas_facturi:.2f} RON", delta="-", delta_color="inverse")
    c3.metric("Buget Real Disponibil", f"{buget_real:.2f} RON", 
            help="Banii rămași în portofel DUPĂ ce vei plăti toate facturile curente.")
    
    st.divider()
    
    # 🟩 BARA DE PROGRES PENTRU FACTURI
    total_facturi = mgr_plati.get_total_ron()
    total_achitat = mgr_plati.get_total_ron(StatusPlata.ACHITAT)
    
    st.subheader("🏁 Progres Achitare Facturi")
    if total_facturi > 0:
        procent = int((total_achitat / total_facturi) * 100)
        st.progress(procent / 100, text=f"Ai achitat {procent}% din facturile lunii ({total_achitat:.0f} / {total_facturi:.0f} RON)")
    else:
        st.info("Nu ai nicio factură adăugată pentru a calcula progresul.")
        
    st.divider()

    # 📊 GRAFIC PIE CHART - Distribuția Cheltuielilor
    st.subheader("🍕 Distribuția Facturilor pe Categorii")
    date_grafic = {"Categorie": [], "Suma": []}
    
    for p in mgr_plati.lista_plati:
        date_grafic["Categorie"].append(p.categorie.value)
        # Convertim tot in RON pentru grafic
        suma_ron = p.suma * mgr_plati.rate_valutare.get(p.valuta.value, 1)
        date_grafic["Suma"].append(suma_ron)
        
    if date_grafic["Suma"]:
        df = pd.DataFrame(date_grafic)
        fig = px.pie(df, values='Suma', names='Categorie', hole=0.4, color_discrete_sequence=px.colors.sequential.RdBu)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.write("Nu există date suficiente pentru grafic.")

# ==========================================
# 💳 PAGINA 2: FACTURI (Aplicația ta veche, restilizată)
# ==========================================
elif meniu == "💳 Facturi & Scadențe":
    st.header("💳 Gestionare Facturi Recurente")
    ziua_azi = datetime.now().day

    with st.expander("➕ Adaugă Factură Nouă"):
        with st.form("form_adaugare_plata"):
            col1, col2 = st.columns(2)
            n_nume = col1.text_input("Nume Plată")
            n_suma = col1.number_input("Suma", min_value=0.0, step=10.0)
            n_valuta = col1.selectbox("Valuta", [v.value for v in ValutaPlata])
            n_scadenta = col2.number_input("Ziua (1-31)", min_value=1, max_value=31)
            n_cat = col2.selectbox("Categorie", [c.value for c in CategoriePlata])
            n_loc = col2.selectbox("Locație", [l.value for l in LocatiePlata])
            
            if st.form_submit_button("Salvează Factura", use_container_width=True):
                mgr_plati.adauga_plata(n_nume, n_suma, n_scadenta, CategoriePlata(n_cat), LocatiePlata(n_loc), ValutaPlata(n_valuta))
                st.session_state.toast_mesaj = "Factură adăugată!"
                st.rerun()

    st.divider()

    # Modalul pentru Editare Plăți
    @st.dialog("✏️ Editează Plata")
    def modal_editare(plata):
        with st.form(f"form_modal_{plata.id_plata}"):
            e_nume = st.text_input("Nume", value=plata.nume_plata)
            e_suma = st.number_input("Suma", value=float(plata.suma))
            v_list, c_list, l_list = [v.value for v in ValutaPlata], [c.value for c in CategoriePlata], [l.value for l in LocatiePlata]
            e_val = st.selectbox("Valuta", v_list, index=v_list.index(plata.valuta.value))
            e_scad = st.number_input("Ziua", value=plata.scadenta)
            e_cat = st.selectbox("Categorie", c_list, index=c_list.index(plata.categorie.value))
            e_loc = st.selectbox("Locație", l_list, index=l_list.index(plata.locatie.value))
            
            if st.form_submit_button("Salvează Modificările", use_container_width=True):
                mgr_plati.editeaza_plata(plata.id_plata, e_nume, e_suma, e_scad, CategoriePlata(e_cat), LocatiePlata(e_loc), ValutaPlata(e_val))
                st.session_state.toast_mesaj = "Actualizat cu succes!"
                st.rerun()
                
        if st.button("🗑️ Șterge plată", type="primary", use_container_width=True):
            mgr_plati.sterge_plata(plata.id_plata)
            st.session_state.toast_mesaj = "Ștearsă!"
            st.rerun()

    # --- FILTRARE ȘI ORDONARE ---
    with st.expander("🔎 Filtrare și Ordonare", expanded=False):
        f1, f2, f3 = st.columns(3)
        f_stat = f1.selectbox("Status", ["Toate", "Doar Neachitate", "Doar Achitate"])
        f_cat = f2.selectbox("Categorie", ["Toate"] + [c.value for c in CategoriePlata])
        
        optiuni_sortare = [
            "Scadență (Apropiate)", 
            "Scadență (Îndepărtate)", 
            "Sumă (Crescător)", 
            "Sumă (Descrescător)", 
            "Nume (A-Z)",
            "Status (Neachitate primele)",
            "Status (Achitate primele)"
        ]
        
        # Recuperăm preferința din cookie
        sort_salvat = cookie_manager.get("pref_sortare")
        index_pref = optiuni_sortare.index(sort_salvat) if sort_salvat in optiuni_sortare else 0
        
        sortare = f3.selectbox("Ordonare după", optiuni_sortare, index=index_pref)
        
        # Salvăm dacă s-a schimbat
        if sortare != sort_salvat:
            cookie_manager.set("pref_sortare", sortare, key="set_sort_p", expires_at=datetime.now() + timedelta(days=365))

    # --- APLICARE LOGICĂ FILTRARE ---
    plati = mgr_plati.lista_plati.copy()
    if f_stat == "Doar Neachitate": plati = [p for p in plati if p.status.value == "Neachitat"]
    elif f_stat == "Doar Achitate": plati = [p for p in plati if p.status.value == "Achitat"]
    if f_cat != "Toate": plati = [p for p in plati if p.categorie.value == f_cat]
    
    # --- APLICARE LOGICĂ SORTARE ---
    if sortare == "Scadență (Apropiate)": 
        plati.sort(key=lambda x: x.scadenta)
    elif sortare == "Scadență (Îndepărtate)": 
        plati.sort(key=lambda x: x.scadenta, reverse=True)
    elif sortare == "Sumă (Crescător)": 
        plati.sort(key=lambda x: x.suma * mgr_plati.rate_valutare.get(x.valuta.value, 1))
    elif sortare == "Sumă (Descrescător)": 
        plati.sort(key=lambda x: x.suma * mgr_plati.rate_valutare.get(x.valuta.value, 1), reverse=True)
    elif sortare == "Nume (A-Z)": 
        plati.sort(key=lambda x: x.nume_plata.lower())
    elif sortare == "Status (Neachitate primele)":
        plati.sort(key=lambda x: x.status.value, reverse=True) # N vine după A
    elif sortare == "Status (Achitate primele)":
        plati.sort(key=lambda x: x.status.value)

    # --- AFIȘARE REZULTATE ---
    for plata in plati:
        with st.container(border=True):
            cn, ce = st.columns([4, 1])
            cn.markdown(f"<div style='font-size: 1.35rem; font-weight: 800; color: #2e86c1;'>{plata.nume_plata}</div>", unsafe_allow_html=True)
            cn.markdown(f"<div style='font-size: 0.85rem; color: gray;'>📂 {plata.categorie.value} | 📍 {plata.locatie.value}</div>", unsafe_allow_html=True)
            
            ce.markdown("<div style='text-align: right;'>", unsafe_allow_html=True)
            if ce.button("✏️", key=f"btn_edit_{plata.id_plata}"): modal_editare(plata)
            ce.markdown("</div>", unsafe_allow_html=True)

            st.divider()
            c_suma, c_stat, c_act = st.columns([1.5, 1.5, 1])
            c_suma.markdown(f"<div style='font-size: 1.2rem; font-weight: 700;'>{plata.suma} <span style='font-size: 0.9rem;'>{plata.valuta.value}</span></div>", unsafe_allow_html=True)
            
            if plata.status.value == "Achitat":
                c_stat.success("✅ ACHITAT")
            else:
                zr = plata.scadenta - ziua_azi
                if zr < 0: c_stat.error(f"🚨 Întârziat ({abs(zr)} zile)")
                elif zr == 0: c_stat.error("⚠️ Scadent AZI!")
                else: c_stat.info(f"📅 Scadență: {plata.scadenta}")

            if plata.status.value == "Neachitat":
                if c_act.button("💸 Achită", key=f"pay_{plata.id_plata}", use_container_width=True):
                    mgr_plati.actualizeaza_status(plata.id_plata, StatusPlata.ACHITAT)
                    suma_ron = plata.suma * mgr_plati.rate_valutare.get(plata.valuta.value, 1)
                    data_azi_str = datetime.now().strftime("%d-%m-%Y")
                    mgr_tranz.adauga_tranzactie(suma_ron, f"Plată factură: {plata.nume_plata}", data_azi_str, TipTranzactie.CHELTUIALA)
                    st.session_state.toast_mesaj = f"Achitat! Au fost retrași {suma_ron:.2f} RON din portofel."
                    st.rerun()
            else:
                if c_act.button("↩️ Anulează", key=f"unpay_{plata.id_plata}", use_container_width=True):
                    mgr_plati.actualizeaza_status(plata.id_plata, StatusPlata.NEACHITAT)
                    st.session_state.toast_mesaj = "Status anulat! (Banii nu au fost returnați automat)"
                    st.rerun()

# ==========================================
# 💰 PAGINA 3: PORTOFEL (Tranzacții Cashflow)
# ==========================================
elif meniu == "💰 Portofel (Cashflow)":
    st.header("💰 Portofelul Meu")
    st.write(f"**Sold Curent:** {mgr_tranz.calculeaza_sold():.2f} RON")
    
    with st.form("form_tranzactie"):
        c1, c2, c3 = st.columns(3)
        t_tip = c1.selectbox("Tip", ["Cheltuiala", "Venit"])
        t_suma = c2.number_input("Suma (RON)", min_value=1.0)
        t_cat = c3.text_input("Detalii / Categorie")
        
        if st.form_submit_button("Înregistrează", use_container_width=True):
            if not t_cat: st.error("Completează categoria!")
            else:
                data_azi = datetime.now().strftime("%d-%m-%Y")
                tip_enum = TipTranzactie.VENIT if t_tip == "Venit" else TipTranzactie.CHELTUIALA
                mgr_tranz.adauga_tranzactie(t_suma, t_cat, data_azi, tip_enum)
                st.session_state.toast_mesaj = f"{t_tip} adăugat cu succes!"
                st.rerun()

    st.subheader("Istoric Tranzacții")
    if not mgr_tranz.lista_tranzactii:
        st.info("Nicio tranzacție înregistrată.")
    else:
        # Afișăm cele mai noi primele
        for t in reversed(mgr_tranz.lista_tranzactii):
            with st.container(border=True):
                col_i, col_d = st.columns([4, 1])
                culoare = "green" if t.tip.value == "Venit" else "red"
                semn = "+" if t.tip.value == "Venit" else "-"
                
                col_i.markdown(f"**{t.categorie}** <br> <span style='color: gray; font-size: 0.8em;'>{t.data}</span>", unsafe_allow_html=True)
                col_d.markdown(f"<div style='text-align:right; font-weight: bold; color: {culoare};'>{semn}{t.suma}</div>", unsafe_allow_html=True)
                
                if col_d.button("🗑️", key=f"del_t_{t.id_tranzactie}", help="Șterge tranzacție"):
                    mgr_tranz.sterge_tranzactie(t.id_tranzactie)
                    st.rerun()


