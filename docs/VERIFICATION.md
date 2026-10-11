# Ověření připraveného prostředí

Ověřeno 11. 10. 2026 v cloudovém prostředí s přiloženým soukromým datovým snímkem. Celý širší návrh automatizovaného monitoringu není implementován; rozsah této verze popisuje README.

- Kontrolní SHA-256 všech osmi souborů uvedených v přiloženém seznamu souhlasí; JSON Schema prošlo bez chyby.
- Import: 31 vozidel, 31 pojistných souhrnů, 14 položek pojistného, 105 odečtů, 63 jízd, 2 885 zdrojových pozorování, 38 úkolů a 21 zdrojů.
- Součty: Q4 53 847 CZK; zpětná položka 9 475; nový předpis 63 322; historicky požadováno 106 230; Triumph 19 818. Potvrzení připsání plateb zůstává neověřené.
- Všech **16 Python testů a 7 JavaScript testů prošlo**, včetně přístupových pravidel, opakovaného importu, rollbacku při přerušení, zachování původních tvrzení, oddělených identit, povinných metadat důkazu, ručních změn zachovaných po importu a srozumitelných chybových odpovědí. Žádný z těchto testů nebyl přeskočen při ověření této instance.
- Chromium: první nastavení přístupu, přihlášení, vyhledávání, čtyři záložky detailu, ruční odečet, přiřazení úkolu, pojistné součty, 21 zdrojů, nepřipojené integrace, opakovaný import, export a odhlášení prošly. Simulované odpovědi HTTP 413 a 500 zobrazily konkrétní chybu bez obsahu odpovědi a následné opakování skutečného importu prošlo. Ověřeno desktopové i mobilní zobrazení; bez JavaScriptových chyb.
- Instalační postup byl proveden dvakrát; druhý import nevytvořil duplicity. Služba se po zastavení a novém spuštění vrátila ke zdravému stavu. Databáze i konzistentní záloha prošly `integrity_check`.
- Testy běží na dočasných databázích. Skutečná uživatelská databáze nemá testovací heslo, odečty ani uměle uzavřené úkoly. Při prvním otevření se vytvoří vlastní heslo.

Připravenost se týká aktuálního místního vývojového workflow. Veřejné nasazení, publikace snapshotu prostředí a obnovení v nové cloudové úloze tímto reportem nejsou potvrzeny. Externí registry, pojišťovny a cenové zdroje nebyly živě dotazovány; automatické konektory jsou vypnuté.

Příčina uživatelem hlášené neplatné odpovědi při importu v jeho Codespaces není tímto místním ověřením potvrzena. Návod v `docs/CODESPACES.md` popisuje aktualizaci, diagnostiku a místní import bez přesměrovaného portu.
