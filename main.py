import asyncio
import calendar
import datetime
import hashlib
import time
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import pandas as pd
import requests
import streamlit as st
import urllib3
import yfinance as yf
from bip_utils import (
    Bip32Slip10Secp256k1,
    P2PKHAddrEncoder,
    P2SHAddrEncoder,
    P2WPKHAddrEncoder,
)

# Disabilita gli avvisi noiosi di sicurezza SSL nel terminale nero
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- COSTANTI GLOBALI ---
BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
MAGIC_XPUB = b"\x04\x88\xb2\x1e"
DEPTH_ACCOUNT = b"\x03"

# ==========================================
# 1. MODULO CRITTOGRAFIA E CHIAVI
# ==========================================

def decode_base58(payload: str) -> bytes:
    decimal_value = 0
    for char in payload:
        decimal_value = decimal_value * 58 + BASE58_ALPHABET.index(char)
    
    hex_str = f"{decimal_value:x}"
    if len(hex_str) % 2:
        hex_str = "0" + hex_str
    result_bytes = bytes.fromhex(hex_str)
    
    pad_count = 0
    for char in payload:
        if char == BASE58_ALPHABET[0]:
            pad_count += 1
        else:
            break
            
    return b"\x00" * pad_count + result_bytes


def encode_base58(payload: bytes) -> str:
    decimal_value = int.from_bytes(payload, "big")
    chars =[]
    while decimal_value > 0:
        decimal_value, remainder = divmod(decimal_value, 58)
        chars.append(BASE58_ALPHABET[remainder])
    result_str = "".join(chars[::-1])
    
    pad_count = 0
    for byte in payload:
        if byte == 0:
            pad_count += 1
        else:
            break
            
    return (BASE58_ALPHABET[0] * pad_count) + result_str


def patch_extended_public_key(ext_key_str: str) -> str:
    decoded = decode_base58(ext_key_str)
    raw_key_data = decoded[:-4]
    new_raw_data = MAGIC_XPUB + DEPTH_ACCOUNT + raw_key_data[5:]
    hash1 = hashlib.sha256(new_raw_data).digest()
    hash2 = hashlib.sha256(hash1).digest()
    new_checksum = hash2[:4]
    return encode_base58(new_raw_data + new_checksum)


def derive_addresses_from_extended_key(
    ext_key_str: str, change_type: int, start_index: int = 0, count: int = 10
) -> List[str]:
    derived_addresses =[]
    key_prefix = ext_key_str[:4].lower()
    
    try:
        patched_key = patch_extended_public_key(ext_key_str)
        bip32_ctx = Bip32Slip10Secp256k1.FromExtendedKey(patched_key)
        
        for index in range(start_index, start_index + count):
            derived_ctx = bip32_ctx.DerivePath(f"{change_type}/{index}")
            pub_key_bytes = derived_ctx.PublicKey().RawCompressed().ToBytes()
            
            if key_prefix in["zpub", "vpub"]:
                address = P2WPKHAddrEncoder.EncodeKey(pub_key_bytes, hrp="bc")
            elif key_prefix in["ypub", "upub"]:
                address = P2SHAddrEncoder.EncodeKey(pub_key_bytes)
            else:
                address = P2PKHAddrEncoder.EncodeKey(pub_key_bytes)
                
            derived_addresses.append(address)
            
        return derived_addresses
    except Exception as e:
        st.error(f"Errore critico nella derivazione: {e}")
        return[]

# ==========================================
# 2. MODULO ASINCRONO E DATA FETCHING
# ==========================================

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_daily_btc_eur_prices() -> Optional[Dict[datetime.date, float]]:
    try:
        btc_ticker = yf.Ticker("BTC-EUR")
        history_df = btc_ticker.history(period="max")
        
        if history_df is None or history_df.empty:
            return None
            
        history_df.reset_index(inplace=True)
        history_df["Date_Only"] = pd.to_datetime(history_df["Date"], utc=True).dt.date
        prices_dict = dict(zip(history_df["Date_Only"], history_df["Close"]))
        return prices_dict
    except Exception as e:
        print(f"Errore yfinance: {e}")
        return None


def get_closest_historical_price(target_date: datetime.date, prices_dict: Dict[datetime.date, float]) -> float:
    for day_offset in range(5):
        search_date = target_date - datetime.timedelta(days=day_offset)
        if search_date in prices_dict:
            return prices_dict[search_date]
    return 0.0


async def fetch_mempool_tx_async(
    addr: str, semaphore: asyncio.Semaphore
) -> Tuple[str, List[Dict[str, Any]]]:
    url = f"https://mempool.space/api/address/{addr}/txs"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    async with semaphore:
        for attempt in range(5):
            try:
                response = await asyncio.to_thread(
                    requests.get, url, headers=headers, timeout=15, verify=False
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return addr, (data if isinstance(data, list) else[])
                elif response.status_code == 429:
                    print(f"[{addr[:8]}] Rate limit API. Attesa...")
                    await asyncio.sleep(2 + attempt) 
                    continue
                else:
                    print(f"[{addr[:8]}] Blocco server: Status {response.status_code}")
                    return addr,[]
            except Exception as e:
                print(f"[{addr[:8]}] Eccezione di rete: {e}")
                await asyncio.sleep(1)
                continue
                
    return addr,[]


async def scan_addresses_async(
    addresses: List[str], progress_bar: Any, debug_text: Any
) -> List[Tuple[str, List[Dict[str, Any]]]]:
    semaphore = asyncio.Semaphore(5)
    results =[]
    
    tasks =[fetch_mempool_tx_async(addr, semaphore) for addr in addresses]
    completed = 0
    total = len(addresses)

    for coro in asyncio.as_completed(tasks):
        addr, tx_data = await coro
        results.append((addr, tx_data))
        completed += 1
        progress_bar.progress(completed / total)
        debug_text.markdown(f"⏳ **Scansione in corso:** Elaborati {completed}/{total} indirizzi...")
            
    return results


def calculate_net_btc_for_address(transaction: Dict[str, Any], address: str) -> float:
    net_satoshis = 0
    for vin in transaction.get("vin",[]):
        if vin.get("prevout", {}).get("scriptpubkey_address") == address:
            net_satoshis -= vin["prevout"]["value"]
            
    for vout in transaction.get("vout",[]):
        if vout.get("scriptpubkey_address") == address:
            net_satoshis += vout["value"]
            
    return net_satoshis / 100_000_000

# ==========================================
# 3. MODULO FISCALITÀ (RW & LIFO)
# ==========================================

def calculate_rw_data(
    tax_year: int, df_grouped: pd.DataFrame, historical_prices: Dict[datetime.date, float]
) -> Tuple[float, float, int, float, Optional[float], Optional[datetime.date], Optional[datetime.date]]:
    jan_1st = datetime.date(tax_year, 1, 1)
    dec_31st = datetime.date(tax_year, 12, 31)
    days_in_year = 366 if calendar.isleap(tax_year) else 365

    price_jan1 = get_closest_historical_price(jan_1st, historical_prices)
    price_dec31 = get_closest_historical_price(dec_31st, historical_prices)

    df_tax_year = df_grouped[df_grouped["date_only"] <= dec_31st].copy()

    if df_tax_year.empty:
        return 0.0, 0.0, 0, 0.0, None, None, None

    df_before_jan1 = df_tax_year[df_tax_year["date_only"] < jan_1st]
    balance_jan1 = df_before_jan1["cumulative_btc"].iloc[-1] if not df_before_jan1.empty else 0.0
    
    df_tax_year_only = df_tax_year[df_tax_year["date_only"] >= jan_1st]
    daily_changes = df_tax_year_only.groupby("date_only")["net_btc"].sum().to_dict()
    
    current_balance = balance_jan1
    giorni_possesso = 0
    last_day_with_balance = None
    balance_before_emptying = 0.0

    for i in range(days_in_year):
        day = jan_1st + datetime.timedelta(days=i)
        start_of_day_balance = current_balance
        
        if day in daily_changes:
            current_balance += daily_changes[day]
            
        end_of_day_balance = current_balance
        
        if start_of_day_balance > 1e-8 or end_of_day_balance > 1e-8 or day in daily_changes:
            giorni_possesso += 1
            last_day_with_balance = day
            
            if end_of_day_balance > 1e-8:
                balance_before_emptying = end_of_day_balance
            elif start_of_day_balance > 1e-8:
                balance_before_emptying = start_of_day_balance
            else:
                balance_before_emptying = abs(daily_changes[day]) 
    
    first_price = None
    first_date = None

    if balance_jan1 > 1e-8:
        valore_iniziale = balance_jan1 * price_jan1
    elif not df_tax_year_only.empty:
        first_date = df_tax_year_only["date_only"].iloc[0]
        first_btc_amount = abs(df_tax_year_only["net_btc"].iloc[0])
        first_price = get_closest_historical_price(first_date, historical_prices)
        valore_iniziale = first_btc_amount * first_price 
    else:
        valore_iniziale = 0.0

    if last_day_with_balance is None:
        valore_finale = 0.0
        ivca = 0.0
    else:
        if last_day_with_balance == dec_31st and current_balance > 1e-8:
            valore_finale = current_balance * price_dec31
        else:
            price_end = get_closest_historical_price(last_day_with_balance, historical_prices)
            valore_finale = balance_before_emptying * price_end
            
        ivca = valore_finale * 0.002 * (giorni_possesso / days_in_year)
    
    return valore_iniziale, valore_finale, giorni_possesso, ivca, first_price, first_date, last_day_with_balance


def process_lifo_sale(inventory: List[Dict[str, Any]], qty_to_sell: float) -> float:
    cost_basis = 0.0
    margin_of_error = 1e-8
    
    while qty_to_sell > margin_of_error and inventory:
        last_in = inventory[-1]
        if last_in["amount"] <= qty_to_sell:
            cost_basis += last_in["amount"] * last_in["price"]
            qty_to_sell -= last_in["amount"]
            inventory.pop()
        else:
            cost_basis += qty_to_sell * last_in["price"]
            last_in["amount"] -= qty_to_sell
            qty_to_sell = 0.0
    return cost_basis


def calculate_lifo_gains(df_grouped: pd.DataFrame, historical_prices: Dict[datetime.date, float]) -> pd.DataFrame:
    inventory: List[Dict[str, Any]] =[]
    taxable_events =[]
    df_sorted = df_grouped.sort_values(by="date_time").copy()
    
    for _, row in df_sorted.iterrows():
        date = row["date_only"]
        amount = row["net_btc"]
        txid = row["txid"]
        price = get_closest_historical_price(date, historical_prices)
        
        if amount > 0:
            inventory.append({"amount": amount, "price": price, "date": date})
        elif amount < 0:
            qty_to_sell = abs(amount)
            sell_value = qty_to_sell * price
            cost_basis = process_lifo_sale(inventory, qty_to_sell)
            gain_loss = sell_value - cost_basis
            
            taxable_events.append({
                "Anno": date.year,
                "Data Operazione": date,
                "TXID": txid,
                "BTC Ceduti": abs(amount),
                "Prezzo Riferimento (€)": price,
                "Valore Uscita (€)": sell_value,
                "Costo di Carico (€)": cost_basis,
                "Plus/Minusvalenza (€)": gain_loss
            })
    return pd.DataFrame(taxable_events)

# ==========================================
# 4. ORCHESTRAZIONE APP (STREAMLIT)
# ==========================================

def initialize_session_state() -> None:
    if "dati_caricati" not in st.session_state:
        st.session_state.dati_caricati = False
    if "df_grouped" not in st.session_state:
        st.session_state.df_grouped = None
    if "historical_prices" not in st.session_state:
        st.session_state.historical_prices = None
    if "lifo_results" not in st.session_state:
        st.session_state.lifo_results = None


def perform_wallet_scan(input_data: str, scan_limit: int) -> Tuple[List[Dict[str, Any]], List[str]]:
    processed_transactions = []
    addresses_to_check =[]
    
    if input_data.startswith(("xpub", "ypub", "zpub", "vpub", "upub", "tpub")):
        receiving_addrs = derive_addresses_from_extended_key(input_data, 0, 0, scan_limit)
        change_addrs = derive_addresses_from_extended_key(input_data, 1, 0, scan_limit)
        addresses_to_check = receiving_addrs + change_addrs
        if not addresses_to_check:
            st.error("Impossibile derivare gli indirizzi. Chiave errata o non supportata.")
            return [],[]
    else:
        addresses_to_check =[input_data]

    st.info(f"👁️ Scansione asincrona su **{len(addresses_to_check)}** indirizzi in corso...")
    progress_bar = st.progress(0)
    debug_text = st.empty()
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        results = loop.run_until_complete(scan_addresses_async(addresses_to_check, progress_bar, debug_text))
    finally:
        loop.close()
        
    debug_text.empty()
    progress_bar.empty()

    for addr, tx_data in results:
        if tx_data:
            if len(addresses_to_check) > 1:
                st.toast(f"✅ Trovate {len(tx_data)} transazioni su {addr[:8]}...")
            for tx in tx_data:
                net_btc = calculate_net_btc_for_address(tx, addr)
                if net_btc != 0:
                    is_confirmed = tx.get("status", {}).get("confirmed")
                    tx_date_obj = (datetime.datetime.fromtimestamp(tx["status"]["block_time"]) 
                                   if is_confirmed else datetime.datetime.now())
                    processed_transactions.append({
                        "txid": tx["txid"],
                        "date_time": tx_date_obj.strftime("%Y-%m-%d %H:%M:%S"),
                        "date_only": tx_date_obj.date(),
                        "net_btc": net_btc,
                    })
                    
    return processed_transactions, addresses_to_check


def main() -> None:
    st.set_page_config(page_title="BTC IT Tax Calculator", page_icon="₿", layout="wide")
    st.markdown("""
        <style>
        div[data-testid="metric-container"] { background-color: #f0f2f6; border-radius: 10px; padding: 15px; border: 1px solid #e0e0e0; }
        .rw-box { background-color: #e8f4f8; padding: 20px; border-radius: 10px; border-left: 5px solid #0078D7; margin: 20px 0; }
        .rt-box { background-color: #fdf5e6; padding: 20px; border-radius: 10px; border-left: 5px solid #f39c12; margin: 20px 0; }
        </style>
    """, unsafe_allow_html=True)

    st.title("₿ BTC IT Tax Calculator")
    st.subheader("Moduli Automatici: Quadro RW (IVCA) e Quadro RT (Plusvalenze LIFO)")

    initialize_session_state()

    # --- SEZIONE DISCLAIMER OBBLIGATORIO ---
    with st.expander("⚖️ TERMINI E CONDIZIONI D'USO (Disclaimer Legale e Fiscale)", expanded=False):
        st.markdown("""
        **⚠️ ATTENZIONE: LEGGERE PRIMA DELL'USO**
        * **Scopo informativo:** Questo software è uno strumento di utilità sperimentale generato con l'ausilio di intelligenza artificiale. Ha uno scopo puramente informativo e di supporto al calcolo.
        * **Nessuna consulenza:** I risultati generati (Quadri RW e RT) sono stime algoritmiche basate su dati pubblici (blockchain e Yahoo Finance). Questo strumento **non sostituisce in alcun modo la consulenza di un commercialista** o di un professionista fiscale abilitato.
        * **Limiti dell'analisi On-Chain:** Il software non può distinguere tra una transazione verso terzi (vendita/tassabile) e un giroconto verso un proprio conto exchange (non tassabile). L'utente è l'unico responsabile della verifica e della cernita dei movimenti in uscita esportati in CSV.
        * **Esclusione di responsabilità:** Il software è fornito "così com'è". Gli ideatori e gli sviluppatori declinano ogni responsabilità per eventuali bug, calcoli imprecisi, sanzioni fiscali o perdite finanziarie derivanti dall'utilizzo di questi dati.
        * **Privacy:** L'elaborazione avviene localmente sul tuo dispositivo. I dati non vengono salvati su server esterni. **NON INSERIRE MAI SEED PHRASE O CHIAVI PRIVATE.**
        """)
    
    st.markdown("<br>", unsafe_allow_html=True)
    # Checkbox che agisce da sblocco per il pulsante
    accetto_disclaimer = st.checkbox("Dichiaro di aver letto e compreso il Disclaimer e accetto di usare i dati sotto la mia esclusiva responsabilità.", value=False)
    st.markdown("<br>", unsafe_allow_html=True)

    # --- INPUT ---
    with st.container():
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            input_data = st.text_input("Indirizzo o xPub/yPub/zPub:", placeholder="es. zpub6rFR...")
        with col2:
            scan_limit = st.number_input("Profondità (Gap Limit):", min_value=10, max_value=200, value=20, step=10)
        with col3:
            st.write("") 
            st.write("")
            # Il pulsante è abilitato SOLO se la checkbox è spuntata (accetto_disclaimer == True)
            analyze_btn = st.button("🔍 Avvia Analisi", use_container_width=True, type="primary", disabled=not accetto_disclaimer)

    st.divider()

    if analyze_btn:
        clean_input = input_data.strip()
        if not clean_input:
            st.warning("⚠️ Inserisci un indirizzo o una chiave pubblica.")
            st.stop()

        with st.status("Analisi Blockchain in corso...", expanded=True) as status:
            historical_prices = fetch_daily_btc_eur_prices()
            if not historical_prices:
                status.update(label="Errore Critico: API Finanziaria Fallita", state="error")
                st.error("🚨 BLOCCO DI SICUREZZA: Impossibile scaricare i tassi di cambio storici.")
                st.stop()

            raw_txs, addresses = perform_wallet_scan(clean_input, scan_limit)
            status.update(label="Scansione asincrona completata!", state="complete", expanded=False)

        if not raw_txs:
            st.error("🚨 Nessuna transazione trovata. Prova ad aumentare il Gap Limit.")
            st.session_state.dati_caricati = False 
        else:
            df = pd.DataFrame(raw_txs)
            df_grouped = df.groupby(["txid", "date_time", "date_only"]).agg({"net_btc": "sum"}).reset_index()
            df_grouped = df_grouped[abs(df_grouped["net_btc"]) > 1e-5].sort_values(by="date_time")
            df_grouped["cumulative_btc"] = df_grouped["net_btc"].cumsum().round(8)
            
            lifo_df = calculate_lifo_gains(df_grouped, historical_prices)
            
            st.session_state.df_grouped = df_grouped
            st.session_state.historical_prices = historical_prices
            st.session_state.lifo_results = lifo_df
            st.session_state.dati_caricati = True

    if st.session_state.dati_caricati:
        df_grouped = st.session_state.df_grouped
        historical_prices = st.session_state.historical_prices
        lifo_df = st.session_state.lifo_results

        min_date = df_grouped["date_only"].min().strftime("%d/%m/%Y")
        max_date = df_grouped["date_only"].max().strftime("%d/%m/%Y")
        st.success(f"✅ Dati in memoria. Storico dal **{min_date}** al **{max_date}**.")

        current_year = datetime.datetime.now().year
        st.markdown("### 🗓️ Configurazione Dichiarazione")
        tax_year = st.selectbox(
            "Seleziona l'Anno d'Imposta:", 
            options=[current_year, current_year - 1, current_year - 2, current_year - 3, current_year - 4, current_year - 5], 
            index=0
        )

        # === SEZIONE RW ===
        st.header(f"1. Quadro RW - Monitoraggio (Anno {tax_year})")
        val_iniziale, val_finale, giorni, ivca, p_inizio, d_inizio, d_fine = calculate_rw_data(tax_year, df_grouped, historical_prices)

        if giorni == 0:
            st.info(f"💡 Nel {tax_year} il saldo è rimasto a zero. Nessun RW da compilare.")
        else:
            st.markdown('<div class="rw-box">', unsafe_allow_html=True)
            
            box_title = f"### 📝 Dati Quadro RW ({tax_year})"
            if d_inizio and d_inizio > datetime.date(tax_year, 1, 1):
                box_title += " - *Aperto in corso d'anno*"
            if d_fine and d_fine < datetime.date(tax_year, 12, 31):
                box_title += " - *Dismesso in corso d'anno*"
            st.markdown(box_title)
            
            rw_data = {
                "Col. 1 (Titolo)":["1 (Proprietà)"], "Col. 3 (Codice)":["21 (Cripto)"],
                "Col. 5 (Quota %)":["100"], "Col. 6 (Criterio)":["1 (Mercato)"],
                "Col. 7 (Val Inizio)":[f"€ {val_iniziale:,.0f}"], "Col. 8 (Val Fine)":[f"€ {val_finale:,.0f}"],
                "Col. 10 (Giorni)":[str(giorni)], "Col. 33 (IVCA)":[f"€ {ivca:,.0f}"]
            }
            st.dataframe(pd.DataFrame(rw_data), hide_index=True)
            
            if ivca < 12:
                st.success("💡 IVCA < 12€. L'imposta non si versa (ma il quadro va compilato).")
            else:
                st.warning(f"⚠️ **IVCA da versare:** € {ivca:,.0f}")
            st.markdown('</div>', unsafe_allow_html=True)

        # === SEZIONE RT ===
        st.header(f"2. Quadro RT - Plusvalenze (LIFO - {tax_year})")
        st.markdown("⚠️ Seleziona dal file esportato le uscite *realmente* tassabili (escludi giroconti).")
        
        lifo_year = lifo_df[lifo_df["Anno"] == tax_year].copy()
        
        if lifo_year.empty:
            st.info(f"💡 Nessuna cessione rilevata nel {tax_year}. Quadro RT non necessario.")
        else:
            styled_lifo = lifo_year[["Data Operazione", "BTC Ceduti", "Valore Uscita (€)", "Costo di Carico (€)", "Plus/Minusvalenza (€)", "TXID"]].style.format({
                "BTC Ceduti": "{:.8f}", "Valore Uscita (€)": "€ {:.2f}", "Costo di Carico (€)": "€ {:.2f}", "Plus/Minusvalenza (€)": "€ {:.2f}"
            }).map(lambda val: "color: green" if val > 0 else "color: red", subset=["Plus/Minusvalenza (€)"])
            
            st.dataframe(styled_lifo, use_container_width=True, hide_index=True)
            
            tot_plus_minus = lifo_year["Plus/Minusvalenza (€)"].sum()
            franchigia = 2000.0 if tax_year == 2024 else 0.0
            aliquota = 0.33 if tax_year >= 2026 else 0.26
            
            if tax_year == 2025:
                st.info("ℹ️ **Nota 2025:** Ricorda l'eventuale affrancamento al 01/01/2025.")
            elif tax_year < 2024:
                st.warning("⚠️ Per anni < 2024 (Soglia 51k), i calcoli base omettono la vecchia franchigia mobile.")
                
            imponibile = max(0, tot_plus_minus - franchigia) if tot_plus_minus > 0 else 0
            imposta_dovuta = imponibile * aliquota
            
            st.markdown('<div class="rt-box">', unsafe_allow_html=True)
            st.markdown(f"### 🧮 Simulazione Fiscale {tax_year} (Franchigia: **€{franchigia}** | Aliquota: **{aliquota*100}%**)")
            col_rt1, col_rt2, col_rt3 = st.columns(3)
            col_rt1.metric("Risultato Netto Uscite", f"€ {tot_plus_minus:,.2f}")
            col_rt2.metric("Imponibile Deducendo Franchigia", f"€ {imponibile:,.2f}")
            col_rt3.metric("Imposta Sostitutiva Stimata", f"€ {imposta_dovuta:,.2f}")
            st.markdown('</div>', unsafe_allow_html=True)

            st.download_button(
                label=f"⬇️ Scarica Tabella Plusvalenze {tax_year} (CSV)",
                data=lifo_year.to_csv(index=False).encode("utf-8"),
                file_name=f"Quadro_RT_{tax_year}_LIFO.csv",
                mime="text/csv",
            )

    # --- FOOTER ---
    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; padding: 10px; color: gray;'>"
        "Ideato da <a href='https://alvioinsights.com' target='_blank' style='text-decoration: none; color: #4CAF50; font-weight: bold;'>Alvioinsights.com</a> "
        "e sviluppato con Google Gemini AI"
        "</div>",
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()