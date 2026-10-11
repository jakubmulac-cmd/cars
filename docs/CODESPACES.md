# Spuštění v GitHub Codespaces

Codespaces je jiné prostředí než původní cloudová instalace. Kód se stáhne z Gitu, ale osobní snímek, heslo a databázi je nutné připravit v tomto Codespace. Databáze je ve výchozím stavu v ignorovaném adresáři `.local`; nikdy ji ani původní JSON nepřidávejte do Gitu.

Otevřete Codespace na větvi `main` a jeho spodní Terminál. Výchozí pracovní adresář je `/workspaces/cars`.

## První příprava

```bash
python3 -m pip install --user uv
python3 -m uv sync --frozen
```

Při prvním použití zvolte heslo místně v Terminálu, ještě před otevřením webu. Nezadávejte jej do žádného příkazu ani do chatu:

```bash
python3 -m uv run python -m fleet.admin password
```

Tento příkaz změní heslo a odhlásí staré relace, proto jej neopakujte při běžném spouštění.

## Spuštění webu

```bash
export FLEET_ALLOWED_HOSTS="localhost,127.0.0.1,${CODESPACE_NAME}-8000.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
export FLEET_SECURE_COOKIES=1
python3 -m uv run uvicorn fleet.main:app --host 0.0.0.0 --port 8000 --no-proxy-headers
```

Po zobrazení `Uvicorn running` otevřete spodní záložku **Porty**. Přidejte port **8000**, pokud tam není, a z jeho řádku otevřete prohlížeč. Viditelnost zůstává **Private**. Nevkládejte do adresního řádku adresu `0.0.0.0`; použijte adresu přidělenou Codespaces.

## Import

Přihlaste se zvoleným heslem, otevřete **Připojení a data**, vyberte `fleet_context_2026-10-11.json`, vyčkejte na kontrolu a klikněte **Potvrdit import**. Nahrává se skutečný datový JSON, ne jeho `.schema.json` nebo `sheet_manifest.json`.

Pokud přístup přes přesměrovaný port soubor odmítá, lze importovat přímo místně:

1. V Terminálu vytvořte ignorovaný adresář: `mkdir -p .local/import`.
2. V levém Průzkumníku otevřete `.local/import` a nahrajte nebo přetáhněte do něj datový soubor ze svého počítače. Nevkládejte jej do kořene veřejného repozitáře.
3. V novém Terminálu ze stejného checkoutu spusťte následující příkaz. Pokud server používá vlastní `FLEET_DATA_DIR`, nastavte stejnou hodnotu i pro tento příkaz.

```bash
python3 -m uv run python -m fleet.importer .local/import/fleet_context_2026-10-11.json --commit
```

Po úspěšném importu obnovte stránku aplikace. U připraveného snímku se zobrazí 31 evidenčních záznamů a 38 úkolů. Opakování stejného importu nevytvoří duplicity.

## Aktualizace a diagnostika

Zastavte vlastní server pomocí Ctrl+C, potom ve stejném Terminálu:

```bash
git pull --ff-only
python3 -m uv sync --frozen
```

Znovu spusťte web výše uvedeným blokem a obnovte stránku v prohlížeči. Soukromá databáze i heslo zůstávají zachovány.

Při importní chybě aplikace zobrazí stav HTTP a případně kód chyby. HTTP 413 znamená odmítnutou velikost požadavku; pomůže místní import. HTTP 400 vyžaduje kontrolu adresy a serverového nastavení. HTML místo JSON s HTTP 200, 401 nebo 403 může pocházet z přihlášení nebo přístupové brány Codespaces. HTTP 500 vyžaduje kontrolu Terminálu, nikoli vypnutí kontroly vstupních dat. Bez těchto důkazů nelze příčinu určit.

Pro podporu sdílejte jen chybový stav, příslušný řádek požadavku a případný kód chyby. Nesdílejte hesla, tokeny, session cookies ani obsah osobních dokumentů.
