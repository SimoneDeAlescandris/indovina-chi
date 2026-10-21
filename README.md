# Indovina Chi?

**Indovina Chi?** è un gioco multiplayer per browser ispirato al classico gioco da tavolo. Permette di sfidare gli amici online attraverso una connessione peer-to-peer (P2P), senza necessità di registrazione.

Il progetto è realizzato in HTML, CSS e JavaScript vanilla, con un'interfaccia responsive e diverse opzioni per personalizzare le partite.

## Funzionalità

- **Multiplayer P2P:** connessione tra giocatori tramite PeerJS e WebRTC.
- **Stanze private:** creazione di una stanza con codice da condividere con gli altri partecipanti.
- **Categorie di personaggi:** selezione tra YouTuber, personaggi dei videogiochi, Pokémon e modalità Mix.
- **Mazzo personalizzabile:** scelta del numero di personaggi da utilizzare, da un minimo di 24 fino al totale disponibile.
- **Generazioni Pokémon:** selezione di una o più generazioni, dalla prima alla nona.
- **Modalità Mix:** composizione casuale di un mazzo con personaggi di categorie differenti, con un limite massimo di sei Pokémon.
- **Regole configurabili:** scelta della penalità per un tentativo errato e possibilità di abilitare o disabilitare il Jolly.
- **Partite da 2 o 3 giocatori attivi:** l'Host decide il numero massimo di partecipanti attivi.
- **Modalità spettatore:** possibilità di ammettere spettatori, fino a un massimo di cinque utenti complessivi nella stanza.
- **Visuale regia:** gli spettatori possono selezionare un partecipante e osservare il suo tabellone e la sua carta segreta.
- **Contatore degli scarti:** visualizzazione del numero di carte abbassate da ciascun giocatore, senza rivelare gli scarti specifici.
- **Chat e risposte rapide:** comunicazione tra i partecipanti durante la partita.
- **Interfaccia responsive:** layout adattabile a desktop, tablet e smartphone.
- **Nessuna registrazione:** accesso tramite nome utente e codice stanza.

## Come giocare

### 1. Crea o raggiungi una stanza

Apri il sito, inserisci il tuo nome e scegli una delle seguenti opzioni:

- **Crea stanza:** diventi l'Host e configuri la partita.
- **Entra:** inserisci il codice della stanza condiviso dall'Host.

### 2. Configura la partita

Prima di creare la stanza, l'Host può scegliere:

- la categoria e il numero di personaggi;
- le generazioni Pokémon da includere;
- la penalità per un tentativo di vittoria errato;
- la disponibilità del Jolly;
- il numero massimo di giocatori attivi;
- se consentire l'ingresso degli spettatori.

Una volta creata la stanza, condividi il codice con gli amici.

### 3. Scegli la tua carta segreta

Ogni giocatore attivo seleziona una carta dal proprio tabellone e la conferma con il pulsante **Conferma carta segreta**.

La carta segreta deve rimanere sconosciuta agli avversari.

### 4. Fai domande ed elimina i sospetti

Durante il tuo turno, formula una domanda sulle caratteristiche del personaggio avversario. Le risposte previste sono **SÌ** e **NO**.

In base alla risposta, abbassa dal tuo tabellone le carte che ritieni di poter escludere. Il contatore degli scarti ti aiuta a monitorare i tuoi progressi.

Quando pensi di conoscere la carta segreta dell'avversario, utilizza **Tenta di indovinare**.

### 5. Attenzione alle impostazioni dell'Host

Un tentativo errato può avere due conseguenze:

- **Salta il Turno:** il turno passa al giocatore successivo e la partita continua.
- **Sconfitta Istantanea:** il tentativo errato conclude la partita.

La regola applicata è quella scelta dall'Host per la stanza.

### 6. Partecipa come spettatore

Se gli spettatori sono abilitati e gli slot disponibili lo consentono, puoi entrare nella stanza senza partecipare attivamente alla partita.

La modalità spettatore permette di seguire i turni, utilizzare la chat e aprire la visuale regia per osservare il tabellone e la carta segreta di un giocatore.

**Nota:** la visuale regia mostra informazioni riservate ai partecipanti attivi. Per mantenere il fair play, gli spettatori non devono comunicare tali informazioni ai giocatori.

## Tecnologie utilizzate

- **HTML5:** struttura della pagina.
- **CSS3:** layout, stili e interfaccia responsive.
- **JavaScript ES6 (Vanilla):** logica di gioco, gestione degli eventi e sincronizzazione dello stato.
- **[PeerJS](https://peerjs.com/):** gestione delle connessioni peer-to-peer tramite WebRTC.
- **[WebRTC](https://webrtc.org/):** tecnologia per la comunicazione in tempo reale tra browser.
- **[Google Fonts](https://fonts.google.com/):** font Fredoka.
- **[Canvas Confetti](https://github.com/catdad/canvas-confetti):** effetti grafici celebrativi.

Il progetto non richiede un backend applicativo proprietario da installare e gestire. La creazione delle stanze e la comunicazione dipendono tuttavia dai servizi PeerJS/WebRTC e dalle condizioni della rete utilizzata.

## Esecuzione locale

1. Clona il repository.
2. Avvia un server HTTP nella cartella del progetto:

   ```bash
   python -m http.server 8000
   ```

3. Apri `http://localhost:8000` nel browser.

## Pubblicazione

Il progetto può essere ospitato tramite [GitHub Pages](https://pages.github.com/).

## Licenza

Questo progetto è distribuito sotto licenza **MIT**. Consulta il file [`LICENSE`](LICENSE) per il testo completo della licenza.

La licenza del codice del progetto non implica automaticamente che le immagini, i loghi o gli altri asset di terze parti siano distribuiti con la stessa licenza.

## Disclaimer

*Indovina Chi?* è un progetto amatoriale indipendente, sviluppato a fini ricreativi e dimostrativi. Non è ufficiale, né affiliato, approvato o sponsorizzato da Hasbro, Inc.

Il nome *Indovina Chi?* è associato al marchio registrato dei rispettivi titolari. I nomi, i loghi, le immagini e gli altri contenuti di terze parti appartengono ai rispettivi proprietari.

L'utilizzo e la redistribuzione degli asset devono rispettare i diritti e le condizioni applicabili.