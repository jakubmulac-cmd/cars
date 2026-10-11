# Cars · soukromý přehled vozového parku

Česká responzivní aplikace pro evidenci vozidel, dohledání podkladů, kontrolu pojistných předpisů a správu ověřovacích úkolů. Importovaná tvrzení jsou oddělena od aktuálně ověřených skutečností. Osobní data nejsou součástí tohoto repozitáře.

## Co tato verze umí

- Přihlášení jedním správcovským heslem, vytvořeným při prvním místním otevření. Server kontroluje přístup ke všem datovým endpointům i exportům.
- Přehled vozidel, vyhledávání podle názvu/RZ/VIN a filtry podle evidenčního stavu a majitele ve zdroji.
- Detail identity, vlastnictví podle podkladů, STK, servisu, pořízení, historie km, pojištění a zdrojových tvrzení.
- Předpisy po vozidlech a historická rekapitulace pojištění; fakturované období neukončuje smlouvu. Neověřená úhrada není označena jako současný dluh.
- Přiřazení odpovědné osoby, uzavření úkolu s požadovaným druhem důkazu, jeho názvem, odkazem, datem a vysvětlením; změny mají auditní historii.
- Ruční odečty s datem a původem, zachování původní historie.
- Validace JSON Schema, kontrola referencí a přesných finančních součtů, staging s náhledem, transakční opakovatelný import bez duplicit a soukromý export.
- Přehled nepřipojených zdrojů. Google, registr a cenové zdroje se bez oprávnění nedotazují a nevytvářejí fiktivní výsledky.

Jde o **první soukromý přehled**, nikoli celý automatizovaný systém z širšího návrhu. Bankovní párování a alokace plateb, plánovač a doručování upozornění, automatické externí adaptéry, cenová pipeline, více uživatelů a firemní role vyžadují další implementaci. Graf cen má poctivý prázdný stav; žádné ceny uživatelova majetku nejsou vymyšlené. Potvrzení úkolu správcem není automatickou validací obsahu dokladu.

## Spuštění

Pro spuštění přímo v prohlížeči na GitHubu použijte [návod pro Codespaces](docs/CODESPACES.md), včetně importu a řešení chyb.

Potřeba: Python 3.12 a `uv`. Závislosti jsou zamčené v `uv.lock`; samostatná kompilace frontendu není potřeba. Použijte stávající checkout; každá cloudová úloha je už izolovaná a další Git worktree není potřeba.

```bash
cd /workspace/cars
uv sync --frozen --cache-dir /workspace/.cache/uv
export FLEET_DATA_DIR=/workspace/fleet-private
.venv/bin/python -m uvicorn fleet.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers
```

Při prvním místním otevření vytvořte vlastní heslo dlouhé alespoň 12 znaků. V prostředí není společné ani přednastavené heslo. Živé procesy se mezi cloudovými úlohami nezachovávají; web je nutné znovu spustit. Pro jiný místní checkout vynechte export `FLEET_DATA_DIR` a použije se ignorovaný adresář `.local`.

`.env.example` popisuje proměnné; soubor `.env` se automaticky nenačítá. Exportujte potřebné hodnoty v shellu nebo nastavte prostředí služby. Soukromá databáze a vstupní dokumenty musí být na chráněném trvalém disku, mimo Git. SQLite slouží současné jednouživatelské aplikaci; pro více instancí a workerů je další etapou migrace na PostgreSQL.

## Import podkladů

V cloudovém prostředí je vstupní balíček uchován soukromě v `/workspace/fleet-private/import`; soubory obsahují osobní a obchodní informace. Jejich kontrolní součty byly ověřeny před importem. JSON schema bez skutečných dat je v repozitáři.

```bash
export FLEET_DATA_DIR=/workspace/fleet-private
# Náhled bez změny evidenčních záznamů:
.venv/bin/python -m fleet.importer /workspace/fleet-private/import/fleet_context_2026-10-11.json
# Potvrzení validovaného importu:
.venv/bin/python -m fleet.importer /workspace/fleet-private/import/fleet_context_2026-10-11.json --commit
```

Stejné dvě fáze jsou v obrazovce „Připojení a data“. Celý import je transakční: přerušení nezanechá polovinu dat. UUID je stálá identita; RZ, VIN a názvy zůstávají tvrzeními. Záznamy, zdroje i nezpracované buňky jsou zachovány spolu s neměnným úplným snímkem. Opakování stejného snímku nemění ruční odečty ani uzavření a odpovědné osoby úkolů. Náhled neprovádí mazání. Nový obsah stejného záznamu je importovaná revize a starý snímek zůstává dohledatelný v databázi.

Při změně datového formátu nejdřív upravte schéma a importní pravidla. Přímé přepisování starých buněk či dokladů není součástí importu. Soukromý export slouží ke kontrole a přenosu celého stavu; není zaměnitelný za migrační vstupní JSON.

## Kontroly

```bash
# Přístup, hesla, cookie relace, omezení pokusů a ochrana požadavků:
.venv/bin/python -m unittest tests.test_app.AuthenticationTests -v
# Odpovědi přístupové brány a serverové chyby při importu (Node.js 18+):
node --test tests/test_api.mjs
# Všechny kontroly včetně skutečného snímku (data nepatří do Gitu):
FLEET_TEST_SNAPSHOT=/workspace/fleet-private/import/fleet_context_2026-10-11.json \
  .venv/bin/python -m unittest discover -v
```

Bez `FLEET_TEST_SNAPSHOT` se testy skutečného snímku výslovně přeskočí. Testy používají dočasné databáze; žádné testovací heslo, odečet ani uzavření úkolu se nevkládá do uživatelské databáze.

Volitelná kontrola v prohlížeči vyžaduje systémový Playwright a Chromium. Testuje dočasnou kopii databáze; snímky obrazovky ukládá **mimo repozitář** a mohou obsahovat soukromé informace.

```bash
python3 tests/browser_check.py --data-dir /workspace/fleet-private \
  --output /workspace/fleet-private/verification
```

## Záloha, obnova a změna hesla

Konzistentní záloha SQLite přes jeho online backup API, bez přepsání existujícího cíle:

```bash
FLEET_DATA_DIR=/workspace/fleet-private .venv/bin/python -m fleet.admin backup \
  /workspace/fleet-private/backups/fleet-backup.sqlite3
```

Záloha obsahuje soukromá data i hash hesla. Uchovávejte ji v chráněném úložišti. Obnova: zastavte vlastní službu, zachovejte současnou databázi a její WAL/SHM, vložte ověřenou zálohu jako `fleet.sqlite3` do datového adresáře s oprávněním 0600, poté službu spusťte a zkontrolujte přihlášení, záznamy a auditní historii. Neobnovujte databázi za běhu.

```bash
FLEET_DATA_DIR=/workspace/fleet-private .venv/bin/python -m fleet.admin password
```

Heslo se zadává místně skrytým vstupem; změna odhlásí všechny existující relace. Hesla nejsou v kódu ani nastavení cloudu.

## Vzdálené nasazení

Aktuální ověřené spuštění je místní a nevystavuje osobní data veřejnému internetu. Před vzdáleným nasazením nastavte správcovské heslo místně, HTTPS reverzní proxy, konkrétní `FLEET_ALLOWED_HOSTS`, `FLEET_SECURE_COOKIES=1`, trvalý chráněný disk a zálohy. Proxy musí zachovat origin/host; nepovolujte přepis IP nedůvěryhodnými forwarded headers. První založení správce není z cizí IP povoleno. Produkční dostupnost a nasazení na doméně nebyly součástí tohoto kroku.

Google originály vyžadují autorizaci příslušného účtu, registr příslušné oprávnění a tržní data povolený zdroj/licenci. Žádné klíče pro tento místní přehled nejsou potřeba a žádná data se neposílají AI službám, brokerům nebo jiným externím systémům.
