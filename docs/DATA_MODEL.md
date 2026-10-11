# Rozhodnutí prvního přehledu

Datovým základem je SQLite s číslovanými migracemi a cizími klíči. `vehicles` používá stálé UUID a zachovává migrační ID. `sources` je katalog původu. `records` uchovává jednotlivé pojistné položky, operace, pořízení, odečty, jízdy, úkoly a zdrojová pozorování; referenční pole vážou vozidla a zdroje, původní JSON zachovává přesné neznámé i rozporné hodnoty. Rozšíření do samostatných tabulek dalších domén a PostgreSQL není předstíráno.

`imports` je staging s reportem a rozhodnutím; `snapshots` uchovává úplné neměnné revize. Doménový migrační klíč pojistné položky zabraňuje duplicitě při opakování snímku. Přímý import nového PDF nebo XLSX není implementován; nesmí se obcházet klíč vložením další položky.

`manual_readings` a `issue_updates` jsou oddělené od importovaných tvrzení. `audit_log` zaznamenává všechny změny provedené aplikací. Uzavření úkolu je doložené ruční rozhodnutí správce; backend kontroluje povinné metadatové důkazy a požadovaný typ. Nemůže sám posoudit pravost externího dokumentu.

Peněžní kontrolní součty se počítají pomocí `Decimal`. Aktuální dluh, účinnost krytí a vlastnictví se z historické tabulky neodvozují. Fakturované čtvrtletí není interval krytí, `null` km limit není neomezený, rok 2024 není současná smlouva, pořizovací cena bez měny se nezobrazuje v CZK. Prodané záznamy a plán zůstávají oddělené od kandidátního současného majetku.

Datum zdroje, odečtu, evidence a jejího ručního uzavření jsou samostatná data. UI používá české formátování a Europe/Paris; časové audity jsou UTC. Výchozí datum není pevně nastavené na den migračního snímku.

Autorizace této verze je jednouživatelská. Heslo je hashované scrypt, token relace je náhodný a databáze uchovává pouze jeho hash. Relace trvá 12 hodin. Citlivé odpovědi mají `no-store`; web nemá externí fonty, trackery, veřejné datové soubory ani offline cache citlivých odpovědí.

Připojení Google/registr/ceny jsou explicitně vypnutá a uvádějí důvod. Tato verze neobsahuje periodické joby ani odesílání upozornění; přehled úkolů se počítá po přihlášení z databáze. Produkční plánovač, outbox, platební alokace, cenový pilot a firemní oprávnění patří do dalšího vývoje.
