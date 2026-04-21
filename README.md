# ₿ BTC IT Tax Calculator - Analizzatore Fiscale Bitcoin

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI Status](https://img.shields.io/badge/build-passing-brightgreen.svg)](https://github.com/)

BTC IT Tax Calculator è un'applicazione Python locale che analizza la cronologia on-chain di portafogli Bitcoin (tramite indirizzi singoli o chiavi estese xPub/yPub/zPub). 
Il software scarica i tassi storici e genera automaticamente le simulazioni per la dichiarazione dei redditi italiana, compilando il Quadro RW (patrimonio/IVCA) e il Quadro RT (plusvalenze LIFO).
Progettato per essere veloce, sicuro (local-first, nessun dato salvato in cloud) e costantemente allineato alla normativa fiscale vigente.

---

## ⚠️ DISCLAIMER IMPORTANTE (LEGGERE PRIMA DELL'USO)

1. **Sviluppo tramite AI:** Questo software è stato ideato e generato con l'ausilio di **Google Gemini AI**.
2. **Pubblico Dominio & Nessuna Garanzia:** Il codice è open source e fornito "così com'è". Può contenere bug, errori di rete o logiche di calcolo imprecise.
3. **Esenzione di Responsabilità:** Gli autori e l'intelligenza artificiale non si assumono **alcuna responsabilità** per sanzioni fiscali, perdite finanziarie o dichiarazioni errate derivanti dall'uso di questo strumento.
4. **Obbligo di Consulenza:** Questo software produce esclusivamente *stime matematiche*. **Devi SEMPRE consultare un commercialista qualificato** prima di inviare la tua dichiarazione dei redditi.

---

## 💻 Requisiti di sistema

* **Sistema Operativo:** Windows, macOS, Linux
* **Python:** Versione 3.8 o superiore installata sul sistema
* **Rete:** Connessione Internet attiva (per interrogare la blockchain e i tassi di cambio su Yahoo Finance)

---

## 🛠️ Installazione

L'installazione è progettata per completarsi in meno di 2 minuti. Apri il terminale e digita:

1. **Clona o scarica il repository:**
   ```bash
   git clone https://github.com/alvioinsights/BTC-IT-Tax-Calculator.git
   cd BTC-IT-Tax-Calculator
   ```

2. **Crea e attiva un ambiente virtuale (Consigliato):**
   ```bash
   python -m venv venv
   # Su Windows:
   venv\Scripts\activate
   # Su macOS/Linux:
   source venv/bin/activate
   ```

3. **Installa le dipendenze necessarie:**
   ```bash
   pip install streamlit pandas requests aiohttp yfinance bip_utils urllib3
   ```

---

## 🚀 Quickstart (Inizia in 5 minuti)

1. Avvia l'interfaccia grafica direttamente dal tuo terminale:
   ```bash
   streamlit run main.py
   ```
2. Si aprirà automaticamente una finestra nel browser all'indirizzo `http://localhost:8501`.
3. Scorri il disclaimer rosso iniziale e spunta la casella *"Dichiaro di aver letto e compreso..."*.
4. Inserisci un indirizzo Bitcoin reale per testarlo (es. l'indirizzo genesi di Satoshi: `1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa` o una tua chiave `zpub`).
5. Clicca su **"🔍 Avvia Analisi"** e attendi il completamento della scansione asincrona.
6. Seleziona l'Anno d'Imposta dal menu a tendina (es. 2024, 2025 o 2026) e osserva i Quadri RW e RT calcolarsi all'istante con le aliquote corrette!

---

## 📂 Struttura del Progetto

```text
BTC-IT-Tax-Calculator/
│
├── main.py               # Script principale (Interfaccia UI, motore LIFO e API asincrone)
├── README.md             # Questo file di documentazione
└── requirements.txt      # Elenco librerie per l'installazione automatica
```
*Nota: Il codice logico è stato volutamente racchiuso in un singolo file (`main.py`) per facilitare la revisione di sicurezza (Zero-Trust) da parte degli utenti, garantendo la massima trasparenza su come vengono trattate le chiavi pubbliche.*

---

## 🤝 Come Contribuire (Open Source)

I contributi per supportare altre chain (Ethereum, Solana) o per permettere l'importazione di CSV dagli exchange sono i benvenuti!

1. Fai un **Fork** del repository.
2. Crea un branch per la tua feature (`git checkout -b feature/NuovaFunzione`).
3. Esegui le modifiche e fai il commit (`git commit -m 'Aggiunta NuovaFunzione'`).
4. Fai il push sul branch (`git push origin feature/NuovaFunzione`).
5. Apri una **Pull Request** spiegando chiaramente le modifiche apportate.

*Importante: Poiché questo software tratta materie fiscali, ogni PR riguardante logiche di calcolo deve includere un riferimento normativo (es. circolare Agenzia delle Entrate o articoli di legge) nella descrizione.*

---

## ⚖️ Licenza

Questo progetto è distribuito sotto licenza **MIT**. 
Sei libero di usarlo, modificarlo e distribuirlo per uso personale o commerciale. Assicurati di includere il file `LICENSE` nel tuo progetto.

<div align="center">
  <p style="color: gray; font-size: 0.9em;">
    Ideato da <a href="https://alvioinsights.com" target="_blank" style="color: #4CAF50; text-decoration: none; font-weight: bold;">Alvioinsights.com</a> e sviluppato con l'ausilio di Google Gemini AI.
  </p>
</div>
```
