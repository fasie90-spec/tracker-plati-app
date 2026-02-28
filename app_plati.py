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

    # --- SECTIUNE ECONOMII (500 RON Target) ---
    luna_curenta = datetime.now().month
    economii_luna_asta = sum(t.suma for t in mgr_tranz.lista_tranzactii 
                             if t.tip == TipTranzactie.ECONOMII and 
                             datetime.strptime(t.data, "%d-%m-%Y").month == luna_curenta)
    
    economii_totale = mgr_tranz.calculeaza_economii_totale()

    col_ec1, col_ec2 = st.columns([1, 2])
    col_ec1.metric("Total în Seif", f"{economii_totale:.2f} RON", delta="💰")
    
    with col_ec2:
        st.write("**Target Lunar Economii (500 RON)**")
        procent_ec = min(int((economii_luna_asta / 500) * 100), 100)
        st.progress(procent_ec / 100)
        st.caption(f"Ai pus deoparte {economii_luna_asta:.2f} RON luna aceasta.")
    
    st.divider()
    
    # 🟩 BARA DE PROGRES PENTRU FACTURI
    total_facturi = mgr_plati.get_total_ron()
    total_achitat = mgr_plati.get_total_ron(StatusPlata.ACHITAT)
    
    st.subheader("🏁 Progres Achitare Facturi")
    if total_facturi > 0:
        procent = int((total_achitat / total_facturi) * 100)
        st.progress(procent / 100, text=f"Ai achitat {procent}% din facturi ({total_achitat:.0f} / {total_facturi:.0f} RON)")
    else:
        st.info("Nu ai facturi adăugate.")
        
    st.divider()

    # 📊 GRAFIC DONUT CHART MODERN
    st.subheader("🍕 Distribuția Cheltuielilor")
    date_grafic = {"Categorie": [], "Suma": []}
    
    for p in mgr_plati.lista_plati:
        date_grafic["Categorie"].append(p.categorie)
        suma_ron = p.suma * mgr_plati.rate_valutare.get(p.valuta.value, 1)
        date_grafic["Suma"].append(suma_ron)
        
    if date_grafic["Suma"]:
        df = pd.DataFrame(date_grafic).groupby("Categorie")["Suma"].sum().reset_index()
        fig = px.pie(df, values='Suma', names='Categorie', hole=0.6, 
                     color_discrete_sequence=px.colors.qualitative.Pastel)
        fig.update_traces(textposition='inside', textinfo='percent')
        fig.update_layout(showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.write("Nu există date pentru grafic.")

    st.divider()
    st.subheader("🏁 Închidere Lună")
    with st.expander("🔄 Resetare pentru Lună Nouă"):
        st.warning("Atenție: Această acțiune va reseta toate facturile la statusul 'NEACHITAT'.")
        if st.button("Confirmă Resetarea Facturilor", use_container_width=True, type="primary"):
            mgr_plati.actualizeaza_luna_noua()
            st.session_state.toast_mesaj = "Toate facturile au fost resetate!"
            st.rerun()

# ==========================================
# 💳 PAGINA 2: FACTURI
# ==========================================
elif meniu == "💳 Facturi & Scadențe":
    st.header("💳 Gestionare Facturi Recurente")
    
    # 1. BARA DE PROGRES
    total_facturi = mgr_plati.get_total_ron()
    total_achitat = mgr_plati.get_total_ron(StatusPlata.ACHITAT)
    if total_facturi > 0:
        procent = int((total_achitat / total_facturi) * 100)
        st.write(f"**Progres Lună Curentă:** {procent}% achitat")
        st.progress(procent / 100)
    
    st.divider()
    ziua_azi = datetime.now().day

    # 2. BUTONUL DE ADĂUGARE CU CATEGORII DINAMICE
    with st.expander("➕ Adaugă Factură Nouă"):
        with st.form("form_adaugare_plata"):
            col1, col2 = st.columns(2)
            n_nume = col1.text_input("Nume Plată")
            n_suma = col1.number_input("Suma", min_value=0.0, step=10.0)
            n_valuta = col1.selectbox("Valuta", [v.value for v in ValutaPlata])
            
            with col2:
                n_scadenta = st.number_input("Ziua (1-31)", min_value=1, max_value=31)
                optiuni_cat = mgr_plati.categorii_disponibile + ["➕ Adaugă categorie nouă..."]
                selectie_cat = st.selectbox("Categorie", optiuni_cat)
                if selectie_cat == "➕ Adaugă categorie nouă...":
                    n_cat = st.text_input("Nume Categorie Nouă")
                else:
                    n_cat = selectie_cat
                n_loc = st.selectbox("Locație", [l.value for l in LocatiePlata])
            
            if st.form_submit_button("Salvează Factura", use_container_width=True):
                if not n_nume or not n_cat:
                    st.error("Numele și Categoria sunt obligatorii!")
                else:
                    mgr_plati.adauga_plata(n_nume, n_suma, n_scadenta, n_cat, LocatiePlata(n_loc), ValutaPlata(n_valuta))
                    st.session_state.toast_mesaj = "Factură adăugată!"
                    st.rerun()

    # 3. FILTRARE ȘI ORDONARE
    with st.expander("🔎 Filtrare și Ordonare", expanded=False):
        f1, f2, f3 = st.columns(3)
        f_stat = f1.selectbox("Status", ["Toate", "Doar Neachitate", "Doar Achitate"])
        f_cat = f2.selectbox("Categorie", ["Toate"] + mgr_plati.categorii_disponibile)
        
        optiuni_sortare = ["Scadență (Apropiate)", "Scadență (Îndepărtate)", "Sumă (Crescător)", "Sumă (Descrescător)", "Nume (A-Z)", "Status (Neachitate primele)", "Status (Achitate primele)"]
        sort_salvat = cookie_manager.get("pref_sortare")
        index_pref = optiuni_sortare.index(sort_salvat) if sort_salvat in optiuni_sortare else 0
        sortare = f3.selectbox("Ordonare după", optiuni_sortare, index=index_pref)
        if sortare != sort_salvat:
            cookie_manager.set("pref_sortare", sortare, key="set_sort_p", expires_at=datetime.now() + timedelta(days=365))

    # 4. LOGICA DE FILTRARE/SORTARE
    plati = mgr_plati.lista_plati.copy()
    if f_stat == "Doar Neachitate": plati = [p for p in plati if p.status.value == "Neachitat"]
    elif f_stat == "Doar Achitate": plati = [p for p in plati if p.status.value == "Achitat"]
    if f_cat != "Toate": plati = [p for p in plati if p.categorie == f_cat]
    
    if sortare == "Scadență (Apropiate)": plati.sort(key=lambda x: x.scadenta)
    elif sortare == "Scadență (Îndepărtate)": plati.sort(key=lambda x: x.scadenta, reverse=True)
    elif sortare == "Sumă (Crescător)": plati.sort(key=lambda x: x.suma * mgr_plati.rate_valutare.get(x.valuta.value, 1))
    elif sortare == "Sumă (Descrescător)": plati.sort(key=lambda x: x.suma * mgr_plati.rate_valutare.get(x.valuta.value, 1), reverse=True)
    elif sortare == "Nume (A-Z)": plati.sort(key=lambda x: x.nume_plata.lower())
    elif sortare == "Status (Neachitate primele)": plati.sort(key=lambda x: x.status.value, reverse=True)
    elif sortare == "Status (Achitate primele)": plati.sort(key=lambda x: x.status.value)

    # 5. MODAL EDITARE
    @st.dialog("✏️ Editează Plata")
    def modal_editare(plata_e):
        with st.form(f"form_edit_{plata_e.id_plata}"):
            e_nume = st.text_input("Nume", value=plata_e.nume_plata)
            e_suma = st.number_input("Suma", value=float(plata_e.suma))
            v_list = [v.value for v in ValutaPlata]
            e_val = st.selectbox("Valuta", v_list, index=v_list.index(plata_e.valuta.value))
            e_scad = st.number_input("Ziua", value=plata_e.scadenta, min_value=1, max_value=31)
            
            e_cat = st.selectbox("Categorie", mgr_plati.categorii_disponibile, index=mgr_plati.categorii_disponibile.index(plata_e.categorie) if plata_e.categorie in mgr_plati.categorii_disponibile else 0)
            l_list = [l.value for l in LocatiePlata]
            e_loc = st.selectbox("Locație", l_list, index=l_list.index(plata_e.locatie.value))
            
            if st.form_submit_button("Salvează Modificările", use_container_width=True):
                mgr_plati.editeaza_plata(plata_e.id_plata, e_nume, e_suma, e_scad, e_cat, LocatiePlata(e_loc), ValutaPlata(e_val))
                st.session_state.toast_mesaj = "Actualizat!"
                st.rerun()
        if st.button("🗑️ Șterge plată", type="primary", use_container_width=True):
            mgr_plati.sterge_plata(plata_e.id_plata)
            st.rerun()

    # 6. AFIȘARE LISTA CARDURI (DESIGN PREMIUM)
    if not plati:
        st.info("Nicio factură găsită.")
    else:
        for p in plati:
            with st.container(border=True):
                col_nume, col_edit = st.columns([4, 1])
                with col_nume:
                    st.markdown(f"<div style='line-height: 1.2;'><div style='font-size: 1.4rem; font-weight: 800; color: #2e86c1;'>{p.nume_plata}</div><div style='font-size: 0.85rem; color: #7f8c8d; margin-top: 2px;'>📂 {p.categorie} | 📍 {p.locatie.value}</div></div>", unsafe_allow_html=True)
                with col_edit:
                    st.markdown("<div style='text-align: right;'>", unsafe_allow_html=True)
                    if st.button("✏️", key=f"e_{p.id_plata}"): modal_editare(p)
                    st.markdown("</div>", unsafe_allow_html=True)

                st.divider()
                c_suma, c_status, c_actiune = st.columns([1.4, 1.4, 1.2])
                c_suma.markdown(f"<div style='margin-top: 5px;'><span style='font-size: 1.3rem; font-weight: 700;'>{p.suma}</span> <span style='font-size: 0.9rem;'>{p.valuta.value}</span></div>", unsafe_allow_html=True)
                
                if p.status.value == "Achitat":
                    c_status.success("✅ ACHITAT")
                else:
                    zr = p.scadenta - ziua_azi
                    if zr < 0: c_status.error(f"🚨 -{abs(zr)} zile")
                    elif zr == 0: c_status.error("⚠️ AZI")
                    else: c_status.info(f"📅 Ziua {p.scadenta}")

                with c_actiune:
                    if p.status.value == "Neachitat":
                        if st.button("💸 Achită", key=f"py_{p.id_plata}", use_container_width=True, type="primary"):
                            mgr_plati.actualizeaza_status(p.id_plata, StatusPlata.ACHITAT)
                            s_ron = p.suma * mgr_plati.rate_valutare.get(p.valuta.value, 1)
                            mgr_tranz.adauga_tranzactie(s_ron, f"Factură: {p.nume_plata}", datetime.now().strftime("%d-%m-%Y"), TipTranzactie.CHELTUIALA)
                            st.rerun()
                    else:
                        if st.button("↩️ Anulează", key=f"un_{p.id_plata}", use_container_width=True):
                            mgr_plati.actualizeaza_status(p.id_plata, StatusPlata.NEACHITAT)
                            st.rerun()

# ==========================================
# 💰 PAGINA 3: PORTOFEL (Tranzacții Cashflow)
# ==========================================
elif meniu == "💰 Portofel (Cashflow)":
    st.header("💰 Portofelul Meu")
    st.write(f"**Sold Curent:** {mgr_tranz.calculeaza_sold():.2f} RON")
    
    with st.form("form_tranzactie"):
        c1, c2, c3 = st.columns(3)
        t_tip = c1.selectbox("Tip", ["Cheltuiala", "Venit", "Economii"]) # Adăugat Economii
        t_suma = c2.number_input("Suma (RON)", min_value=1.0)
        t_cat = c3.text_input("Detalii / Categorie")
        
        if st.form_submit_button("Înregistrează", use_container_width=True):
            if not t_cat: st.error("Completează categoria!")
            else:
                data_azi = datetime.now().strftime("%d-%m-%Y")
                tip_map = {"Venit": TipTranzactie.VENIT, "Cheltuiala": TipTranzactie.CHELTUIALA, "Economii": TipTranzactie.ECONOMII}
                mgr_tranz.adauga_tranzactie(t_suma, t_cat, data_azi, tip_map[t_tip])
                st.session_state.toast_mesaj = f"{t_tip} înregistrat!"
                st.rerun()

    st.subheader("Istoric Tranzacții")
    if not mgr_tranz.lista_tranzactii:
        st.info("Nicio tranzacție.")
    else:
        for t in reversed(mgr_tranz.lista_tranzactii):
            with st.container(border=True):
                col_i, col_d = st.columns([4, 1])
                culoare = "green" if t.tip == TipTranzactie.VENIT else "blue" if t.tip == TipTranzactie.ECONOMII else "red"
                semn = "+" if t.tip == TipTranzactie.VENIT else "🔒" if t.tip == TipTranzactie.ECONOMII else "-"
                
                col_i.markdown(f"**[{t.tip.value}] {t.categorie}** <br> <span style='color: gray; font-size: 0.8em;'>{t.data}</span>", unsafe_allow_html=True)
                col_d.markdown(f"<div style='text-align:right; font-weight: bold; color: {culoare};'>{semn}{t.suma}</div>", unsafe_allow_html=True)
                
                if col_d.button("🗑️", key=f"del_t_{t.id_tranzactie}"):
                    mgr_tranz.sterge_tranzactie(t.id_tranzactie)
                    st.rerun()
